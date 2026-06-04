# GCP Cloud Run CI/CD

This repository includes a GitHub Actions pipeline that tests the Python API,
builds a Docker image, pushes it to Google Artifact Registry, and deploys a
real-time HTTPS endpoint on Cloud Run.

## Runtime

- Python FastAPI service
- OpenAI Responses API for final answer generation
- AutoGen hospital, doctor, and nurse agents for `/assistant`
- Pinecone retrieval and memory
- Cloud Run real-time endpoint with one warm minimum instance

## Required GCP APIs

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com secretmanager.googleapis.com
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

## Pipeline Output

On every push to `main`, the workflow prints:

```text
Real-time endpoint: https://SERVICE-REGION.a.run.app
Health check: https://SERVICE-REGION.a.run.app/health
```

Use `/assistant` for the AutoGen path:

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
