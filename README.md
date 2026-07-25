# 국내주식 스크리너 (KUMO$)

재무는 **네이버(Wisereport) 연간 스냅샷**, 주가는 **주가 캐시** 기준으로 즉시 스크리닝합니다.

## 웹앱 실행 (권장)

`stock-screener` 폴더에서:

```powershell
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저: http://127.0.0.1:8000

## 온라인 배포 (Railway)

1. 이 저장소를 GitHub에 push
2. [Railway](https://railway.app) → New Project → Deploy from GitHub repo
3. `kumoswork/stock-screener` 선택 후 Deploy
4. Settings → Networking → Generate Domain

시작 명령은 `Procfile` / `railway.json`에 포함되어 있습니다.

```text
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

## 사용

1. 사이드바: 종목 검색 / 필터 검색 / 즐겨찾기
2. 필터 선택 후 **스크리닝** → 결과 · 상세
3. 즐겨찾기는 브라우저 `localStorage`에 저장됩니다

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
