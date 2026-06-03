from typing import Any

from app.config import Settings


def metadata_text(metadata: dict[str, Any]) -> str:
    for key in ("text", "chunk", "content", "body", "page_content"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_context(matches: list[dict[str, Any]], max_chars: int) -> tuple[str, list[dict[str, Any]]]:
    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    current_length = 0

    for position, match in enumerate(matches, start=1):
        metadata = match.get("metadata") or {}
        text = metadata_text(metadata)
        if not text:
            continue

        title = metadata.get("title") or metadata.get("source_file") or match.get("id") or f"Source {position}"
        site = metadata.get("site")
        published_date = metadata.get("publishedDate")
        source_file = metadata.get("source_file")

        source = {
            "number": position,
            "id": match.get("id"),
            "score": match.get("score"),
            "title": title,
            "site": site,
            "publishedDate": published_date,
            "source_file": source_file,
        }
        source = {key: value for key, value in source.items() if value is not None}

        block = f"[Source {position}] {title}\n{text}"
        if current_length + len(block) > max_chars:
            remaining = max_chars - current_length
            if remaining <= 200:
                break
            block = block[:remaining]

        context_parts.append(block)
        sources.append(source)
        current_length += len(block)

    return "\n\n".join(context_parts), sources


def generate_answer(settings: Settings, question: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    if not settings.gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is required for Vertex AI generation")

    context, sources = build_context(matches, settings.rag_max_context_chars)
    if not context:
        return {
            "answer": "I could not find enough retrieved Pinecone context to answer that question.",
            "sources": [],
        }

    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
    except ImportError as exc:
        raise RuntimeError("google-cloud-aiplatform is required for Vertex AI generation") from exc

    vertexai.init(project=settings.gcp_project_id, location=settings.vertex_location)
    model = GenerativeModel(settings.vertex_generative_model)
    prompt = (
        "Answer using only the retrieved Pinecone context. "
        "If the answer is not in the context, say you do not know. "
        "Cite sources by source number, for example [Source 1].\n\n"
        f"Question:\n{question}\n\nRetrieved context:\n{context}"
    )
    response = model.generate_content(prompt)

    return {
        "answer": response.text,
        "sources": sources,
    }
