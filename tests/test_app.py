from fastapi.testclient import TestClient

from app.main import app


def test_health_uses_pinecone_defaults(monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["pinecone"]["index"] == "news-demo"
    assert body["pinecone"]["namespace"] == "news"
    assert body["pinecone"]["host"] == "https://news-demo-4fe9eo0.svc.aped-4627-b74a.pinecone.io/"
    assert body["pinecone"]["configured"] is False


def test_fetch_rejects_blank_ids():
    client = TestClient(app)

    response = client.post("/fetch", json={"ids": ["valid-id", " "]})

    assert response.status_code == 422


def test_score_requires_text_or_vector():
    client = TestClient(app)

    response = client.post("/score", json={"top_k": 3})

    assert response.status_code == 422


def test_predict_requires_instances():
    client = TestClient(app)

    response = client.post("/predict", json={})

    assert response.status_code == 422


def test_predict_accepts_vertex_shape(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    monkeypatch.setattr("app.main.run_inference", lambda request, settings: {"matches": []})

    client = TestClient(app)
    response = client.post("/predict", json={"instances": [{"text": "hello", "top_k": 3}]})

    assert response.status_code == 200
    assert response.json() == {"predictions": [{"matches": []}]}


def test_score_accepts_text_payload(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    class FakeResult:
        def to_dict(self):
            return {"matches": []}

    class FakeIndex:
        def query(self, **kwargs):
            assert kwargs["vector"] == [0.1, 0.2, 0.3]
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.1, 0.2, 0.3])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post("/score", json={"text": "Edgio earnings call", "top_k": 3})

    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_semantic_search_accepts_query_payload(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    class FakeResult:
        def to_dict(self):
            return {"matches": [{"id": "match-1", "score": 0.92}]}

    class FakeIndex:
        def query(self, **kwargs):
            assert kwargs["vector"] == [0.7, 0.8, 0.9]
            assert kwargs["top_k"] == 4
            assert kwargs["namespace"] == "news"
            assert kwargs["include_metadata"] is True
            assert kwargs["include_values"] is False
            return FakeResult()

    def fake_embed_text(settings, text):
        assert text == "semantic pinecone search"
        return [0.7, 0.8, 0.9]

    monkeypatch.setattr("app.main.embed_text", fake_embed_text)
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/semantic-search",
        json={"query": "semantic pinecone search", "top_k": 4},
    )

    assert response.status_code == 200
    assert response.json() == {"matches": [{"id": "match-1", "score": 0.92}]}


def test_semantic_search_can_query_with_hybrid_sparse_values(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {"matches": [{"id": "match-1", "score": 0.91}]}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [1.0, 2.0, 3.0])
    monkeypatch.setattr(
        "app.main.sparse_text_values",
        lambda text: {"indices": [11, 22], "values": [3.0, 1.0]},
    )
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/semantic-search",
        json={
            "query": "Vertex Pinecone hybrid search",
            "top_k": 4,
            "hybrid": True,
            "hybrid_alpha": 0.25,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"matches": [{"id": "match-1", "score": 0.91}]}
    assert captured["vector"] == [0.25, 0.5, 0.75]
    assert captured["sparse_vector"] == {"indices": [11, 22], "values": [2.25, 0.75]}
    assert captured["top_k"] == 4


def test_query_can_use_explicit_sparse_values(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {"matches": []}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/query",
        json={
            "vector": [0.2, 0.4],
            "sparse_values": {"indices": [7], "values": [2.0]},
            "hybrid": True,
            "hybrid_alpha": 0.5,
        },
    )

    assert response.status_code == 200
    assert captured["vector"] == [0.1, 0.2]
    assert captured["sparse_vector"] == {"indices": [7], "values": [1.0]}


def test_duplicate_detection_filters_matches_by_threshold(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {
                "matches": [
                    {"id": "same-record", "score": 1.0},
                    {"id": "duplicate-1", "score": 0.98},
                    {"id": "near-match", "score": 0.91},
                ]
            }

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.4, 0.5, 0.6])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/duplicates",
        json={
            "text": "Vertex Pinecone duplicate candidate",
            "top_k": 3,
            "duplicate_threshold": 0.95,
            "exclude_id": "same-record",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_duplicate"] is True
    assert body["duplicate_count"] == 1
    assert body["duplicates"] == [{"id": "duplicate-1", "score": 0.98}]
    assert body["duplicate_threshold"] == 0.95
    assert body["namespace"] == "news"
    assert captured["vector"] == [0.4, 0.5, 0.6]
    assert captured["top_k"] == 3
    assert captured["include_metadata"] is True


def test_memory_write_upserts_to_memory_namespace(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    captured = {}

    class FakeIndex:
        def upsert(self, **kwargs):
            captured.update(kwargs)
            return {"upserted_count": 1}

    def fake_embed_text(settings, text, task_type="RETRIEVAL_QUERY"):
        assert text == "User prefers short technical answers."
        assert task_type == "RETRIEVAL_DOCUMENT"
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("app.memory.embed_text", fake_embed_text)
    monkeypatch.setattr("app.memory.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/memory",
        json={
            "id": "mem-test",
            "content": "User prefers short technical answers.",
            "user_id": "user-1",
            "conversation_id": "thread-1",
            "metadata": {"topic": "preferences"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "mem-test"
    assert body["namespace"] == "memory"
    assert captured["namespace"] == "memory"
    assert captured["vectors"][0]["id"] == "mem-test"
    assert captured["vectors"][0]["values"] == [0.1, 0.2, 0.3]
    assert captured["vectors"][0]["metadata"]["kind"] == "memory"
    assert captured["vectors"][0]["metadata"]["user_id"] == "user-1"
    assert captured["vectors"][0]["metadata"]["conversation_id"] == "thread-1"
    assert captured["vectors"][0]["metadata"]["topic"] == "preferences"


def test_memory_search_filters_by_user_and_conversation(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {"matches": [{"id": "mem-test", "score": 0.95}]}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    def fake_embed_text(settings, text, task_type="RETRIEVAL_QUERY"):
        assert text == "How should answers be written?"
        assert task_type == "RETRIEVAL_QUERY"
        return [0.4, 0.5, 0.6]

    monkeypatch.setattr("app.memory.embed_text", fake_embed_text)
    monkeypatch.setattr("app.memory.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/memory/search",
        json={
            "query": "How should answers be written?",
            "user_id": "user-1",
            "conversation_id": "thread-1",
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "matches": [{"id": "mem-test", "score": 0.95}],
        "namespace": "memory",
    }
    assert captured["vector"] == [0.4, 0.5, 0.6]
    assert captured["top_k"] == 3
    assert captured["namespace"] == "memory"
    assert captured["include_metadata"] is True
    assert captured["include_values"] is False
    assert captured["filter"] == {
        "$and": [
            {"kind": {"$eq": "memory"}},
            {"user_id": {"$eq": "user-1"}},
            {"conversation_id": {"$eq": "thread-1"}},
        ]
    }


def test_memory_search_uses_hybrid_when_enabled(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("PINECONE_HYBRID_ENABLED", "true")
    monkeypatch.setenv("PINECONE_HYBRID_ALPHA", "0.5")

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {"matches": []}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return FakeResult()

    monkeypatch.setattr("app.memory.embed_text", lambda settings, text, task_type="RETRIEVAL_QUERY": [2.0, 4.0])
    monkeypatch.setattr(
        "app.memory.sparse_text_values",
        lambda text: {"indices": [8], "values": [6.0]},
    )
    monkeypatch.setattr("app.memory.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post("/memory/search", json={"query": "hybrid memory", "top_k": 2})

    assert response.status_code == 200
    assert captured["vector"] == [1.0, 2.0]
    assert captured["sparse_vector"] == {"indices": [8], "values": [3.0]}


def test_score_accepts_vertex_text_payload(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    class FakeResult:
        def to_dict(self):
            return {"matches": []}

    class FakeIndex:
        def query(self, **kwargs):
            assert kwargs["vector"] == [0.4, 0.5, 0.6]
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.4, 0.5, 0.6])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post("/score", json={"text": "Vertex semantic search", "top_k": 3})

    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_score_accepts_dedupe_mode(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    class FakeResult:
        def to_dict(self):
            return {"matches": [{"id": "record-1", "score": 0.94}]}

    class FakeIndex:
        def query(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.1, 0.2, 0.3])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())

    client = TestClient(app)
    response = client.post(
        "/score",
        json={
            "mode": "dedupe",
            "text": "Potential duplicate",
            "duplicate_threshold": 0.95,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_duplicate"] is False
    assert body["duplicate_count"] == 0
    assert body["duplicates"] == []


def test_score_rag_mode_returns_answer(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    class FakeResult:
        def to_dict(self):
            return {
                "matches": [
                    {
                        "id": "record-1",
                        "score": 0.99,
                        "metadata": {
                            "title": "Edgio Q3 2023 Earnings Call Transcript",
                            "text": "Edgio discussed its Q3 2023 earnings call results.",
                        },
                    }
                ]
            }

    class FakeIndex:
        def query(self, **kwargs):
            assert kwargs["vector"] == [0.1, 0.2, 0.3]
            assert kwargs["include_metadata"] is True
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.1, 0.2, 0.3])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())
    monkeypatch.setattr(
        "app.main.generate_answer",
        lambda settings, question, matches: {
            "answer": "Edgio discussed its Q3 2023 earnings call results. [Source 1]",
            "sources": [{"number": 1, "title": "Edgio Q3 2023 Earnings Call Transcript"}],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/score",
        json={
            "mode": "rag",
            "question": "What did Edgio discuss in Q3 2023?",
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Edgio discussed its Q3 2023 earnings call results. [Source 1]"
    assert body["sources"][0]["number"] == 1
    assert body["matches"][0]["id"] == "record-1"


def test_chat_uses_rag_answer_path(monkeypatch):
    monkeypatch.setattr(
        "app.main.rag_pinecone",
        lambda request, settings: {"answer": "grounded chatbot response"},
    )

    client = TestClient(app)
    response = client.post("/chat", json={"question": "What is in the docs?"})

    assert response.status_code == 200
    assert response.json() == {"answer": "grounded chatbot response"}


def test_assistant_returns_agent_synthesis(monkeypatch):
    class FakeResult:
        def to_dict(self):
            return {"matches": [{"id": "record-1", "metadata": {"text": "context"}}]}

    class FakeIndex:
        def query(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr("app.main.embed_text", lambda settings, text: [0.1, 0.2])
    monkeypatch.setattr("app.main.get_index", lambda settings: FakeIndex())
    monkeypatch.setattr(
        "app.main.run_assistant",
        lambda settings, question, matches, requested_agents: {
            "answer": "assistant synthesis [Source 1]",
            "agents": [{"agent": "retrieval_agent", "output": "review"}],
            "sources": [{"number": 1, "id": "record-1"}],
        },
    )

    client = TestClient(app)
    response = client.post(
        "/assistant",
        json={"question": "Summarize the docs", "agents": ["retrieval_agent"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "assistant synthesis [Source 1]"
    assert body["agents"][0]["agent"] == "retrieval_agent"
