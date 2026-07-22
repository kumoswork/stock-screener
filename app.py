"""국내 상장주 스크리너 — 좌측 필터 / 우측 결과."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from price import fetch_price_metrics  # noqa: E402
from screener import (  # noqa: E402
    SORT_LABELS,
    apply_range_filters,
    format_display_df,
    merge_financial_and_price,
    render_sidebar_filters,
    sort_dataframe,
)
from snapshot import financials_exists, financials_meta, load_financials  # noqa: E402

st.set_page_config(page_title="국내주식 스크리너", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] { width: 340px !important; }
    div[data-testid="stSidebarContent"] { padding-top: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

if not financials_exists():
    st.error("재무 스냅샷이 없습니다. PC에서 `python scripts/build_snapshot.py` 실행 후 push 하세요.")
    st.stop()


@st.cache_data
def get_financials():
    return load_financials()


financials = get_financials()

# ---------- Sidebar ----------
with st.sidebar:
    st.title("필터")

    market_label = st.radio(
        "시장",
        ["전체", "코스피", "코스닥"],
        horizontal=True,
        label_visibility="collapsed",
    )
    market_map = {"전체": "ALL", "코스피": "KOSPI", "코스닥": "KOSDAQ"}
    market = market_map[market_label]

    st.caption(financials_meta().strip().replace("\n", " · "))

    if st.button("오늘 주가 갱신", use_container_width=True, type="secondary"):
        subset = financials
        if market != "ALL" and "market" in subset.columns:
            subset = subset[subset["market"] == market]
        codes = subset["stock_code"].astype(str).str.zfill(6).tolist()
        name_map = dict(zip(subset["stock_code"].astype(str).str.zfill(6), subset["corp_name"]))
        bar = st.progress(0)
        status = st.empty()

        def on_prog(cur, total, name):
            bar.progress(min(cur / max(total, 1), 1.0))
            if cur == 1 or cur % 20 == 0 or cur == total:
                status.caption(f"주가 {cur}/{total} {name}")

        with st.spinner("오늘 주가·바닥지표 계산 중..."):
            prices = fetch_price_metrics(codes, name_map, progress_callback=on_prog, max_workers=6)
        st.session_state["prices"] = prices
        st.session_state["prices_date"] = str(date.today())
        st.session_state["prices_market"] = market
        status.caption(f"주가 {len(prices)}종목 갱신 완료")
        st.success(f"{len(prices)}종목 주가 반영")

    if "prices" in st.session_state:
        st.caption(
            f"주가: {st.session_state.get('prices_date', '-')} "
            f"({len(st.session_state['prices'])}종목)"
        )
    else:
        st.caption("주가 미갱신 — 재무 필터만 가능 / 바닥위치는 갱신 후")

    st.divider()
    filters: dict = {}
    sort_rules = render_sidebar_filters(filters)

    run = st.button("스크리닝 실행", type="primary", use_container_width=True)

# ---------- Main (results) ----------
st.title("국내 상장주 스크리너")
st.caption("재무는 연간 스냅샷 · 주가만 오늘 갱신")

view = financials.copy()
if market != "ALL" and "market" in view.columns:
    view = view[view["market"] == market].copy()

prices = st.session_state.get("prices")
merged = merge_financial_and_price(view, prices if prices is not None else None)

if run or "last_result" in st.session_state:
    if run:
        filtered = apply_range_filters(merged, filters)
        filtered = sort_dataframe(filtered, sort_rules)
        st.session_state["last_result"] = filtered
    else:
        filtered = st.session_state["last_result"]

    st.subheader(f"결과 {len(filtered)}종목  /  대상 {len(merged)}종목")

    show_cols = [
        "corp_name", "stock_code", "market",
        "current_price", "pct_from_low", "range_position", "bottom_dwell_ratio",
        "current_ratio", "quick_ratio", "debt_ratio",
        "revenue_growth", "roe", "roa",
        "revenue_minus_debt_growth",
        "revenue", "operating_profit", "net_income",
    ]
    show_cols = [c for c in show_cols if c in filtered.columns]
    display = format_display_df(filtered[show_cols])
    rename = {k: SORT_LABELS.get(k, k) for k in display.columns}
    rename.update({"corp_name": "종목명", "stock_code": "코드", "market": "시장"})
    st.dataframe(display.rename(columns=rename), use_container_width=True, hide_index=True, height=560)

    st.download_button(
        "CSV 다운로드",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="screener_result.csv",
        mime="text/csv",
    )
else:
    st.info("왼쪽에서 필터를 고른 뒤 **스크리닝 실행**을 누르세요. 바닥 위치 필터를 쓰려면 먼저 **오늘 주가 갱신**을 하세요.")
    st.metric("재무 스냅샷 종목 수", len(view))
