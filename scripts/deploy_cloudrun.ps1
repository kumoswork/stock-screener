# Deploy stock-screener to Google Cloud Run (Seoul, scale-to-zero).
# Prerequisites: gcloud CLI installed & logged in, billing enabled on the project.
#
# Usage:
#   .\scripts\deploy_cloudrun.ps1
#   .\scripts\deploy_cloudrun.ps1 -ProjectId my-gcp-project
#   $env:GITHUB_TOKEN = "ghp_..."; .\scripts\deploy_cloudrun.ps1

param(
    [string]$ProjectId = $env:GCP_PROJECT_ID,
    [string]$Region = $(if ($env:GCP_REGION) { $env:GCP_REGION } else { "asia-northeast3" }),
    [string]$Service = $(if ($env:CLOUD_RUN_SERVICE) { $env:CLOUD_RUN_SERVICE } else { "kumo-screener" }),
    [string]$Memory = "1Gi",
    [string]$Cpu = "1",
    [int]$TimeoutSec = 300,
    [int]$Concurrency = 40,
    [string]$GithubToken = $(if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } else { $env:GH_TOKEN }),
    [string]$GithubRepo = $(if ($env:GITHUB_REPO) { $env:GITHUB_REPO } else { "kumoswork/stock-screener" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' not found. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    }
}

Require-Command "gcloud"

if (-not $ProjectId) {
    $ProjectId = (gcloud config get-value project 2>$null).Trim()
}
if (-not $ProjectId -or $ProjectId -eq "(unset)") {
    throw "Set -ProjectId or: gcloud config set project YOUR_PROJECT_ID"
}

Write-Host "=== Cloud Run deploy ===" -ForegroundColor Cyan
Write-Host "Project : $ProjectId"
Write-Host "Region  : $Region"
Write-Host "Service : $Service"
Write-Host "Source  : $Root"
Write-Host ""

gcloud config set project $ProjectId | Out-Null

Write-Host "Enabling APIs (idempotent)..." -ForegroundColor Yellow
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    --project $ProjectId

$EnvVars = "GITHUB_REPO=$GithubRepo"
if ($GithubToken) {
    $EnvVars = "GITHUB_TOKEN=$GithubToken,GITHUB_REPO=$GithubRepo"
    Write-Host "GITHUB_TOKEN: set (portfolio sync enabled)" -ForegroundColor Green
} else {
    Write-Host "GITHUB_TOKEN: not set (portfolio survives via git image + browser backup only)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Building & deploying (first run can take several minutes)..." -ForegroundColor Yellow

gcloud run deploy $Service `
    --source $Root `
    --region $Region `
    --project $ProjectId `
    --platform managed `
    --allow-unauthenticated `
    --memory $Memory `
    --cpu $Cpu `
    --timeout $TimeoutSec `
    --concurrency $Concurrency `
    --min-instances 0 `
    --max-instances 3 `
    --port 8000 `
    --set-env-vars $EnvVars `
    --quiet

$Url = gcloud run services describe $Service `
    --region $Region `
    --project $ProjectId `
    --format "value(status.url)"

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "URL     : $Url"
Write-Host "Health  : $Url/health"
Write-Host ""
Write-Host "Checklist:"
Write-Host "  1) Open $Url/health  -> status ok"
Write-Host "  2) Open $Url         -> UI loads"
Write-Host "  3) Screen + login portfolio (kumos)"
Write-Host "  4) If OK, stop/delete the Railway service to save credits"
Write-Host ""
Write-Host "Budget alert tip: GCP Console -> Billing -> Budgets ($1 recommended)"
