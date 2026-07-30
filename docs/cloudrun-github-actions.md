# GitHub Actions → Cloud Run 자동 배포 (최초 1회 설정)

`main` 브랜치에 push하면 Cloud Run이 자동 배포됩니다.  
로컬에서 `deploy_cloudrun.ps1`을 매번 돌릴 필요 없습니다.

## 1. GCP 서비스 계정 만들기

PowerShell/CMD에서 (프로젝트 ID는 본인 것으로):

```cmd
set PROJECT=stockscreener-504006
set SA=github-cloudrun-deploy
set SA_EMAIL=%SA%@%PROJECT%.iam.gserviceaccount.com

gcloud config set project %PROJECT%

gcloud iam service-accounts create %SA% --display-name="GitHub Actions Cloud Run deploy"

gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/run.admin"
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/cloudbuild.builds.builder"
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/artifactregistry.admin"
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:%SA_EMAIL%" --role="roles/serviceusage.serviceUsageConsumer"

gcloud iam service-accounts keys create github-sa-key.json --iam-account=%SA_EMAIL%
```

`github-sa-key.json` 파일이 생깁니다. **GitHub에 올리지 마세요.**

## 2. GitHub Secrets 등록

저장소: https://github.com/kumoswork/stock-screener/settings/secrets/actions

| Secret 이름 | 값 |
|-------------|-----|
| `GCP_PROJECT_ID` | `stockscreener-504006` |
| `GCP_SA_KEY` | `github-sa-key.json` **파일 전체 내용** (복사·붙여넣기) |
| `PORTFOLIO_GITHUB_TOKEN` | GitHub PAT (`repo` 권한). 포트폴리오 영구저장용 |

**`GCP_SA_KEY` 주의:** 메모장으로 `github-sa-key.json`을 열어 `{` 로 시작하는 **전체 JSON**을 복사하세요.  
파일 경로(`C:\...`)나 일부만 넣으면 `credentials_json` 오류가 납니다.

Secrets를 넣기 **전에** 돌아간 워크플로는 실패합니다. Secrets 저장 후 **Re-run all jobs** 하세요.

PAT 만들기: https://github.com/settings/tokens → Generate new token (classic) → `repo` 체크

`PORTFOLIO_GITHUB_TOKEN`은 Cloud Run 서버에 `GITHUB_TOKEN`으로 들어가서, 재배포 후에도 즐겨찾기가 GitHub에 저장됩니다.  
**한 번만 넣으면** 이후 자동 배포마다 같이 적용됩니다.

## 3. 확인

1. `main`에 아무 커밋 push (또는 Actions 탭에서 `deploy-cloudrun` → Run workflow)
2. https://github.com/kumoswork/stock-screener/actions 에서 초록 체크
3. 로그 맨 아래 `Deployed: https://...run.app` 주소 확인

### 배포가 `PERMISSION_DENIED` / `default service account` 로 실패할 때

로컬에서 **한 번만** 실행 (프로젝트 소유자 계정):

```cmd
cd stock-screener
scripts\setup_gcp_ci_permissions.bat
```

그다음 Actions → **Re-run all jobs**.

## 4. 로컬 수동 배포 (선택)

Secrets 설정 전이거나 급할 때만:

```powershell
.\scripts\deploy_cloudrun.ps1 -ProjectId stockscreener-504006
```

## 보안

- `github-sa-key.json`은 PC에 두지 말고 삭제해도 됩니다 (Secrets에 이미 있음)
- PAT 유출 시 GitHub에서 해당 토큰 revoke 후 Secrets만 새 값으로 교체
