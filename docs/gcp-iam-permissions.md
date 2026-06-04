# Google Cloud IAM Permissions

This project deploys a custom container to a real-time Vertex AI endpoint named
`vertex-pinecone-mcp`.

## Cloud Build Deployment

The Cloud Build trigger service account needs permissions to run builds, read
the Pinecone and OpenAI secrets, push container images, upload Vertex models,
and deploy those models to an endpoint.

For the current project, the trigger service account is:

```text
683447325858-compute@developer.gserviceaccount.com
```

Grant these project roles:

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

Cloud Build expects both secrets to exist in Secret Manager:

```bash
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create OPENAI_API_KEY --data-file=-
```

This is an OpenAI-backed endpoint. The running container does not call Gemini
publisher models, so it does not need Gemini model prediction permissions.

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
