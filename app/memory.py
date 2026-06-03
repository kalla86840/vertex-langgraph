from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.embeddings import embed_text
from app.pinecone_client import get_index
from app.sparse import scale_dense_vector, scale_sparse_values, sparse_text_values


def build_memory_filter(
    user_id: str | None,
    conversation_id: str | None,
    extra_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [{"kind": {"$eq": "memory"}}]
    if user_id:
        filters.append({"user_id": {"$eq": user_id}})
    if conversation_id:
        filters.append({"conversation_id": {"$eq": conversation_id}})
    if extra_filter:
        filters.append(extra_filter)
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def remember(
    settings: Settings,
    content: str,
    user_id: str,
    conversation_id: str | None,
    metadata: dict[str, Any] | None,
    namespace: str | None,
    memory_id: str | None = None,
) -> dict[str, Any]:
    vector = embed_text(settings=settings, text=content, task_type="RETRIEVAL_DOCUMENT")
    sparse_values = None
    if settings.pinecone_hybrid_enabled:
        vector = scale_dense_vector(vector, settings.pinecone_hybrid_alpha)
        sparse_values = scale_sparse_values(
            sparse_text_values(content),
            settings.pinecone_hybrid_alpha,
        )
    target_namespace = namespace or settings.memory_namespace
    record_id = memory_id or f"mem-{uuid4()}"
    now = datetime.now(timezone.utc).isoformat()
    record_metadata = {
        "kind": "memory",
        "text": content,
        "user_id": user_id,
        "created_at": now,
    }
    if conversation_id:
        record_metadata["conversation_id"] = conversation_id
    if metadata:
        record_metadata.update(metadata)

    pinecone_record = {
        "id": record_id,
        "values": vector,
        "metadata": record_metadata,
    }
    if sparse_values is not None:
        pinecone_record["sparse_values"] = sparse_values

    index = get_index(settings)
    index.upsert(vectors=[pinecone_record], namespace=target_namespace)
    return {
        "id": record_id,
        "namespace": target_namespace,
        "metadata": record_metadata,
    }


def recall(
    settings: Settings,
    query: str,
    user_id: str | None,
    conversation_id: str | None,
    top_k: int,
    namespace: str | None,
    include_values: bool,
    extra_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vector = embed_text(settings=settings, text=query, task_type="RETRIEVAL_QUERY")
    sparse_values = None
    if settings.pinecone_hybrid_enabled:
        vector = scale_dense_vector(vector, settings.pinecone_hybrid_alpha)
        sparse_values = scale_sparse_values(
            sparse_text_values(query),
            settings.pinecone_hybrid_alpha,
        )
    target_namespace = namespace or settings.memory_namespace
    index = get_index(settings)
    query_args = {
        "vector": vector,
        "top_k": top_k,
        "namespace": target_namespace,
        "include_metadata": True,
        "include_values": include_values,
        "filter": build_memory_filter(user_id, conversation_id, extra_filter),
    }
    if sparse_values is not None:
        query_args["sparse_vector"] = sparse_values

    result = index.query(**query_args)
    body = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    body["namespace"] = target_namespace
    return body
