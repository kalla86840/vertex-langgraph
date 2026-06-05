# GitHub Repository Permissions

The Cloud Run CI/CD workflow needs these repository settings and secrets.

## Actions Permissions

Enable GitHub Actions for the repository:

```text
Settings -> Actions -> General -> Actions permissions -> Allow all actions and reusable workflows
```

Set workflow permissions:

```text
Settings -> Actions -> General -> Workflow permissions -> Read repository contents permission
```

The workflow requests the OIDC token permission inside
`.github/workflows/gcp-cloud-run-cicd.yml`:

```yaml
permissions:
  contents: read
  id-token: write
```

## Repository Secrets

Add these under:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

```text
GCP_PROJECT_ID
GCP_SERVICE_ACCOUNT
GCP_WORKLOAD_IDENTITY_PROVIDER
```

Use Google Secret Manager for runtime API keys instead of GitHub secrets:

```text
OPENAI_API_KEY
PINECONE_API_KEY
```

## Required GCP Access

The service account in `GCP_SERVICE_ACCOUNT` needs:

```text
roles/run.admin
roles/artifactregistry.admin
roles/secretmanager.secretAccessor
roles/iam.serviceAccountUser
```

It also needs `roles/iam.workloadIdentityUser` on the service account IAM
policy for the `kalla86840/gcpcrewai` repository principal.
