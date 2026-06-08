param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Region = "us-central1",
    [string]$Repository = "kalla86840/vertex-langgraph",
    [string]$ServiceAccountName = "github-actions-deployer",
    [string]$PoolId = "github-pool",
    [string]$ProviderId = "github-provider",
    [string]$LangGraphOutputBucket = "",
    [string]$CallerMember = ""
)

$ErrorActionPreference = "Stop"

$ServiceAccountEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$CloudBuildServiceAccount = "$ProjectNumber@cloudbuild.gserviceaccount.com"
$ProviderResource = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/providers/$ProviderId"

gcloud config set project $ProjectId

gcloud services enable `
    cloudbuild.googleapis.com `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    aiplatform.googleapis.com `
    iamcredentials.googleapis.com `
    secretmanager.googleapis.com `
    storage.googleapis.com

gcloud iam service-accounts describe $ServiceAccountEmail --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create $ServiceAccountName `
        --project $ProjectId `
        --display-name "GitHub Actions GCP LangGraph deployer"
}

$DeployRoles = @(
    "roles/run.admin",
    "roles/artifactregistry.admin",
    "roles/secretmanager.secretAccessor",
    "roles/iam.serviceAccountUser"
)

foreach ($Role in $DeployRoles) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$ServiceAccountEmail" `
        --role $Role
}

$CloudBuildRoles = @(
    "roles/cloudbuild.builds.builder",
    "roles/artifactregistry.admin",
    "roles/aiplatform.admin",
    "roles/secretmanager.secretAccessor"
)

foreach ($Role in $CloudBuildRoles) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$CloudBuildServiceAccount" `
        --role $Role
}

if ($LangGraphOutputBucket) {
    gcloud storage buckets add-iam-policy-binding "gs://$LangGraphOutputBucket" `
        --member "serviceAccount:$ServiceAccountEmail" `
        --role "roles/storage.objectCreator"

    gcloud storage buckets add-iam-policy-binding "gs://$LangGraphOutputBucket" `
        --member "serviceAccount:$CloudBuildServiceAccount" `
        --role "roles/storage.objectCreator"
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

if ($CallerMember) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member $CallerMember `
        --role "roles/aiplatform.user"
}

Write-Host ""
Write-Host "GCP LangGraph permissions configured."
Write-Host ""
Write-Host "Cloud Run deploy service account:"
Write-Host $ServiceAccountEmail
Write-Host ""
Write-Host "Cloud Build service account:"
Write-Host $CloudBuildServiceAccount
Write-Host ""
Write-Host "Add these GitHub repository secrets:"
Write-Host "GCP_PROJECT_ID=$ProjectId"
Write-Host "GCP_SERVICE_ACCOUNT=$ServiceAccountEmail"
Write-Host "GCP_WORKLOAD_IDENTITY_PROVIDER=$ProviderResource"
Write-Host ""
Write-Host "Create or update these Secret Manager secrets:"
Write-Host "OPENAI_API_KEY"
Write-Host "PINECONE_API_KEY"
