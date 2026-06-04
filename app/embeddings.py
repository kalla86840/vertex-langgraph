from app.config import Settings


def embed_text(settings: Settings, text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")

    import httpx

    payload = {
        "model": settings.openai_embedding_model,
        "input": text,
    }
    if settings.openai_embedding_dimensions > 0:
        payload["dimensions"] = settings.openai_embedding_dimensions

    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
