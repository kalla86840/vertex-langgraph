# LangGraph GCP Hospital Example

This repo includes a simple LangGraph hospital operations workflow at
`POST /langgraph-hospital`. It uses OpenAI for synthesis, Pinecone for optional
retrieved guidance, and Google Cloud Storage for optional JSON artifact export.

## What The Graph Shows

- Typed shared state carries a hospital case through the workflow.
- Nodes isolate intake, retrieval, urgent/standard routing, nurse review,
  doctor review, final synthesis, and artifact export.
- Conditional edges route urgent cases differently from routine cases.
- The compiled graph runs inside the existing FastAPI service, so it can be
  served by Cloud Run or Vertex AI.

## Request

```json
{
  "case_id": "case-demo-001",
  "patient_summary": "Adult patient recovering after observation, stable vitals.",
  "question": "What should the hospital team coordinate next?",
  "top_k": 4,
  "namespace": "news",
  "output_bucket": ""
}
```

Send it locally:

```bash
curl -X POST "http://localhost:8080/langgraph-hospital" \
  -H "Content-Type: application/json" \
  -d '{"patient_summary":"Adult patient recovering after observation, stable vitals.","question":"What should the hospital team coordinate next?","top_k":4}'
```

If `output_bucket` is empty and `LANGGRAPH_OUTPUT_BUCKET` is not set, the
workflow returns the result inline and skips artifact upload. If a bucket is
provided, it writes:

```text
gs://YOUR_BUCKET/langgraph-hospital/CASE_ID.json
```

## GCP Items To Prepare

You already have the OpenAI key in Secret Manager, which this service expects
as `OPENAI_API_KEY`. The existing deployment files mount that secret.

Create a GCS bucket later if you want artifact export:

```bash
PROJECT_ID="YOUR_GCP_PROJECT_ID"
BUCKET="YOUR_LANGGRAPH_OUTPUT_BUCKET"
REGION="us-central1"

gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

Grant the runtime service account permission to write objects:

```bash
RUNTIME_SA="YOUR_RUNTIME_SERVICE_ACCOUNT@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com"

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectCreator"
```

Set the default bucket during deployment with `LANGGRAPH_OUTPUT_BUCKET`, or
pass `output_bucket` per request.

## Required Runtime Values

```text
OPENAI_API_KEY
PINECONE_API_KEY
PINECONE_HOST
PINECONE_INDEX
PINECONE_NAMESPACE
LANGGRAPH_MODEL
LANGGRAPH_OUTPUT_BUCKET
```

`LANGGRAPH_OUTPUT_BUCKET` is optional. Without it, no GCS write is attempted.
