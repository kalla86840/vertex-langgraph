# GCP Cloud Run CI/CD

This repository includes a GitHub Actions pipeline that tests the Python API,
builds a Docker image, pushes it to Google Artifact Registry, and deploys a
real-time HTTPS endpoint on Cloud Run.

## Runtime

- Python FastAPI service
- OpenAI Responses API for final answer generation
- LangGraph hospital operations workflow for `/langgraph-hospital`
- Optional Google Cloud Storage artifact export
- Pinecone retrieval and memory
- Cloud Run real-time endpoint with one warm minimum instance

## Required GCP APIs

The complete deployment checklist is in `docs/deployment-requirements.md`.
For the Cloud Run GitHub Actions path, you can also run:

```powershell
.\scripts\setup-gcp-cloud-run-permissions.ps1 -ProjectId "YOUR_GCP_PROJECT_ID"
```

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com secretmanager.googleapis.com storage.googleapis.com
```

## Required Secrets

Create application secrets in Google Secret Manager:

```bash
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
```

Create these GitHub repository secrets:

```text
GCP_PROJECT_ID
GCP_SERVICE_ACCOUNT
GCP_WORKLOAD_IDENTITY_PROVIDER
```

The GitHub repository must also allow Actions to request OIDC tokens. In
GitHub, open:

```text
Settings -> Actions -> General -> Workflow permissions
```

Use read access for repository contents. The workflow itself declares:

```yaml
permissions:
  contents: read
  id-token: write
```

`GCP_SERVICE_ACCOUNT` should look like:

```text
github-actions-deployer@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

`GCP_WORKLOAD_IDENTITY_PROVIDER` should look like:

```text
projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

## Service Account Roles

The workflow uses `GCP_SERVICE_ACCOUNT` for deployment authentication and as
the Cloud Run runtime service account, so grant it:

```bash
PROJECT_ID="YOUR_PROJECT_ID"
DEPLOY_SA="github-actions-deployer@$PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/iam.serviceAccountUser"
```

If `LANGGRAPH_OUTPUT_BUCKET` is set, also grant the Cloud Run runtime service
account permission to create objects in that bucket:

```bash
BUCKET="YOUR_LANGGRAPH_OUTPUT_BUCKET"

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/storage.objectCreator"
```

Workload Identity Federation must also allow the GitHub repository principal
to impersonate that service account:

```bash
PROJECT_ID="YOUR_PROJECT_ID"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
DEPLOY_SA="github-actions-deployer@$PROJECT_ID.iam.gserviceaccount.com"
REPO="kalla86840/gcpautogen"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$REPO"
```

For a copy/paste setup script, see `scripts/setup-gcp-cloud-run-permissions.ps1`.

## Pipeline Output

On every push to `main`, the workflow prints:

```text
Real-time endpoint: https://SERVICE-REGION.a.run.app
Health check: https://SERVICE-REGION.a.run.app/health
```

Use `/langgraph-hospital` for the LangGraph hospital operations path:

```bash
curl -X POST "$SERVICE_URL/langgraph-hospital" \
  -H "Content-Type: application/json" \
  -d '{"patient_summary":"Adult patient recovering after observation, stable vitals.","question":"What should the hospital team coordinate next?","top_k":4}'
```

Use `/assistant` for the legacy AutoGen path:

```bash
curl -X POST "$SERVICE_URL/assistant" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize the retrieved guidance and cite sources.","agents":["hospital_agent","doctor_agent","nurse_agent"],"top_k":5}'
```

The same assistant can be called through a Vertex-style prediction body:

```bash
curl -X POST "$SERVICE_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{"instances":[{"mode":"assistant","question":"Summarize the retrieved guidance and cite sources.","agents":["hospital_agent","doctor_agent","nurse_agent"],"top_k":5}]}'
```
