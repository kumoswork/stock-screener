# 국내주식 스크리너

재무는 **네이버(Wisereport) 연간 스냅샷**, 주가는 **앱에서 결과 종목만 조회**합니다.

## 사용 (Streamlit Cloud)

1. 왼쪽 사이드바: 종목 검색 / 필터 검색
2. 필터 선택 후 **스크리닝** → 오른쪽에 결과 · 상세

## 재무 스냅샷 만들기 (한국 PC)

기본 소스는 네이버입니다. (`--source dart` 로 예전 DART 경로 가능)

```powershell
.\.venv\Scripts\python.exe scripts\build_snapshot.py --year 2025 --prev 2024
# 테스트: --limit 50 / 시장: --market KOSPI / 병렬: --workers 8
```

생성 파일: `data/financials_snapshot.csv` → GitHub push

## 로컬 실행

```powershell
streamlit run app.py
```
