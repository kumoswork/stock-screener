# 국내주식 스크리너

재무는 **연 1회 스냅샷**, 주가는 **앱에서 오늘 갱신** 후 필터합니다.

## 사용 (Streamlit Cloud)

1. 왼쪽 사이드바: 시장(전체/코스피/코스닥) · 카테고리 필터
2. **오늘 주가 갱신** (바닥 위치 필터용)
3. **스크리닝 실행** → 오른쪽에 결과

## 재무 스냅샷 만들기 (한국 PC, 연 1회)

```powershell
.\.venv\Scripts\python.exe scripts\build_snapshot.py --year 2025 --prev 2024
# 테스트: --limit 500 / 시장: --market KOSPI
```

생성 파일: `data/financials_snapshot.csv` → GitHub push

## 로컬 실행

```powershell
streamlit run app.py
```
