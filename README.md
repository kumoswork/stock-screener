# 국내주식 스크리너 (KUMO$)

재무는 **네이버(Wisereport) 연간 스냅샷**, 주가는 **주가 캐시** 기준으로 즉시 스크리닝합니다.

## 웹앱 실행 (로컬)

`stock-screener` 폴더에서:

```powershell
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저: http://127.0.0.1:8000

## 온라인 배포 (권장: Google Cloud Run — 무료 한도)

취미용으로 **Cloud Run**을 권장합니다. 사용량이 적을 때 인스턴스 0으로 내려가서 한도 안이면 사실상 무료입니다.  
UI·API 코드는 그대로이고, 배포 대상만 Railway → Cloud Run으로 바꿉니다.

### 사전 준비 (GCP)

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성 (CRM용 Firebase/GCP 프로젝트 재사용 가능)
2. **결제 계정 연결** (무료 한도용; 초과 방지로 **Budgets 알림 $1** 권장)
3. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) 설치 후:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `GITHUB_TOKEN` | 권장 | GitHub PAT (`repo` 권한). 포트폴리오를 GitHub에 동기화해 재배포 후에도 종목 유지 |
| `GITHUB_REPO` | 선택 | 기본 `kumoswork/stock-screener` |
| `GCP_PROJECT_ID` | 선택 | 스크립트에 `-ProjectId` 대신 사용 |
| `GCP_REGION` | 선택 | 기본 `asia-northeast3` (서울) |
| `CLOUD_RUN_SERVICE` | 선택 | 기본 `kumo-screener` |

포트폴리오용 토큰: GitHub → Settings → Developer settings → Personal access tokens (classic) → `repo` 체크.

### 배포 명령

```powershell
cd stock-screener
$env:GITHUB_TOKEN = "ghp_xxxxxxxx"   # 권장
.\scripts\deploy_cloudrun.ps1 -ProjectId YOUR_PROJECT_ID
```

### 배포 후 확인 체크리스트

`main`에 push할 때마다 Cloud Run이 자동 배포됩니다.  
**최초 1회만** GitHub Secrets를 넣으면, 이후에는 토큰·배포 명령을 매번 칠 필요 없습니다.

자세한 설정: [`docs/cloudrun-github-actions.md`](docs/cloudrun-github-actions.md)

| Secret | 설명 |
|--------|------|
| `GCP_PROJECT_ID` | `stockscreener-504006` |
| `GCP_SA_KEY` | GCP 서비스 계정 JSON 키 |
| `PORTFOLIO_GITHUB_TOKEN` | GitHub PAT (`repo`) — 포트폴리오 저장용 |

### 수동 배포 (급할 때만)

1. `https://…run.app/health` → `{"status":"ok"}`
2. `https://…run.app` → UI 로드
3. 스크리닝 동작
4. 포트폴리오 `kumos` 로그인 + 즐겨찾기
5. (선택) 즐겨찾기 하나 추가 후 응답/상태에 github 동기화 확인

첫 접속만 수 초~십수 초 느리면 **콜드스타트**로 정상입니다. 재접속은 빨라야 합니다.

### Railway → Cloud Run 전환 (컷오버)

Cloud Run이 안정이면:

1. 북마크/공유 주소를 **Cloud Run URL**로 교체
2. [Railway](https://railway.app) 대시보드에서 기존 서비스 **Stop 또는 Delete** (크레딧 낭비 방지)
3. Railway Variables에 넣어 둔 `GITHUB_TOKEN`이 있다면 Cloud Run에도 동일하게 넣었는지 확인 (`deploy_cloudrun.ps1`이 배포 시 `--set-env-vars`로 설정)

불편하면 나중에 집 PC + Cloudflare 터널로 다시 옮길 수 있습니다.

## 온라인 배포 (레거시: Railway)

1. 이 저장소를 GitHub에 push
2. [Railway](https://railway.app) → Deploy from GitHub
3. Networking → Generate Domain
4. Variables: `GITHUB_TOKEN`, `GITHUB_REPO` (권장)

시작 설정은 `Procfile` / `railway.json`에 있습니다.

## 사용

1. 사이드바: 종목 검색 / 필터 검색 / 즐겨찾기
2. 필터 선택 후 **스크리닝** → 결과 · 상세
3. 즐겨찾기/포트폴리오: 이름(영문) + PIN 4자리 (서버 + 브라우저 백업)

## 재무 스냅샷 만들기 (한국 PC)

```powershell
.\.venv\Scripts\python.exe scripts\build_snapshot.py --year 2025 --prev 2024
```

생성 파일: `data/financials_snapshot.csv` → GitHub push

주가 캐시는 GitHub Actions(`daily-price-cache`) 또는:

```powershell
.\.venv\Scripts\python.exe scripts\build_price_cache.py
```

## Streamlit (레거시)

```powershell
streamlit run app.py
```
