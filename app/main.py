from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.assistant import run_assistant
from app.config import Settings, get_settings
from app.embeddings import embed_text
from app.langgraph_hospital import run_hospital_ops_graph
from app.memory import recall, remember
from app.pinecone_client import get_index
from app.rag import generate_answer
from app.sparse import scale_dense_vector, scale_sparse_values, sparse_text_values


class QueryRequest(BaseModel):
    vector: list[float] | None = Field(default=None, min_length=1)
    sparse_values: dict[str, Any] | None = None
    text: str | None = Field(default=None, min_length=1)
    question: str | None = Field(default=None, min_length=1)
    mode: Literal["search", "rag", "assistant", "dedupe"] = "search"
    agents: list[str] | None = None
    hybrid: bool | None = None
    hybrid_alpha: float | None = Field(default=None, ge=0, le=1)
    top_k: int = Field(default=10, ge=1, le=100)
    duplicate_threshold: float = Field(default=0.95, ge=0)
    exclude_id: str | None = Field(default=None, min_length=1)
    include_metadata: bool = True
    include_values: bool = False
    filter: dict[str, Any] | None = None
    namespace: str | None = None

    @model_validator(mode="after")
    def require_text_or_vector(self) -> "QueryRequest":
        if self.vector is None and not self.text and not self.question:
            raise ValueError("Either text, question, or vector is required")
        return self

    def search_text(self) -> str:
        return self.text or self.question or ""


class FetchRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=100)
    namespace: str | None = None

    @field_validator("ids")
    @classmethod
    def ids_must_not_be_blank(cls, ids: list[str]) -> list[str]:
        if any(not item.strip() for item in ids):
            raise ValueError("ids cannot contain blank values")
        return ids


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    hybrid: bool | None = None
    hybrid_alpha: float | None = Field(default=None, ge=0, le=1)
    top_k: int = Field(default=10, ge=1, le=100)
    include_metadata: bool = True
    include_values: bool = False
    filter: dict[str, Any] | None = None
    namespace: str | None = None


class HospitalLangGraphRequest(BaseModel):
    patient_summary: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=4, ge=1, le=25)
    namespace: str | None = None
    output_bucket: str | None = Field(default=None, min_length=3)
    case_id: str | None = Field(default=None, min_length=1)


class MemoryWriteRequest(BaseModel):
    content: str = Field(..., min_length=1)
    user_id: str = Field(default="default", min_length=1)
    conversation_id: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None
    namespace: str | None = None
    id: str | None = Field(default=None, min_length=1)


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    conversation_id: str | None = Field(default=None, min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    include_values: bool = False
    filter: dict[str, Any] | None = None
    namespace: str | None = None


class VertexPredictRequest(BaseModel):
    instances: list[QueryRequest] = Field(..., min_length=1)


app = FastAPI(
    title="GCP LangGraph Healthcare RAG API",
    version="4.0.0",
    description="Real-time GCP endpoint for Python, OpenAI, LangGraph workflows, and Pinecone RAG.",
)


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "openai": {
            "configured": bool(settings.openai_api_key),
            "embedding_model": settings.openai_embedding_model,
            "embedding_dimensions": settings.openai_embedding_dimensions,
            "generation_model": settings.openai_generation_model,
            "autogen_model": settings.autogen_model,
            "langgraph_model": settings.langgraph_model,
        },
        "agents": ["hospital_agent", "doctor_agent", "nurse_agent"],
        "langgraph": {
            "hospital_ops": True,
            "output_bucket_configured": bool(settings.langgraph_output_bucket),
        },
        "pinecone": {
            "index": settings.pinecone_index,
            "namespace": settings.pinecone_namespace,
            "host": str(settings.pinecone_host),
            "configured": bool(settings.pinecone_api_key),
        },
    }


