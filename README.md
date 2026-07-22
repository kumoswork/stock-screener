# 국내주식 스크리너

**클라우드에서는 필터만** 합니다. 재무·주가 데이터는 PC에서 미리 만들어 `data/screener_snapshot.csv`로 올립니다.

## 왜 이렇게?

Streamlit Cloud(해외)에서는 DART/KRX 실시간 조회가 느리거나 막힙니다.  
종목마다 API를 치면 끝이 없으므로 **오프라인 스냅샷 → 온라인 필터** 구조입니다.

## Streamlit Cloud

1. `data/screener_snapshot.csv` 가 포함된 상태로 GitHub push
2. Secrets는 더 이상 필수가 아님 (스냅샷만 쓸 때)
3. 앱에서 필터 → 결과 즉시

## 로컬에서 스냅샷 만들기 (한국 PC)

```powershell
cd stock-screener
.\.venv\Scripts\activate
pip install -r requirements.txt

# 테스트 (300종목)
python scripts/build_snapshot.py --limit 300 --year 2025 --prev 2024

# 전체
python scripts/build_snapshot.py --year 2025 --prev 2024

# KOSPI만
python scripts/build_snapshot.py --market KOSPI
```

완료 후:

```powershell
git add data/screener_snapshot.csv data/screener_snapshot_meta.txt
git commit -m "Update screener snapshot"
git push
```

## 로컬 앱 실행

```powershell
streamlit run app.py
```
