# AWS CodePipeline to GCP Vertex AI

This CI/CD path uses AWS CodePipeline as the orchestrator and keeps real-time
inference on Vertex AI. A GitHub push triggers CodePipeline, CodeBuild runs the
tests, builds the Docker image, pushes it to Google Artifact Registry, uploads a
Vertex model, and creates or updates the Vertex endpoint.

The endpoint is hosted on Vertex AI, but model inference inside the container
uses OpenAI for embeddings and answer generation.

## 1. Create the AWS GitHub connection

In AWS Developer Tools, create a CodeStar connection to GitHub and authorize:

```text
kalla86840/vertex-mcp-ops
```

Copy the connection ARN.

## 2. Store secrets in AWS Systems Manager Parameter Store

Create SecureString parameters:

```powershell
aws ssm put-parameter --name "/vertex-mcp-ops/gcp-service-account-key-json" --type SecureString --value "<full GCP service account JSON>" --overwrite
aws ssm put-parameter --name "/vertex-mcp-ops/pinecone-api-key" --type SecureString --value "<pinecone api key>" --overwrite
aws ssm put-parameter --name "/vertex-mcp-ops/openai-api-key" --type SecureString --value "<openai api key>" --overwrite
```

The GCP service account needs these permissions in the target GCP project:

- Artifact Registry Administrator, or enough access to create/push Docker repos
- Vertex AI Administrator, or enough access to upload models and deploy endpoints
- Service Account User if your Vertex deployment requires attaching a runtime service account

The default Vertex endpoint and image names are MCP-specific:

```text
vertex-pinecone-mcp
vertex-pinecone-mcp-model
```

## 3. Deploy the AWS pipeline stack

```powershell
aws cloudformation deploy `
  --template-file aws-codepipeline-vertex.yml `
  --stack-name vertex-mcp-ops-cicd `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    CodeStarConnectionArn="<your codestar connection arn>" `
    GcpProjectId="<your gcp project id>" `
    GitHubFullRepositoryId="kalla86840/vertex-mcp-ops" `
    GitHubBranch="main"
```

If your GitHub default branch is `master`, change `GitHubBranch`.

## 4. Push the repo

The repository should include:

- `Dockerfile`
- `requirements.txt`
- `app/`
- `tests/`
- `buildspec-aws-codepipeline.yml`
- `aws-codepipeline-vertex.yml`

After a push, CodePipeline creates a real-time Vertex endpoint with `/health`
and `/predict` wired to the FastAPI app.

## 5. Call the endpoint

After the deployment succeeds, CodeBuild publishes `vertex-deployment.env` as an
artifact with `ENDPOINT_ID`.

Use Vertex online prediction:

```bash
gcloud ai endpoints predict ENDPOINT_ID \
  --region=us-central1 \
  --json-request=request.json
```

Example `request.json`:

```json
{
  "instances": [
    {
      "mode": "rag",
      "question": "What did Edgio discuss in Q3 2023?",
      "top_k": 5,
      "namespace": "news"
    }
  ]
}
```
