param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Region = "us-central1",
    [string]$Repository = "kalla86840/gcpcrewai",
    [string]$ServiceAccountName = "github-actions-deployer",
    [string]$PoolId = "github-pool",
    [string]$ProviderId = "github-provider"
)

$ErrorActionPreference = "Stop"

$ServiceAccountEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$ProviderResource = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/providers/$ProviderId"

gcloud config set project $ProjectId

gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    iamcredentials.googleapis.com `
    secretmanager.googleapis.com

gcloud iam service-accounts describe $ServiceAccountEmail --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create $ServiceAccountName `
        --project $ProjectId `
        --display-name "GitHub Actions Cloud Run deployer"
}

$ProjectRoles = @(
    "roles/run.admin",
    "roles/artifactregistry.admin",
    "roles/secretmanager.secretAccessor",
    "roles/iam.serviceAccountUser"
)

foreach ($Role in $ProjectRoles) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$ServiceAccountEmail" `
        --role $Role
}

gcloud iam workload-identity-pools describe $PoolId --location global --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam workload-identity-pools create $PoolId `
        --project $ProjectId `
        --location global `
        --display-name "GitHub Actions"
}

gcloud iam workload-identity-pools providers describe $ProviderId `
    --workload-identity-pool $PoolId `
    --location global `
    --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam workload-identity-pools providers create-oidc $ProviderId `
        --project $ProjectId `
        --location global `
        --workload-identity-pool $PoolId `
        --display-name "GitHub provider" `
        --issuer-uri "https://token.actions.githubusercontent.com" `
        --attribute-mapping "google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
        --attribute-condition "assertion.repository == '$Repository'"
}

gcloud iam service-accounts add-iam-policy-binding $ServiceAccountEmail `
    --project $ProjectId `
    --role "roles/iam.workloadIdentityUser" `
    --member "principalSet://iam.googleapis.com/projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/attribute.repository/$Repository"

Write-Host ""
Write-Host "Add these GitHub repository secrets:"
Write-Host "GCP_PROJECT_ID=$ProjectId"
Write-Host "GCP_SERVICE_ACCOUNT=$ServiceAccountEmail"
Write-Host "GCP_WORKLOAD_IDENTITY_PROVIDER=$ProviderResource"
Write-Host ""
Write-Host "Create these Google Secret Manager secrets if they do not exist:"
Write-Host "OPENAI_API_KEY"
Write-Host "PINECONE_API_KEY"
