from app.config import Settings


def embed_text(settings: Settings, text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    if not settings.gcp_project_id:
        raise RuntimeError("GCP_PROJECT_ID is required for Vertex AI embeddings")

    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
    except ImportError as exc:
        raise RuntimeError("google-cloud-aiplatform is required for Vertex AI embeddings") from exc

    vertexai.init(project=settings.gcp_project_id, location=settings.vertex_location)
    model = TextEmbeddingModel.from_pretrained(settings.vertex_embedding_model)
    kwargs = {}
    if settings.vertex_embedding_dimensions > 0:
        kwargs["output_dimensionality"] = settings.vertex_embedding_dimensions

    embedding = model.get_embeddings([TextEmbeddingInput(text, task_type)], **kwargs)[0]
    return embedding.values
