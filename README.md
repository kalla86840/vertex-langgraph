# GCP CrewAI RAG Endpoint

This repository deploys a real-time Google Cloud endpoint for Pinecone-backed
RAG, chatbots, and CrewAI assistants. It uses Python/FastAPI for serving,
OpenAI for embeddings and generation, CrewAI for multi-agent review, and
Pinecone for retrieval and memory.

## Capabilities

- Pinecone semantic and optional hybrid search
- RAG answers with Pinecone source citations
- `/chat` route for a grounded chatbot
- `/assistant` route with CrewAI hospital, doctor, and nurse agents
- durable Pinecone conversation memory routes
- duplicate detection, fetch, and Vertex online prediction routes
- GitHub Actions CI/CD to Artifact Registry and a Cloud Run real-time endpoint
- Cloud Build CI/CD to Artifact Registry and a Vertex AI endpoint

## GitHub Actions GCP Cloud Run CI/CD

The primary pipeline is `.github/workflows/gcp-cloud-run-cicd.yml`. On every
push to `main`, it installs dependencies, runs tests, builds the container,
pushes it to Artifact Registry, deploys Cloud Run with Secret Manager-backed
OpenAI and Pinecone keys, and prints the live HTTPS endpoint URL.

See `docs/gcp-cloud-run-cicd.md` for Workload Identity Federation, GitHub
secrets, IAM roles, and a sample `/assistant` request.

## Required Google Cloud Setup

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
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
$env:OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
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

The script chunks each file, creates OpenAI embeddings with
`text-embedding-3-small`, and upserts records into Pinecone.

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
  "agents": ["hospital_agent", "doctor_agent", "nurse_agent"],
  "top_k": 5,
  "namespace": "news"
}
```

Send that payload to `POST /assistant` for the CrewAI agent path, or wrap it in `instances` for the
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
