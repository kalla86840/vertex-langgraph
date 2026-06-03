from typing import Any

from app.config import Settings
from app.rag import build_context


AGENTS = {
    "retrieval_agent": "Identify the retrieved passages that directly answer the question and cite source numbers.",
    "procedure_agent": "Turn the retrieved context into concise ordered guidance when steps are useful.",
    "review_agent": "Check the proposed guidance for unsupported claims, missing caveats, and escalation conditions.",
}


def _generate(settings: Settings, prompt: str) -> str:
    if not settings.gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is required for Vertex AI generation")

    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project=settings.gcp_project_id, location=settings.vertex_location)
    return GenerativeModel(settings.vertex_generative_model).generate_content(prompt).text


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
        "You are the final Vertex AI assistant coordinator. Answer using only the retrieved "
        "context and agent reviews. Cite sources like [Source 1]. State uncertainty clearly.\n\n"
        f"Question:\n{question}\n\nRetrieved context:\n{context}\n\nAgent reviews:\n{outputs}",
    )
    return {"answer": synthesis, "agents": outputs, "sources": sources}
