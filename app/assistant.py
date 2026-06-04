from typing import Any

from app.config import Settings
from app.rag import build_context


AGENTS = {
    "retrieval_agent": "Identify the retrieved passages that directly answer the question and cite source numbers.",
    "procedure_agent": "Turn the retrieved context into concise ordered guidance when steps are useful.",
    "review_agent": "Check the proposed guidance for unsupported claims, missing caveats, and escalation conditions.",
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

    synthesis = _generate(
        settings,
        "You are the final OpenAI assistant coordinator. Answer using only the retrieved "
        "context and agent reviews. Cite sources like [Source 1]. State uncertainty clearly.\n\n"
        f"Question:\n{question}\n\nRetrieved context:\n{context}\n\nAgent reviews:\n{outputs}",
    )
    return {"answer": synthesis, "agents": outputs, "sources": sources}
