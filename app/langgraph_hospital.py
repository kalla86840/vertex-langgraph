import json
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict
from uuid import uuid4

from app.config import Settings
from app.rag import build_context


Urgency = Literal["urgent_review", "standard_review"]
Retriever = Callable[[str, int, str | None], list[dict[str, Any]]]


class HospitalGraphState(TypedDict, total=False):
    case_id: str
    patient_summary: str
    question: str
    urgency: Urgency
    retrieval_namespace: str | None
    top_k: int
    matches: list[dict[str, Any]]
    context: str
    sources: list[dict[str, Any]]
    care_team_notes: dict[str, str]
    answer: str
    artifact: dict[str, Any]
    output_bucket: str | None


def _extract_response_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _generate(settings: Settings, prompt: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for LangGraph OpenAI generation")

    import httpx

    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={"model": settings.langgraph_model or settings.openai_generation_model, "input": prompt},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("output_text") or _extract_response_text(body)


def _route_urgency(state: HospitalGraphState) -> Urgency:
    text = f"{state.get('patient_summary', '')} {state.get('question', '')}".lower()
    urgent_terms = ("chest pain", "stroke", "sepsis", "shortness of breath", "critical", "unresponsive")
    return "urgent_review" if any(term in text for term in urgent_terms) else "standard_review"


def _upload_json(bucket_name: str, destination: str, payload: dict[str, Any]) -> str:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError("google-cloud-storage is required for GCS artifact upload") from exc

    client = storage.Client()
    blob = client.bucket(bucket_name).blob(destination)
    blob.upload_from_string(
        json.dumps(payload, indent=2, sort_keys=True),
        content_type="application/json",
    )
    return f"gs://{bucket_name}/{destination}"


def build_hospital_ops_graph(settings: Settings, retriever: Retriever | None = None):
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError("langgraph is required for the hospital ops workflow") from exc

    def intake_node(state: HospitalGraphState) -> HospitalGraphState:
        return {
            "case_id": state.get("case_id") or f"case-{uuid4().hex[:8]}",
            "top_k": state.get("top_k") or 4,
            "retrieval_namespace": state.get("retrieval_namespace"),
            "care_team_notes": {},
        }

    def retrieve_guidance_node(state: HospitalGraphState) -> HospitalGraphState:
        if retriever is None:
            return {"matches": [], "context": "", "sources": []}

        matches = retriever(
            f"{state.get('patient_summary', '')}\n{state.get('question', '')}".strip(),
            state.get("top_k") or 4,
            state.get("retrieval_namespace"),
        )
        context, sources = build_context(matches, settings.rag_max_context_chars)
        return {"matches": matches, "context": context, "sources": sources}

    def urgent_review_node(state: HospitalGraphState) -> HospitalGraphState:
        notes = dict(state.get("care_team_notes") or {})
        notes["hospital_ops"] = (
            "Urgent path: notify charge nurse and attending, confirm bed/monitoring capacity, "
            "and prepare escalation handoff."
        )
        return {"urgency": "urgent_review", "care_team_notes": notes}

    def standard_review_node(state: HospitalGraphState) -> HospitalGraphState:
        notes = dict(state.get("care_team_notes") or {})
        notes["hospital_ops"] = (
            "Standard path: coordinate routine care team review, patient education, and discharge readiness checks."
        )
        return {"urgency": "standard_review", "care_team_notes": notes}

    def nurse_review_node(state: HospitalGraphState) -> HospitalGraphState:
        notes = dict(state.get("care_team_notes") or {})
        notes["nurse"] = (
            "Track vital signs, symptoms, medication timing, safety risks, and clear escalation triggers."
        )
        return {"care_team_notes": notes}

    def doctor_review_node(state: HospitalGraphState) -> HospitalGraphState:
        notes = dict(state.get("care_team_notes") or {})
        notes["doctor"] = (
            "Assess likely diagnosis, contraindications, missing labs/imaging, and treatment tradeoffs."
        )
        return {"care_team_notes": notes}

    def synthesize_node(state: HospitalGraphState) -> HospitalGraphState:
        context = state.get("context") or "No retrieved Pinecone context was available."
        prompt = (
            "You are a hospital operations coordinator using a LangGraph workflow. "
            "This is a simple demo, not medical advice. Use the patient summary, route, "
            "care-team notes, and retrieved context to produce a concise operational plan. "
            "Cite retrieved sources as [Source 1] when available and state what is missing.\n\n"
            f"Case ID: {state.get('case_id')}\n"
            f"Patient summary: {state.get('patient_summary')}\n"
            f"Question: {state.get('question')}\n"
            f"Route: {state.get('urgency')}\n"
            f"Care-team notes: {state.get('care_team_notes')}\n\n"
            f"Retrieved context:\n{context}"
        )
        return {"answer": _generate(settings, prompt)}

    def artifact_node(state: HospitalGraphState) -> HospitalGraphState:
        bucket_name = state.get("output_bucket") or settings.langgraph_output_bucket
        payload = {
            "case_id": state.get("case_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "patient_summary": state.get("patient_summary"),
            "question": state.get("question"),
            "urgency": state.get("urgency"),
            "answer": state.get("answer"),
            "care_team_notes": state.get("care_team_notes") or {},
            "sources": state.get("sources") or [],
        }
        if not bucket_name:
            return {"artifact": {"status": "skipped", "reason": "No output bucket was provided."}}

        destination = f"langgraph-hospital/{payload['case_id']}.json"
        uri = _upload_json(bucket_name, destination, payload)
        return {"artifact": {"status": "uploaded", "uri": uri}}

    graph = StateGraph(HospitalGraphState)
    graph.add_node("intake", intake_node)
    graph.add_node("retrieve_guidance", retrieve_guidance_node)
    graph.add_node("urgent_review", urgent_review_node)
    graph.add_node("standard_review", standard_review_node)
    graph.add_node("nurse_review", nurse_review_node)
    graph.add_node("doctor_review", doctor_review_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("artifact", artifact_node)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "retrieve_guidance")
    graph.add_conditional_edges(
        "retrieve_guidance",
        _route_urgency,
        {
            "urgent_review": "urgent_review",
            "standard_review": "standard_review",
        },
    )
    graph.add_edge("urgent_review", "nurse_review")
    graph.add_edge("standard_review", "nurse_review")
    graph.add_edge("nurse_review", "doctor_review")
    graph.add_edge("doctor_review", "synthesize")
    graph.add_edge("synthesize", "artifact")
    graph.add_edge("artifact", END)

    return graph.compile()


def run_hospital_ops_graph(
    settings: Settings,
    patient_summary: str,
    question: str,
    top_k: int = 4,
    namespace: str | None = None,
    output_bucket: str | None = None,
    case_id: str | None = None,
    retriever: Retriever | None = None,
) -> dict[str, Any]:
    graph = build_hospital_ops_graph(settings=settings, retriever=retriever)
    state: HospitalGraphState = {
        "case_id": case_id or "",
        "patient_summary": patient_summary,
        "question": question,
        "top_k": top_k,
        "retrieval_namespace": namespace,
        "output_bucket": output_bucket,
    }
    result = graph.invoke(state)
    return {
        "case_id": result.get("case_id"),
        "urgency": result.get("urgency"),
        "answer": result.get("answer"),
        "care_team_notes": result.get("care_team_notes") or {},
        "sources": result.get("sources") or [],
        "artifact": result.get("artifact") or {},
        "matches": result.get("matches") or [],
        "graph_principles": [
            "Typed shared state carries the case through each node.",
            "Nodes isolate intake, retrieval, role review, synthesis, and artifact export.",
            "Conditional routing sends urgent cases down a different operations path.",
            "The compiled graph can run inside FastAPI, Cloud Run, or Vertex prediction.",
        ],
    }
