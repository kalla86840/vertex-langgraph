# Vertex Pinecone MCP

This repository deploys a Google Cloud Vertex AI custom-container endpoint for
Pinecone-backed MCP inference, chatbots, and assistants. It uses Vertex AI
embeddings for retrieval and Gemini on Vertex AI for grounded answer generation.

## Capabilities

- Pinecone semantic and optional hybrid search
- RAG answers with Pinecone source citations
- `/chat` route for a grounded chatbot
- `/assistant` route with retrieval, procedure, and review agents
- durable Pinecone conversation memory routes
- duplicate detection, fetch, and Vertex online prediction routes
- Cloud Build CI/CD to Artifact Registry and a Vertex AI endpoint

## Required Google Cloud Setup

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
```

Grant the Cloud Build service account access to Secret Manager, Artifact
Registry, and Vertex AI. Then deploy:

```bash
gcloud builds submit --config cloudbuild.yaml
```

The build tests the app, builds the container, pushes it to Artifact Registry,
uploads a Vertex model, creates or reuses the endpoint, and deploys the model.
The default online endpoint name is `vertex-pinecone-mcp`.

## Required Google Cloud IAM

For Cloud Build deployment, grant the trigger service account the roles needed
to build, push images, read the Pinecone secret, and deploy Vertex AI models.
For the current project, the trigger service account shown in the console is:

```text
683447325858-compute@developer.gserviceaccount.com
```

```bash
PROJECT_ID="inner-domain-397315"
BUILD_SA="683447325858-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" \
  --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" \
  --role="roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" \
  --role="roles/aiplatform.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILD_SA" \
  --role="roles/secretmanager.secretAccessor"
```

To test or call the endpoint from the Vertex UI, a webpage backend, or another
client, the caller needs `aiplatform.endpoints.predict`. The practical project
role is Vertex AI User:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:YOUR_EMAIL@gmail.com" \
  --role="roles/aiplatform.user"
```

For a future webpage backend, grant the same role to the backend service
account instead of a user.

The same commands are kept in `docs/gcp-iam-permissions.md` for quick reuse.

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GCP_PROJECT_ID = "YOUR_GCP_PROJECT_ID"
$env:PINECONE_API_KEY = "YOUR_PINECONE_API_KEY"
uvicorn app.main:app --reload --port 8080
```

Application Default Credentials are required locally:

```bash
gcloud auth application-default login
```

## Ingest Documents

Add `.txt` files to `docs/`, then run:

```bash
python scripts/ingest_docs.py --docs-dir docs
```

The script chunks each file, creates `RETRIEVAL_DOCUMENT` embeddings with
`gemini-embedding-001`, and upserts records into Pinecone.

## Chatbot Request

```json
{
  "question": "What did Edgio discuss in its Q3 2023 earnings call?",
  "top_k": 5,
  "namespace": "news"
}
```

Send that payload to `POST /chat`.

## Assistant Request

```json
{
  "question": "Summarize the retrieved guidance and flag important caveats.",
  "mode": "assistant",
  "agents": ["retrieval_agent", "procedure_agent", "review_agent"],
  "top_k": 5,
  "namespace": "news"
}
```

Send that payload to `POST /assistant`, or wrap it in `instances` for the
Vertex prediction route:

```json
{
  "instances": [
    {
      "mode": "assistant",
      "question": "Summarize the retrieved guidance.",
      "top_k": 5
    }
  ]
}
```

## Routes

- `GET /health`
- `POST /predict`
- `POST /score`
- `POST /query`
- `POST /semantic-search`
- `POST /rag`
- `POST /chat`
- `POST /assistant`
- `POST /duplicates`
- `POST /memory`
- `POST /memory/search`
- `POST /fetch`

Configuration defaults live in `config/settings.yaml`, Cloud Build deployment
settings live in `cloudbuild.yaml`, and environment examples live in
`.env.example`.

## AWS CodePipeline CI/CD

For an AWS-managed CI/CD pipeline that deploys this container to a real-time
GCP Vertex AI endpoint, see `docs/aws-codepipeline-vertex.md`. The stack uses
GitHub source from `kalla86840/vertex-mcp-ops`, AWS CodeBuild for tests and
container build, Google Artifact Registry for the image, and Vertex AI Endpoint
for online inference.
