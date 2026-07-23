"""국내 상장주 스크리너 — 좌측 필터 / 우측 결과."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from detail import open_detail_for_row  # noqa: E402
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
    format_cell,
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

# 사이드바 접으면 본문이 왼쪽까지 확장 / 필터 한 줄 유지
st.markdown(
    """
    <style>
    div[data-testid="stSidebarContent"] { padding-top: 0.4rem; }
    /* 펼쳤을 때만 살짝 넓게 — 접으면 Streamlit 기본 동작으로 본문 확장 */
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 380px;
        max-width: 420px;
    }
    /* 본문: 가운데 고정 폭 해제 → 사이드바 옆부터 왼쪽 정렬 */
    div[data-testid="stAppViewContainer"] .main .block-container {
        max-width: 100% !important;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    /* 사이드바 안 가로 블록이 좁아서 줄바꿈되지 않게 */
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.35rem !important;
        align-items: center !important;
    }
    section[data-testid="stSidebar"] div[data-testid="column"] {
        min-width: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stNumberInput"] {
        min-width: 0 !important;
    }
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

# 자동완성용 라벨
_stock_labels = (
    financials.assign(
        _label=financials["corp_name"].astype(str)
        + " ("
        + financials["stock_code"].astype(str).str.zfill(6)
        + ")"
    )["_label"]
    .drop_duplicates()
    .sort_values()
    .tolist()
)

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

    search_choice = st.selectbox(
        "종목 검색 (자동완성)",
        options=["— 검색 안 함 —"] + _stock_labels,
        key="stock_search_select",
        help="입력하면 목록이 필터됩니다. 선택 시 해당 종목만 보고, 아래 필터는 무시됩니다.",
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
st.caption("재무 필터 → 해당 종목 주가 조회 → 매력도 · 종목 옆 상세보기")

view = financials.copy()
if market != "ALL" and "market" in view.columns:
    view = view[view["market"] == market].copy()

search_mode = search_choice != "— 검색 안 함 —"
fin_filters, price_filters = split_filters(filters)

if run or search_mode or "last_result" in st.session_state:
    if run or search_mode:
        if search_mode:
            # "이름 (코드)" → 코드 추출
            code = search_choice.rsplit("(", 1)[-1].rstrip(")")
            candidates = view[view["stock_code"].astype(str).str.zfill(6) == code.zfill(6)].copy()
            if candidates.empty:
                # 이름 부분 일치 fallback
                name = search_choice.rsplit(" (", 1)[0]
                candidates = view[view["corp_name"].astype(str) == name].copy()
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
        # 헤더
        metric_cols = [c for c in LIST_COLUMNS if c not in ("corp_name", "stock_code") and c in filtered.columns]
        # 종목+버튼 | 코드 | metrics...
        widths = [2.2] + [1.0] * min(len(metric_cols), 8)
        header = st.columns(widths)
        header[0].markdown("**종목**")
        for i, col in enumerate(metric_cols[:8]):
            header[i + 1].markdown(f"**{SORT_LABELS.get(col, col)}**")

        st.divider()

        # 행 + 상세보기 버튼 (체크/자동 모달 없음)
        for _, r in filtered.head(200).iterrows():
            code = str(r["stock_code"]).zfill(6)
            cols = st.columns(widths)
            with cols[0]:
                b1, b2 = st.columns([2.2, 1.0])
                b1.write(f"**{r['corp_name']}**")
                if b2.button("상세", key=f"detail_btn_{code}", use_container_width=True):
                    st.session_state["open_detail_code"] = code
            for i, col in enumerate(metric_cols[:8]):
                cols[i + 1].write(format_cell(r, col))

        if len(filtered) > 200:
            st.caption(f"상위 200개만 표시 (전체 {len(filtered)})")

        # 명시적으로 버튼 눌렀을 때만 모달
        open_code = st.session_state.pop("open_detail_code", None)
        if open_code:
            hit = filtered[filtered["stock_code"].astype(str).str.zfill(6) == open_code]
            if not hit.empty:
                open_detail_for_row(hit.iloc[0])

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