@app.post("/query")
def query_pinecone(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    namespace = request.namespace or settings.pinecone_namespace

    try:
        vector = request.vector
        if vector is None:
            vector = embed_text(settings, request.search_text())

        sparse_values = request.sparse_values
        hybrid_enabled = request.hybrid if request.hybrid is not None else settings.pinecone_hybrid_enabled
        if hybrid_enabled:
            if sparse_values is None:
                sparse_values = sparse_text_values(request.search_text())
            alpha = request.hybrid_alpha
            if alpha is None:
                alpha = settings.pinecone_hybrid_alpha
            vector = scale_dense_vector(vector, alpha)
            sparse_values = scale_sparse_values(sparse_values, alpha)

        query_args = {
            "vector": vector,
            "top_k": request.top_k,
            "namespace": namespace,
            "include_metadata": request.include_metadata,
            "include_values": request.include_values,
            "filter": request.filter,
        }
        if sparse_values is not None:
            query_args["sparse_vector"] = sparse_values

        index = get_index(settings)
        result = index.query(**query_args)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pinecone query failed: {exc}") from exc

    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


@app.post("/semantic-search")
def semantic_search(
    request: SemanticSearchRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    search_request = QueryRequest(
        text=request.query,
        hybrid=request.hybrid,
        hybrid_alpha=request.hybrid_alpha,
        top_k=request.top_k,
        include_metadata=request.include_metadata,
        include_values=request.include_values,
        filter=request.filter,
        namespace=request.namespace,
    )
    return query_pinecone(request=search_request, settings=settings)


def detect_duplicates(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    namespace = request.namespace or settings.pinecone_namespace
    result = query_pinecone(request=request, settings=settings)
    matches = result.get("matches", [])
    duplicates = [
        match
        for match in matches
        if match.get("id") != request.exclude_id
        and match.get("score") is not None
        and float(match["score"]) >= request.duplicate_threshold
    ]

    result.update(
        {
            "duplicates": duplicates,
            "is_duplicate": bool(duplicates),
            "duplicate_count": len(duplicates),
            "duplicate_threshold": request.duplicate_threshold,
            "namespace": namespace,
        }
    )
    return result


@app.post("/duplicates")
def duplicate_detection(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return detect_duplicates(request=request, settings=settings)


@app.post("/memory")
def write_memory(
    request: MemoryWriteRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return remember(
            settings=settings,
            content=request.content,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            metadata=request.metadata,
            namespace=request.namespace,
            memory_id=request.id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pinecone memory write failed: {exc}") from exc


@app.post("/memory/search")
def search_memory(
    request: MemorySearchRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return recall(
            settings=settings,
            query=request.query,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            namespace=request.namespace,
            include_values=request.include_values,
            extra_filter=request.filter,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pinecone memory search failed: {exc}") from exc


@app.post("/rag")
def rag_pinecone(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    question = request.question or request.text
    if not question:
        raise HTTPException(status_code=422, detail="question or text is required for RAG")

    search_request = request.model_copy(
        update={
            "text": question,
            "include_metadata": True,
            "include_values": False,
        }
    )
    search_result = query_pinecone(request=search_request, settings=settings)
    matches = search_result.get("matches", [])

    try:
        answer = generate_answer(settings=settings, question=question, matches=matches)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RAG answer generation failed: {exc}") from exc

    return {
        "question": question,
        "answer": answer["answer"],
        "sources": answer["sources"],
        "matches": matches,
    }


@app.post("/chat")
def chat(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return rag_pinecone(request=request, settings=settings)


@app.post("/langgraph-hospital")
def langgraph_hospital(
    request: HospitalLangGraphRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    def retriever(text: str, top_k: int, namespace: str | None) -> list[dict[str, Any]]:
        search_request = QueryRequest(
            text=text,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
            include_values=False,
        )
        return query_pinecone(request=search_request, settings=settings).get("matches", [])

    try:
        return run_hospital_ops_graph(
            settings=settings,
            patient_summary=request.patient_summary,
            question=request.question,
            top_k=request.top_k,
            namespace=request.namespace,
            output_bucket=request.output_bucket,
            case_id=request.case_id,
            retriever=retriever,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LangGraph hospital workflow failed: {exc}") from exc


@app.post("/assistant")
def assistant(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    question = request.question or request.text
    if not question:
        raise HTTPException(status_code=422, detail="question or text is required for assistant mode")

    search_request = request.model_copy(
        update={"text": question, "include_metadata": True, "include_values": False}
    )
    matches = query_pinecone(request=search_request, settings=settings).get("matches", [])
    try:
        result = run_assistant(
            settings=settings,
            question=question,
            matches=matches,
            requested_agents=request.agents,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI assistant generation failed: {exc}") from exc
    return {"question": question, **result, "matches": matches}


@app.post("/score")
def score(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return run_inference(request=request, settings=settings)


def run_inference(request: QueryRequest, settings: Settings) -> dict[str, Any]:
    if request.mode == "rag":
        return rag_pinecone(request=request, settings=settings)
    if request.mode == "assistant":
        return assistant(request=request, settings=settings)
    if request.mode == "dedupe":
        return detect_duplicates(request=request, settings=settings)
    return query_pinecone(request=request, settings=settings)


@app.post("/predict")
def predict(
    payload: VertexPredictRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return {
        "predictions": [
            run_inference(request=instance, settings=settings)
            for instance in payload.instances
        ]
    }


@app.post("/fetch")
def fetch_records(
    request: FetchRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    namespace = request.namespace or settings.pinecone_namespace

    try:
        index = get_index(settings)
        result = index.fetch(ids=request.ids, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pinecone fetch failed: {exc}") from exc

    return result.to_dict() if hasattr(result, "to_dict") else dict(result)
