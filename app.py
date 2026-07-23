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
    LIST_WIDTHS,
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
from snapshot import (  # noqa: E402
    financials_basis_caption,
    financials_exists,
    financials_meta,
    load_financials,
)
from ui_theme import grade_badge_html, inject_list_detail_css  # noqa: E402

st.set_page_config(
    page_title="국내주식 스크리너",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 사이드바 레이아웃만 유지 (본문 확장 / 필터 한 줄)
st.markdown(
    """
    <style>
    div[data-testid="stSidebarContent"] { padding-top: 0.4rem; }
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 400px !important;
        max-width: 400px !important;
    }
    div[data-testid="stAppViewContainer"] .main .block-container {
        max-width: 100% !important;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
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
    /* 리스트 상세 버튼: 조회와 같은 primary 하늘색 + 작게 */
    div[data-testid="stAppViewContainer"] .main div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stAppViewContainer"] .main div[data-testid="stButton"] > button[data-testid="baseButton-primary"] {
        background: #4c8bf5 !important;
        color: #fff !important;
        border: none !important;
        padding: 0.12rem 0.45rem !important;
        font-size: 0.78rem !important;
        min-height: 1.55rem !important;
        line-height: 1.2 !important;
    }
    /* 필터검색: 저장/스크리닝 버튼 하단 고정 */
    #ks-filter-actions { display: none; }
    section[data-testid="stSidebar"][aria-expanded="true"]
      div[data-testid="stHorizontalBlock"]:has(button[kind="secondary"]):has(button[kind="primary"]),
    section[data-testid="stSidebar"][aria-expanded="true"]
      div[data-testid="element-container"]:has(#ks-filter-actions)
      + div[data-testid="element-container"],
    section[data-testid="stSidebar"][aria-expanded="true"]
      div[data-testid="stElementContainer"]:has(#ks-filter-actions)
      + div[data-testid="stElementContainer"] {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        width: 400px !important;
        max-width: 400px !important;
        z-index: 1000001 !important;
        margin: 0 !important;
        padding: 0.65rem 1rem 1rem 1rem !important;
        background: #0e1117 !important;
        border-top: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 0 -12px 28px rgba(0, 0, 0, 0.45) !important;
        box-sizing: border-box !important;
    }
    section[data-testid="stSidebar"]:has(#ks-filter-actions)
      [data-testid="stSidebarUserContent"] {
        padding-bottom: 5.5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
inject_list_detail_css()

if not financials_exists():
    st.error("재무 스냅샷이 없습니다. PC에서 `python scripts/build_snapshot.py` 실행 후 push 하세요.")
    st.stop()

seed_session_from_saved(load_saved_filters())

# 이전 모드 라벨 호환
_legacy = st.session_state.get("ui_mode")
if _legacy == "단일 점검":
    st.session_state["ui_mode"] = "종목 검색"
elif _legacy == "조건 검색":
    st.session_state["ui_mode"] = "필터 검색"


@st.cache_data
def get_financials(_version: str):
    return load_financials()


_meta = financials_meta()
try:
    from snapshot import FINANCIALS_PATH

    _csv_sig = (
        f"{FINANCIALS_PATH.stat().st_mtime_ns}:{FINANCIALS_PATH.stat().st_size}"
        if FINANCIALS_PATH.exists()
        else "none"
    )
except Exception:
    _csv_sig = "na"
_data_version = f"{_meta}|{_csv_sig}|ni-fix-3"

# 스냅샷이 바뀌면 예전 검색결과(당기순이익 0 등) 폐기
if st.session_state.get("_data_version") != _data_version:
    get_financials.clear()
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_candidate_count", None)
    st.session_state["_data_version"] = _data_version

financials = get_financials(_data_version)
ABS_KEYS = ["revenue", "operating_profit", "net_income"]
FILTER_KEYS = all_filter_keys()

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


def fetch_prices_for_codes(
    codes: list[str],
    name_map: dict[str, str],
    market_map: dict[str, str] | None = None,
) -> pd.DataFrame:
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
            status.caption(f"주가 {cur}/{total} {name}")

        with st.spinner(f"검색된 {len(missing)}종목 주가 조회 중..."):
            fresh = fetch_price_metrics(
                missing,
                name_map,
                progress_callback=on_prog,
                max_workers=12,
                markets=market_map,
                per_stock_timeout=12.0,
            )
        if not fresh.empty:
            for _, row in fresh.iterrows():
                code = str(row["stock_code"]).zfill(6)
                cache[code] = row.to_dict()
                cache[code]["stock_code"] = code
        status.empty()
        bar.empty()

    return cached_prices_df(codes)


def _on_ui_mode_change() -> None:
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_candidate_count", None)
    st.session_state.pop("open_detail_code", None)


def _on_stock_search_change() -> None:
    """자동완성에서 종목 선택(엔터 포함) 시 바로 조회."""
    choice = st.session_state.get("stock_search_select")
    if choice and choice != "종목을 선택하세요":
        st.session_state["_auto_run_stock"] = True
    else:
        st.session_state.pop("_auto_run_stock", None)


# ---------- Sidebar ----------
with st.sidebar:
    st.title("스크리너")
    ui_mode = st.radio(
        "검색 방식",
        ["종목 검색", "필터 검색"],
        horizontal=True,
        key="ui_mode",
        on_change=_on_ui_mode_change,
    )
    st.caption(financials_basis_caption())

    filters: dict = {}
    search_choice = "종목을 선택하세요"
    market_label = st.session_state.get("market_radio", "전체")
    market_map = {"전체": "ALL", "코스피": "KOSPI", "코스닥": "KOSDAQ"}
    run = False
    save_clicked = False

    if ui_mode == "종목 검색":
        search_choice = st.selectbox(
            "종목 (자동완성)",
            options=["종목을 선택하세요"] + _stock_labels,
            key="stock_search_select",
            help="입력 후 엔터로 선택하면 바로 조회됩니다.",
            on_change=_on_stock_search_change,
        )
        run = st.button("조회", type="primary", use_container_width=True)
        if st.session_state.pop("_auto_run_stock", False):
            run = True
        market = "ALL"
    else:
        market_label = st.radio(
            "시장",
            ["전체", "코스피", "코스닥"],
            horizontal=True,
            key="market_radio",
        )
        market = market_map[market_label]
        st.caption(f"종목 {len(financials)}개 · 주가는 결과만 조회")
        st.divider()
        render_abs_filters(filters)
        render_sidebar_filters(filters)
        st.markdown('<div id="ks-filter-actions"></div>', unsafe_allow_html=True)
        c_save, c_run = st.columns(2)
        with c_save:
            save_clicked = st.button("필터 저장", use_container_width=True)
        with c_run:
            run = st.button("스크리닝", type="primary", use_container_width=True)

        if save_clicked or run:
            state = collect_filter_state(market_label, FILTER_KEYS, ABS_KEYS)
            where = persist_filters(state)
            if save_clicked:
                st.toast(f"필터 저장됨 ({where})")

# ---------- Main ----------
st.title("국내 상장주 스크리너")
st.caption(financials_basis_caption())

view = financials.copy()
if market != "ALL" and "market" in view.columns:
    view = view[view["market"] == market].copy()

search_mode = ui_mode == "종목 검색"
stock_picked = search_mode and search_choice != "종목을 선택하세요"
fin_filters, price_filters = split_filters(filters)

should_query = bool(run)
if search_mode and run and not stock_picked:
    st.warning("종목을 선택하세요.")
    should_query = False

if should_query or "last_result" in st.session_state:
    if should_query:
        if search_mode:
            code = search_choice.rsplit("(", 1)[-1].rstrip(")")
            candidates = view[view["stock_code"].astype(str).str.zfill(6) == code.zfill(6)].copy()
            if candidates.empty:
                name = search_choice.rsplit(" (", 1)[0]
                candidates = view[view["corp_name"].astype(str) == name].copy()
        else:
            candidates = apply_range_filters(view, fin_filters)

        MAX_PRICE_FETCH = 300
        if candidates.empty:
            filtered = candidates
        else:
            fetch_df = candidates.head(MAX_PRICE_FETCH)
            if len(candidates) > MAX_PRICE_FETCH:
                st.warning(f"통과 {len(candidates)}종목 → 주가는 상위 {MAX_PRICE_FETCH}개만 조회")
            codes = fetch_df["stock_code"].astype(str).str.zfill(6).tolist()
            name_map = dict(zip(codes, fetch_df["corp_name"]))
            market_map = None
            if "market" in fetch_df.columns:
                market_map = dict(
                    zip(codes, fetch_df["market"].astype(str).fillna("").tolist())
                )
            prices = fetch_prices_for_codes(codes, name_map, market_map)
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

    if filtered.empty:
        st.info("조건에 맞는 종목이 없습니다.")
    else:
        show = filtered.head(200)
        st.caption(
            f"조건 충족 {len(filtered)}개"
            + (" · 상위 200개 표시" if len(filtered) > 200 else "")
        )

        display_cols = [c for c in LIST_COLUMNS if c in show.columns]
        widths = list(LIST_WIDTHS[: len(display_cols)])
        while len(widths) < len(display_cols):
            widths.append(1.0)
        # 종목명+상세 버튼 공간
        if display_cols and display_cols[0] == "corp_name":
            widths[0] = 2.35

        header = st.columns(widths)
        for i, col in enumerate(display_cols):
            header[i].markdown(f"**{SORT_LABELS.get(col, col)}**")

        st.markdown(
            "<hr style='margin:0.3rem 0 0.45rem 0; border:none; border-top:1px solid #c8c8c8;'>",
            unsafe_allow_html=True,
        )

        for _, r in show.iterrows():
            code = str(r["stock_code"]).zfill(6)
            row_cols = st.columns(widths)
            for i, col in enumerate(display_cols):
                if col == "corp_name":
                    with row_cols[i]:
                        n1, n2 = st.columns([3.0, 1.05])
                        n1.markdown(f"**{r['corp_name']}**")
                        if n2.button("상세", type="primary", key=f"detail_btn_{code}"):
                            st.session_state["open_detail_code"] = code
                elif col == "stock_code":
                    row_cols[i].write(code)
                elif col == "market":
                    m = r.get("market", "")
                    label = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(
                        str(m), str(m) if pd.notna(m) else "-"
                    )
                    row_cols[i].write(label)
                elif col == "grade":
                    row_cols[i].markdown(
                        grade_badge_html(str(r.get("grade", ""))),
                        unsafe_allow_html=True,
                    )
                else:
                    row_cols[i].write(format_cell(r, col))

            st.markdown(
                "<hr style='margin:0.15rem 0; border:none; border-top:1px solid #e6e6e6;'>",
                unsafe_allow_html=True,
            )

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
    if search_mode:
        st.info("왼쪽에서 종목을 선택하세요. (엔터로 선택하면 바로 조회됩니다)")
    else:
        st.info("왼쪽에서 필터를 고른 뒤 **스크리닝**을 누르세요.")
