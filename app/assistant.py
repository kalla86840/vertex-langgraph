from typing import Any

from app.config import Settings
from app.rag import build_context


AGENTS = {
    "hospital_agent": (
        "Review the retrieved context from the hospital operations perspective. "
        "Identify facility-level constraints, policies, care coordination needs, and source citations."
    ),
    "doctor_agent": (
        "Review the retrieved context from the doctor perspective. "
        "Identify clinical reasoning, diagnosis or treatment considerations, risks, and source citations."
    ),
    "nurse_agent": (
        "Review the retrieved context from the nurse perspective. "
        "Identify patient monitoring, bedside workflow, education, escalation needs, and source citations."
    ),
}


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
    if body.get("output_text"):
        return body["output_text"]

    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


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


def _run_crewai_agents(
    settings: Settings,
    question: str,
    context: str,
    selected: list[str],
) -> list[dict[str, str]]:
    try:
        from crewai import Agent, Crew, Process, Task
    except ImportError as exc:
        raise RuntimeError("CrewAI is not installed") from exc

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError("langchain-openai is not installed") from exc

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for CrewAI generation")

    llm = ChatOpenAI(
        model=settings.crewai_llm_model or settings.openai_generation_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    crew_outputs: list[dict[str, str]] = []

    for name in selected:
        agent = Agent(
            role=name.replace("_", " ").title(),
            goal=AGENTS[name],
            backstory=(
                "You are part of a production RAG crew. You only use retrieved "
                "Pinecone context and you cite sources exactly as provided."
            ),
            llm=llm,
            verbose=settings.crewai_verbose,
            allow_delegation=False,
        )
        task = Task(
            description=(
                f"{AGENTS[name]}\n\nQuestion:\n{question}\n\n"
                f"Retrieved context:\n{context}"
            ),
            expected_output="A concise answer or review with source citations where applicable.",
            agent=agent,
        )
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=settings.crewai_verbose,
        )
        result = crew.kickoff()
        crew_outputs.append({"agent": name, "output": str(result).strip()})

    return crew_outputs


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
        }

    selected = requested_agents or list(AGENTS)
    invalid = sorted(set(selected) - set(AGENTS))
    if invalid:
        raise ValueError(f"Unknown assistant agents: {', '.join(invalid)}")

    try:
        outputs = _run_crewai_agents(settings, question, context, selected)
        engine = "crewai"
    except Exception as exc:
        outputs = _run_openai_fallback(settings, question, context, selected)
        engine = f"openai_fallback: {exc}"

    synthesis = _generate(
        settings,
        "You are the final OpenAI assistant coordinator. Answer using only the retrieved "
        "context and agent reviews. Cite sources like [Source 1]. State uncertainty clearly.\n\n"
        f"Question:\n{question}\n\nRetrieved context:\n{context}\n\nAgent reviews:\n{outputs}",
    )
    return {"answer": synthesis, "agents": outputs, "sources": sources, "engine": engine}
