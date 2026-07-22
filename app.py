"""국내 상장주 스크리너 — 미리 만든 스냅샷을 필터링합니다."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from screener import (  # noqa: E402
    FILTER_CATEGORIES,
    SORT_LABELS,
    apply_range_filters,
    format_display_df,
    render_filter_group,
    sort_dataframe,
)
from snapshot import load_snapshot, snapshot_exists, snapshot_meta  # noqa: E402

st.set_page_config(page_title="국내주식 스크리너", page_icon="📊", layout="wide")

st.title("📊 국내 상장주 스크리너")
st.caption("미리 계산된 재무·주가 스냅샷을 필터링합니다. (클라우드에서 DART 실시간 조회 없음)")

if not snapshot_exists():
    st.error(
        "스냅샷 파일이 없습니다. 로컬(한국 PC)에서 아래를 실행한 뒤 GitHub에 push 하세요.\n\n"
        "`python scripts/build_snapshot.py --limit 500`"
    )
    st.code(snapshot_meta())
    st.stop()

@st.cache_data
def get_data() -> "pd.DataFrame":
    return load_snapshot()


import pandas as pd  # noqa: E402

df = get_data()

with st.sidebar:
    st.header("데이터")
    st.markdown(f"```\n{snapshot_meta()}```")
    st.caption("데이터 갱신은 PC에서 `scripts/build_snapshot.py` 실행 후 push")

    market = st.selectbox("시장", ["ALL", "KOSPI", "KOSDAQ"])
    if market != "ALL" and "market" in df.columns:
        view = df[df["market"] == market].copy()
    else:
        view = df.copy()

    st.info(f"대상 종목: {len(view)}개")

st.subheader("필터 조건")

category_names = list(FILTER_CATEGORIES.keys()) + ["절대 금액", "정렬"]
tabs = st.tabs(category_names)
filters: dict[str, tuple[float | None, float | None]] = {}

for tab, category in zip(tabs[:-2], FILTER_CATEGORIES):
    with tab:
        st.markdown(f"**{category}** — 체크한 항목만 필터 적용")
        render_filter_group(filters, category, FILTER_CATEGORIES[category], category[:4])

with tabs[-2]:
    st.markdown("**절대 금액** — 매출액·영업이익·당기순이익")
    for key, label in [("revenue", "매출액"), ("operating_profit", "영업이익"), ("net_income", "당기순이익")]:
        if st.checkbox(label, key=f"abs_{key}"):
            unit = st.selectbox("단위", ["억원", "조원"], key=f"abs_{key}_unit")
            multiplier = 1e8 if unit == "억원" else 1e12
            c1, c2 = st.columns(2)
            with c1:
                lo = st.number_input("최소", key=f"abs_{key}_lo", value=0.0)
            with c2:
                hi = st.number_input("최대", key=f"abs_{key}_hi", value=0.0)
            filters[key] = (lo * multiplier if lo else None, hi * multiplier if hi else None)

sort_rules: list[tuple[str, bool]] = []
with tabs[-1]:
    st.markdown("정렬 기준 최대 3개 (위에서부터 우선순위)")
    sort_options = [c for c in SORT_LABELS.keys() if c in view.columns or c in ("corp_name", "stock_code")]
    for i in range(3):
        c1, c2 = st.columns([3, 1])
        with c1:
            col = st.selectbox(
                f"정렬 {i + 1}",
                [""] + sort_options,
                format_func=lambda x: "— 선택 —" if x == "" else SORT_LABELS.get(x, x),
                key=f"sort_col_{i}",
            )
        with c2:
            direction = st.selectbox("순서", ["내림차순", "오름차순"], key=f"sort_dir_{i}")
        if col:
            sort_rules.append((col, direction == "오름차순"))

if st.button("🔍 스크리닝 실행", type="primary", use_container_width=True):
    filtered = apply_range_filters(view, filters)
    filtered = sort_dataframe(filtered, sort_rules)

    st.subheader(f"결과: {len(filtered)}종목 / 전체 {len(view)}종목")

    show_cols = [
        "corp_name", "stock_code", "market",
        "cash_survival_years", "current_ratio", "quick_ratio", "debt_ratio",
        "revenue_growth", "roe", "revenue_minus_debt_growth",
        "pct_from_low", "range_position", "bottom_dwell_ratio",
        "revenue", "operating_profit", "net_income", "current_price",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]
    display = format_display_df(filtered[show_cols])
    rename_map = {k: SORT_LABELS.get(k, k) for k in display.columns if k in SORT_LABELS}
    rename_map.update({"corp_name": "종목명", "stock_code": "종목코드", "market": "시장"})
    display = display.rename(columns=rename_map)
    st.dataframe(display, use_container_width=True, hide_index=True)

    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSV 다운로드", csv, file_name="screener_result.csv", mime="text/csv")

with st.expander("지표 설명"):
    for category, items in FILTER_CATEGORIES.items():
        st.markdown(f"**{category}**")
        for _, label, help_text in items:
            if help_text:
                st.markdown(f"- {label}: {help_text}")
