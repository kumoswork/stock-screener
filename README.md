# 국내주식 스크리너

재무 지표 + 바닥권 주가 위치로 국내 상장주를 필터링합니다.

## 로컬 실행

```powershell
cd stock-screener
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

브라우저: http://localhost:8501

## Streamlit Cloud 배포

1. 이 폴더를 GitHub 저장소에 push
2. https://share.streamlit.io 접속 → GitHub 연동
3. **Main file path**: `app.py`
4. **Secrets** (Settings → Secrets):

```toml
DART_API_KEY = "발급받은_키"
```

## 사용 순서

1. DART 회사목록 불러오기
2. 재무제표 불러오기
3. 주가/바닥지표 불러오기
4. 필터 설정 → 스크리닝 실행
