import asyncio
from typing import Any

from app.config import Settings
from app.rag import build_context


AGENTS = {
    "hospital_agent": (
        "Agent 1 is the hospital agent. Review the retrieved context from the "
        "hospital operations perspective. Identify facility-level constraints, "
        "policies, care coordination needs, and source citations."
    ),
    "doctor_agent": (
        "Agent 2 is the doctor agent. Review the retrieved context from the "
        "doctor perspective. Identify clinical reasoning, diagnosis or treatment "
        "considerations, risks, and source citations."
    ),
    "nurse_agent": (
        "Agent 3 is the nurse agent. Review the retrieved context from the nurse "
        "perspective. Identify patient monitoring, bedside workflow, education, "
        "escalation needs, and source citations."
    ),
}


def _extract_response_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _generate(settings: Settings, prompt: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI generation")

    import httpx

    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={"model": settings.openai_generation_model, "input": prompt},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("output_text") or _extract_response_text(body)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(message)


async def _run_autogen_agents_async(
    settings: Settings,
    question: str,
    context: str,
    selected: list[str],
) -> list[dict[str, str]]:
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_ext.models.openai import OpenAIChatCompletionClient
    except ImportError as exc:
        raise RuntimeError("AutoGen AgentChat is not installed") from exc

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for AutoGen generation")

    model_client = OpenAIChatCompletionClient(
        model=settings.autogen_model or settings.openai_generation_model,
        api_key=settings.openai_api_key,
        temperature=settings.autogen_temperature,
    )
    try:
        outputs: list[dict[str, str]] = []
        for name in selected:
            agent = AssistantAgent(
                name=name,
                model_client=model_client,
                system_message=(
                    f"{AGENTS[name]} You are part of a production healthcare RAG team. "
                    "Use only retrieved Pinecone context. Cite sources exactly as provided. "
                    "If the context is insufficient, say what is missing."
                ),
            )
            result = await agent.run(
                task=(
                    "Return a concise, grounded review for the final coordinator. "
                    "Use source citations such as [Source 1].\n\n"
                    f"Agent role:\n{AGENTS[name]}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Retrieved context:\n{context}"
                )
            )
            messages = getattr(result, "messages", [])
            output = _message_content(messages[-1]) if messages else str(result)
            outputs.append({"agent": name, "output": output.strip()})
        return outputs
    finally:
        close = getattr(model_client, "close", None)
        if close is not None:
            await close()


def _run_autogen_agents(
    settings: Settings,
    question: str,
    context: str,
    selected: list[str],
) -> list[dict[str, str]]:
    return asyncio.run(_run_autogen_agents_async(settings, question, context, selected))


def _run_openai_fallback(
    settings: Settings,
    question: str,
    context: str,
    selected: list[str],
) -> list[dict[str, str]]:
    outputs = []
    for name in selected:
        outputs.append(
            {
                "agent": name,
                "output": _generate(
                    settings,
                    f"{AGENTS[name]}\nUse only the supplied context.\n\n"
                    f"Question:\n{question}\n\nRetrieved context:\n{context}",
                ),
            }
        )
    return outputs


def run_assistant(
    settings: Settings,
    question: str,
    matches: list[dict[str, Any]],
    requested_agents: list[str] | None = None,
) -> dict[str, Any]:
    context, sources = build_context(matches, settings.rag_max_context_chars)
    if not context:
        return {
            "answer": "I could not find enough retrieved Pinecone context to answer that question.",
            "agents": [],
            "sources": [],
            "engine": "none",
        }

    selected = requested_agents or list(AGENTS)
    invalid = sorted(set(selected) - set(AGENTS))
    if invalid:
        raise ValueError(f"Unknown assistant agents: {', '.join(invalid)}")

    engine_errors: list[str] = []
    try:
        outputs = _run_autogen_agents(settings, question, context, selected)
        engine = "autogen"
    except Exception as exc:
        engine_errors.append(f"autogen: {exc}")
        outputs = _run_openai_fallback(settings, question, context, selected)
        engine = f"openai_fallback: {'; '.join(engine_errors)}"

    synthesis = _generate(
        settings,
        "You are the final OpenAI AutoGen healthcare coordinator. Answer using only "
        "the retrieved context and agent reviews. Cite sources like [Source 1]. "
        "State uncertainty clearly.\n\n"
        f"Question:\n{question}\n\nRetrieved context:\n{context}\n\nAgent reviews:\n{outputs}",
    )
    return {"answer": synthesis, "agents": outputs, "sources": sources, "engine": engine}
