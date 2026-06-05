# Deployment Requirements

Use this checklist before running the GCP CrewAI real-time endpoint pipelines.

## Required Local Tools

- Google Cloud CLI authenticated with a project owner or IAM admin account
- Docker, only for local container testing
- Python 3.11 for parity with CI
- GitHub repository admin access for Actions secrets and OIDC setup

## Required GCP APIs

```bash
PROJECT_ID="YOUR_GCP_PROJECT_ID"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com
```

## Required Secrets

```bash
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
```

If the secrets already exist, add a new version instead:

```bash
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets versions add PINECONE_API_KEY --data-file=-
```

## Cloud Build to Vertex AI Permissions

`cloudbuild.yaml` builds the image, pushes it to Artifact Registry, uploads a
Vertex AI model, creates or reuses the `vertex-pinecone-mcp` endpoint, and
deploys the model for online prediction.

PowerShell helper:

```powershell
.\scripts\setup-gcp-vertex-permissions.ps1 -ProjectId "YOUR_GCP_PROJECT_ID" -CallerMember "user:YOUR_EMAIL@gmail.com"
```

```bash
PROJECT_ID="YOUR_GCP_PROJECT_ID"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

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

Run the Vertex real-time endpoint pipeline:

```bash
gcloud builds submit --config cloudbuild.yaml
```

## GitHub Actions to Cloud Run Permissions

`.github/workflows/gcp-cloud-run-cicd.yml` uses Workload Identity Federation,
pushes the image to Artifact Registry, and deploys a warm Cloud Run endpoint.

PowerShell helper:

```powershell
.\scripts\setup-gcp-cloud-run-permissions.ps1 -ProjectId "YOUR_GCP_PROJECT_ID"
```

```bash
PROJECT_ID="YOUR_GCP_PROJECT_ID"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
REGION="us-central1"
REPO_OWNER="kalla86840"
REPO_NAME="gcpcrewai"
POOL_ID="github-pool"
PROVIDER_ID="github-provider"
DEPLOY_SA="github-actions-deployer@$PROJECT_ID.iam.gserviceaccount.com"

gcloud iam service-accounts create github-actions-deployer \
  --display-name="GitHub Actions deployer"

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

gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '${REPO_OWNER}/${REPO_NAME}'"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO_OWNER}/${REPO_NAME}"
```

Add these GitHub repository secrets in `Settings > Secrets and variables > Actions`:

```text
GCP_PROJECT_ID=YOUR_GCP_PROJECT_ID
GCP_SERVICE_ACCOUNT=github-actions-deployer@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

## Endpoint Caller Permissions

Grant Vertex callers permission to invoke online prediction:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:YOUR_EMAIL@gmail.com" \
  --role="roles/aiplatform.user"
```

For a backend service account, replace the member with:

```text
serviceAccount:BACKEND_SA@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com
```

Cloud Run is deployed with `--allow-unauthenticated` by default. Remove that
flag in the workflow if the endpoint should require IAM-authenticated callers.

## Runtime Environment

The deployed container expects:

```text
OPENAI_API_KEY
PINECONE_API_KEY
PINECONE_HOST
PINECONE_INDEX
PINECONE_NAMESPACE
OPENAI_EMBEDDING_MODEL
OPENAI_EMBEDDING_DIMENSIONS
OPENAI_GENERATION_MODEL
CREWAI_LLM_MODEL
CREWAI_VERBOSE
```

The pipeline supplies these values from `cloudbuild.yaml`, the GitHub Actions
workflow, and Secret Manager.
