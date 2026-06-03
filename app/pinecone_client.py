from pinecone import Pinecone

from app.config import Settings


def get_index(settings: Settings):
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is required")

    client = Pinecone(api_key=settings.pinecone_api_key)
    host = str(settings.pinecone_host).rstrip("/")
    return client.Index(host=host)
