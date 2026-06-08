# GCP LangGraph Permissions

This repo is fully GCP-based. The deployment paths are:

- Cloud Build to Vertex AI using `cloudbuild.yaml`
- GitHub Actions to Cloud Run using `.github/workflows/gcp-cloud-run-cicd.yml`

The quickest setup is:

```powershell
.\scripts\setup-gcp-langgraph-permissions.ps1 `
  -ProjectId "YOUR_GCP_PROJECT_ID" `
  -Repository "kalla86840/vertex-langgraph"
```

If you already created a LangGraph artifact bucket, include it:

```powershell
.\scripts\setup-gcp-langgraph-permissions.ps1 `
  -ProjectId "YOUR_GCP_PROJECT_ID" `
  -Repository "kalla86840/vertex-langgraph" `
  -LangGraphOutputBucket "YOUR_LANGGRAPH_OUTPUT_BUCKET"
```

## Required APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com
```

## Secret Manager

The deployed services expect:

```text
OPENAI_API_KEY
PINECONE_API_KEY
```

Create them once:

```bash
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
```

If they already exist, add new versions:

```bash
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets versions add PINECONE_API_KEY --data-file=-
```

## Cloud Build To Vertex AI

Cloud Build deploys the Vertex endpoint named `gcp-langgraph-endpoint`.

Grant the Cloud Build service account:

```text
roles/cloudbuild.builds.builder
roles/artifactregistry.admin
roles/aiplatform.admin
roles/secretmanager.secretAccessor
```

If `LANGGRAPH_OUTPUT_BUCKET` is configured, grant bucket-level access:

```text
roles/storage.objectCreator
```

## GitHub Actions To Cloud Run

The workflow uses Workload Identity Federation. GitHub Actions needs:

```yaml
permissions:
  contents: read
  id-token: write
```

Add these GitHub repository secrets:

```text
GCP_PROJECT_ID
GCP_SERVICE_ACCOUNT
GCP_WORKLOAD_IDENTITY_PROVIDER
```

The deploy/runtime service account needs:

```text
roles/run.admin
roles/artifactregistry.admin
roles/secretmanager.secretAccessor
roles/iam.serviceAccountUser
roles/iam.workloadIdentityUser on the service account policy for the GitHub OIDC principal
```

If `LANGGRAPH_OUTPUT_BUCKET` is configured, grant bucket-level access:

```text
roles/storage.objectCreator
```

## Endpoint Callers

Vertex AI callers need:

```text
aiplatform.endpoints.predict
```

The simple project role is:

```text
roles/aiplatform.user
```
