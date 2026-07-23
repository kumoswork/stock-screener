"""국내 상장주 스크리너 — 좌측 필터 / 우측 결과."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from detail import show_detail_dialog  # noqa: E402
from filter_store import (  # noqa: E402
    collect_filter_state,
    load_saved_filters,
    persist_filters,
    seed_session_from_saved,
)
from price import fetch_price_metrics  # noqa: E402
from screener import (  # noqa: E402
    LIST_COLUMNS,
    SORT_LABELS,
    all_filter_keys,
    apply_range_filters,
    attach_scores,
    format_display_df,
    merge_financial_and_price,
    render_abs_filters,
    render_sidebar_filters,
    split_filters,
)
from snapshot import financials_exists, financials_meta, load_financials  # noqa: E402

st.set_page_config(
    page_title="국내주식 스크리너",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] { min-width: 420px !important; width: 420px !important; }
    div[data-testid="stSidebarContent"] { padding-top: 0.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

if not financials_exists():
    st.error("재무 스냅샷이 없습니다. PC에서 `python scripts/build_snapshot.py` 실행 후 push 하세요.")
    st.stop()

seed_session_from_saved(load_saved_filters())


@st.cache_data
def get_financials(_version: str):
    return load_financials()


_meta = financials_meta()
financials = get_financials(_meta)
ABS_KEYS = ["revenue", "operating_profit", "net_income"]
FILTER_KEYS = all_filter_keys()

if "price_cache" not in st.session_state:
    st.session_state["price_cache"] = {}
if "price_cache_date" not in st.session_state:
    st.session_state["price_cache_date"] = ""


def cached_prices_df(codes: list[str]) -> pd.DataFrame:
    cache = st.session_state["price_cache"]
    rows = [cache[c] for c in codes if c in cache]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_prices_for_codes(codes: list[str], name_map: dict[str, str]) -> pd.DataFrame:
    today = str(date.today())
    if st.session_state.get("price_cache_date") != today:
        st.session_state["price_cache"] = {}
        st.session_state["price_cache_date"] = today

    cache = st.session_state["price_cache"]
    missing = [c for c in codes if c not in cache]
    if missing:
        bar = st.progress(0)
        status = st.empty()

        def on_prog(cur, total, name):
            bar.progress(min(cur / max(total, 1), 1.0))
            if cur == 1 or cur % 10 == 0 or cur == total:
                status.caption(f"주가 {cur}/{total} {name}")

        with st.spinner(f"검색된 {len(missing)}종목 주가 조회 중..."):
            fresh = fetch_price_metrics(missing, name_map, progress_callback=on_prog, max_workers=8)
        if not fresh.empty:
            for _, row in fresh.iterrows():
                code = str(row["stock_code"]).zfill(6)
                cache[code] = row.to_dict()
                cache[code]["stock_code"] = code
        status.caption(f"주가 신규 {len(fresh)} / 요청 {len(missing)}")

    return cached_prices_df(codes)


# ---------- Sidebar ----------
with st.sidebar:
    st.title("필터")

    search = st.text_input(
        "종목 검색",
        key="stock_search",
        placeholder="코드 또는 종목명 (필터와 별개)",
        help="입력 시 해당 종목만 표시합니다. 사이드바 필터는 무시됩니다.",
    )

    market_label = st.radio(
        "시장",
        ["전체", "코스피", "코스닥"],
        horizontal=True,
        key="market_radio",
        label_visibility="collapsed",
    )
    market_map = {"전체": "ALL", "코스피": "KOSPI", "코스닥": "KOSDAQ"}
    market = market_map[market_label]

    st.caption(financials_meta().strip().replace("\n", " · "))
    st.caption(f"종목 {len(financials)}개 · 주가는 결과 종목만 조회")

    st.divider()
    filters: dict = {}
    render_abs_filters(filters)
    render_sidebar_filters(filters)

    c_save, c_run = st.columns(2)
    with c_save:
        save_clicked = st.button("필터 저장", use_container_width=True)
    with c_run:
        run = st.button("스크리닝", type="primary", use_container_width=True)

    if save_clicked or run:
        state = collect_filter_state(market_label, FILTER_KEYS, ABS_KEYS)
        where = persist_filters(state)
        if save_clicked:
            st.success(f"필터 저장됨 ({where})")

# ---------- Main ----------
st.title("국내 상장주 스크리너")
st.caption("재무 필터 → 해당 종목 주가 조회 → 매력도 점수 · 행 선택 시 상세")

view = financials.copy()
if market != "ALL" and "market" in view.columns:
    view = view[view["market"] == market].copy()

search_q = (search or "").strip()
search_mode = bool(search_q)

fin_filters, price_filters = split_filters(filters)

if run or search_mode or "last_result" in st.session_state:
    if run or search_mode:
        if search_mode:
            q = search_q.lower()
            codes = view["stock_code"].astype(str).str.zfill(6)
            names = view["corp_name"].astype(str)
            candidates = view[
                codes.str.contains(q, case=False, na=False)
                | names.str.lower().str.contains(q, na=False)
            ].copy()
            st.write(f"검색 결과: **{len(candidates)}**종목 (필터 미적용)")
        else:
            candidates = apply_range_filters(view, fin_filters)
            st.write(f"재무 통과: **{len(candidates)}**종목")

        MAX_PRICE_FETCH = 300
        if candidates.empty:
            filtered = candidates
        else:
            fetch_df = candidates.head(MAX_PRICE_FETCH)
            if len(candidates) > MAX_PRICE_FETCH:
                st.warning(f"통과 {len(candidates)}종목 → 주가는 상위 {MAX_PRICE_FETCH}개만 조회")
            codes = fetch_df["stock_code"].astype(str).str.zfill(6).tolist()
            name_map = dict(zip(codes, fetch_df["corp_name"]))
            prices = fetch_prices_for_codes(codes, name_map)
            merged = merge_financial_and_price(fetch_df, prices)
            if search_mode:
                filtered = merged
            else:
                filtered = apply_range_filters(merged, price_filters)
            filtered = attach_scores(filtered)
            filtered = filtered.sort_values("attractiveness", ascending=False, na_position="last")

        st.session_state["last_result"] = filtered
        st.session_state["last_candidate_count"] = len(candidates)
    else:
        filtered = st.session_state["last_result"]

    cand_n = st.session_state.get("last_candidate_count", len(filtered))
    st.subheader(f"결과 {len(filtered)}종목  /  통과·검색 {cand_n}  /  시장 {len(view)}")

    if filtered.empty:
        st.info("조건에 맞는 종목이 없습니다.")
    else:
        show_cols = [c for c in LIST_COLUMNS if c in filtered.columns]
        display = format_display_df(filtered[show_cols])
        rename = {k: SORT_LABELS.get(k, k) for k in display.columns}
        display = display.rename(columns=rename)

        event = st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=560,
            on_select="rerun",
            selection_mode="single-row",
            key="result_table",
        )

        selected_rows = []
        try:
            selected_rows = event.selection.rows  # type: ignore[attr-defined]
        except Exception:
            selected_rows = []

        if selected_rows:
            idx = selected_rows[0]
            if idx < len(filtered):
                show_detail_dialog(filtered.iloc[idx])

        # fallback selector
        options = [
            f"{r.corp_name} ({str(r.stock_code).zfill(6)}) · {int(r.attractiveness) if pd.notna(r.attractiveness) else '-'}점"
            for _, r in filtered.iterrows()
        ]
        pick = st.selectbox("상세 보기 (클릭 선택이 안 될 때)", ["—"] + options, key="detail_pick")
        if pick and pick != "—":
            i = options.index(pick)
            show_detail_dialog(filtered.iloc[i])

        st.download_button(
            "CSV 다운로드",
            filtered.drop(columns=[c for c in filtered.columns if c.startswith("_")], errors="ignore")
            .to_csv(index=False)
            .encode("utf-8-sig"),
            file_name="screener_result.csv",
            mime="text/csv",
        )
else:
    st.info("왼쪽에서 필터를 고르거나 종목을 검색한 뒤 **스크리닝**을 누르세요.")
    st.metric("재무 스냅샷 종목 수", len(view))
