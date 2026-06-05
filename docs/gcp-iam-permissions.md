# Google Cloud IAM Permissions

This project deploys a custom container to a real-time Vertex AI endpoint named
`gcp-crewai`.

For the complete copy/paste setup covering APIs, Secret Manager, Cloud Build,
GitHub Actions OIDC, Cloud Run, and endpoint callers, see
`docs/deployment-requirements.md`.

## Cloud Build Deployment

The Cloud Build trigger service account needs permissions to run builds, read
the Pinecone and OpenAI secrets, push container images, upload Vertex models,
and deploy those models to an endpoint.

Grant these project roles:

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

Cloud Build expects both secrets to exist in Secret Manager:

```bash
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
```

This is an OpenAI-backed endpoint. The running container does not call Gemini
publisher models, so it does not need Gemini model prediction permissions.

## GitHub Actions Cloud Run Deployment

The GitHub Actions workflow requires:

```text
permissions:
  contents: read
  id-token: write
```

The repository must also have these Actions secrets:

```text
GCP_PROJECT_ID
GCP_SERVICE_ACCOUNT
GCP_WORKLOAD_IDENTITY_PROVIDER
```

The deploy service account needs:

```text
roles/run.admin
roles/artifactregistry.admin
roles/secretmanager.secretAccessor
roles/iam.serviceAccountUser
roles/iam.workloadIdentityUser on the service account IAM policy for the GitHub OIDC principal
```

## Endpoint Prediction

Any user or service account that calls online prediction needs:

```text
aiplatform.endpoints.predict
```

The simplest role is:

```text
roles/aiplatform.user
```

Grant it to a human tester:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:YOUR_EMAIL@gmail.com" \
  --role="roles/aiplatform.user"
```

Grant it to a webpage or backend service account:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:WEB_BACKEND_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```
