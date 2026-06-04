from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="vertex-pinecone-mcp", alias="APP_NAME")
    gcp_project_id: str = Field(default="", alias="GCP_PROJECT_ID")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    openai_embedding_dimensions: int = Field(default=1024, alias="OPENAI_EMBEDDING_DIMENSIONS")
    openai_generation_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_GENERATION_MODEL")
    pinecone_api_key: str = Field(default="", alias="PINECONE_API_KEY")
    pinecone_host: AnyHttpUrl = Field(
        default="https://news-demo-4fe9eo0.svc.aped-4627-b74a.pinecone.io",
        alias="PINECONE_HOST",
    )
    pinecone_index: str = Field(default="news-demo", alias="PINECONE_INDEX")
    pinecone_namespace: str = Field(default="news", alias="PINECONE_NAMESPACE")
    vertex_location: str = Field(default="us-central1", alias="VERTEX_LOCATION")
    pinecone_hybrid_enabled: bool = Field(default=False, alias="PINECONE_HYBRID_ENABLED")
    pinecone_hybrid_alpha: float = Field(default=0.5, ge=0, le=1, alias="PINECONE_HYBRID_ALPHA")
    rag_max_context_chars: int = Field(default=12000, alias="RAG_MAX_CONTEXT_CHARS")
    memory_namespace: str = Field(default="memory", alias="MEMORY_NAMESPACE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
