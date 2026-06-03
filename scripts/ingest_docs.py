import argparse
import hashlib
from pathlib import Path

from pinecone import Pinecone

from app.config import get_settings
from app.embeddings import embed_text
from app.sparse import scale_dense_vector, scale_sparse_values, sparse_text_values


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def stable_id(source_file: str, chunk_number: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_file}:{chunk_number}:{text}".encode("utf-8")).hexdigest()
    return digest[:32]


def ingest_docs(docs_dir: Path, chunk_size: int, overlap: int, batch_size: int) -> None:
    settings = get_settings()
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is required")

    pinecone_client = Pinecone(api_key=settings.pinecone_api_key)
    index = pinecone_client.Index(host=str(settings.pinecone_host).rstrip("/"))

    txt_files = sorted(docs_dir.glob("*.txt"))
    if not txt_files:
        raise RuntimeError(f"No .txt files found in {docs_dir}")

    pending: list[dict] = []
    total_chunks = 0

    for path in txt_files:
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text=text, chunk_size=chunk_size, overlap=overlap)

        for chunk_number, chunk in enumerate(chunks, start=1):
            pending.append(
                {
                    "id": stable_id(path.name, chunk_number, chunk),
                    "source_file": path.name,
                    "chunk_number": chunk_number,
                    "text": chunk,
                    "title": path.stem.replace("_", " ").replace("-", " ").title(),
                }
            )

            if len(pending) >= batch_size:
                total_chunks += upsert_batch(index, settings, pending)
                pending.clear()

    if pending:
        total_chunks += upsert_batch(index, settings, pending)

    print(f"Ingested {total_chunks} chunks into Pinecone namespace '{settings.pinecone_namespace}'.")


def upsert_batch(index, settings, records: list[dict]) -> int:
    embeddings = [
        embed_text(settings=settings, text=record["text"], task_type="RETRIEVAL_DOCUMENT")
        for record in records
    ]

    vectors = []
    for record, embedding in zip(records, embeddings):
        values = embedding
        sparse_values = None
        if settings.pinecone_hybrid_enabled:
            values = scale_dense_vector(embedding, settings.pinecone_hybrid_alpha)
            sparse_values = scale_sparse_values(
                sparse_text_values(record["text"]),
                settings.pinecone_hybrid_alpha,
            )

        vector = {
            "id": record["id"],
            "values": values,
            "metadata": {
                "source_file": record["source_file"],
                "chunk_number": record["chunk_number"],
                "title": record["title"],
                "text": record["text"],
            },
        }
        if sparse_values is not None:
            vector["sparse_values"] = sparse_values
        vectors.append(vector)

    index.upsert(vectors=vectors, namespace=settings.pinecone_namespace)
    return len(vectors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest .txt documents into Pinecone for RAG.")
    parser.add_argument("--docs-dir", default="docs", help="Folder containing .txt files.")
    parser.add_argument("--chunk-size", type=int, default=1200, help="Characters per chunk.")
    parser.add_argument("--overlap", type=int, default=150, help="Characters of overlap between chunks.")
    parser.add_argument("--batch-size", type=int, default=50, help="Embedding/upsert batch size.")
    args = parser.parse_args()

    ingest_docs(
        docs_dir=Path(args.docs_dir),
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
