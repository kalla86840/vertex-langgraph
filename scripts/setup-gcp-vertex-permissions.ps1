param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$CallerMember = ""
)

$ErrorActionPreference = "Stop"

$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$BuildServiceAccount = "$ProjectNumber@cloudbuild.gserviceaccount.com"

gcloud config set project $ProjectId

gcloud services enable `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    aiplatform.googleapis.com `
    secretmanager.googleapis.com

$BuildRoles = @(
    "roles/cloudbuild.builds.builder",
    "roles/artifactregistry.admin",
    "roles/aiplatform.admin",
    "roles/secretmanager.secretAccessor"
)

foreach ($Role in $BuildRoles) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member "serviceAccount:$BuildServiceAccount" `
        --role $Role
}

if ($CallerMember) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member $CallerMember `
        --role "roles/aiplatform.user"
}

Write-Host ""
Write-Host "Cloud Build service account:"
Write-Host $BuildServiceAccount
Write-Host ""
Write-Host "Create these Google Secret Manager secrets if they do not exist:"
Write-Host "OPENAI_API_KEY"
Write-Host "PINECONE_API_KEY"
Write-Host ""
Write-Host "Run the Vertex real-time endpoint pipeline with:"
Write-Host "gcloud builds submit --config cloudbuild.yaml"
