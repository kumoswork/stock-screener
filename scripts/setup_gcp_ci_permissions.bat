@echo off
REM One-time: Cloud Build / Compute default SA permissions for `gcloud run deploy --source`
REM Run as project owner (your user), not the github deploy SA.

set PROJECT=stockscreener-504006
set PROJECT_NUMBER=358265577957

set COMPUTE_SA=%PROJECT_NUMBER%-compute@developer.gserviceaccount.com
set CLOUDBUILD_SA=%PROJECT_NUMBER%@cloudbuild.gserviceaccount.com

gcloud config set project %PROJECT%

echo Granting roles to %COMPUTE_SA% ...
for %%R in (
  roles/cloudbuild.builds.builder
  roles/artifactregistry.writer
  roles/storage.admin
  roles/logging.logWriter
  roles/run.admin
  roles/iam.serviceAccountUser
) do (
  gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%COMPUTE_SA%" --role=%%R
)

echo Granting roles to %CLOUDBUILD_SA% ...
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%CLOUDBUILD_SA%" --role=roles/cloudbuild.builds.builder

echo.
echo DONE. Re-run deploy-cloudrun in GitHub Actions.
