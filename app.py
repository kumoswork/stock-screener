"""국내 상장주 스크리너 — 좌측 필터 / 우측 결과."""

from __future__ import annotations

import base64
import sys
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from filter_store import (  # noqa: E402
    backup_filters_from_session,
    collect_filter_state,
    load_saved_filters,
    persist_filters,
    restore_filters_to_session,
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
from tv import tradingview_chart_url  # noqa: E402
from ui_theme import grade_badge_html, inject_list_detail_css  # noqa: E402
from detail import open_detail_for_row  # noqa: E402

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
    div[data-testid="stSidebarContent"] { padding-top: 0 !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
      padding-top: 0.15rem !important;
    }
    #ks-sidebar-logo {
      margin-top: -40px !important;
      margin-bottom: 0.55rem !important;
    }
    /* 사이드바 토글: 옷택(close/open) */
    [data-testid="stSidebarCollapseButton"] button,
    button[data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"] button,
    [data-testid="stSidebarCollapsedControl"] button {
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      position: relative !important;
      min-width: 0 !important;
      min-height: 0 !important;
      width: auto !important;
      height: auto !important;
      padding: 0.15rem !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
    }
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
    button[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
    [data-testid="collapsedControl"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"] {
      font-size: 0 !important;
      line-height: 0 !important;
      width: 0 !important;
      height: 0 !important;
      overflow: hidden !important;
      opacity: 0 !important;
      color: transparent !important;
    }
    [data-testid="stSidebarCollapseButton"] button::after {
      content: "close";
      display: inline-block !important;
      box-sizing: border-box !important;
      background: #ffd400 !important;
      background-image: radial-gradient(circle at 8px 50%, #0e1117 3.2px, transparent 3.5px) !important;
      color: #1a1a1a !important;
      font-size: 0.72rem !important;
      font-weight: 800 !important;
      letter-spacing: 0.04em !important;
      line-height: 1 !important;
      text-transform: lowercase !important;
      padding: 0.48rem 0.62rem 0.48rem 1.05rem !important;
      border-radius: 3px 8px 8px 3px !important;
      box-shadow: 0 1px 4px rgba(0,0,0,0.35) !important;
      border: 1px solid #e6be00 !important;
    }
    button[data-testid="stExpandSidebarButton"]::after,
    [data-testid="collapsedControl"] button::after,
    [data-testid="stSidebarCollapsedControl"] button::after {
      content: "open";
      display: inline-block !important;
      box-sizing: border-box !important;
      background: #ffd400 !important;
      background-image: radial-gradient(circle at 8px 50%, #0e1117 3.2px, transparent 3.5px) !important;
      color: #1a1a1a !important;
      font-size: 0.78rem !important;
      font-weight: 800 !important;
      letter-spacing: 0.04em !important;
      line-height: 1 !important;
      text-transform: lowercase !important;
      padding: 0.58rem 0.72rem 0.58rem 1.12rem !important;
      border-radius: 3px 8px 8px 3px !important;
      box-shadow: 0 1px 4px rgba(0,0,0,0.35) !important;
      border: 1px solid #e6be00 !important;
    }
    /* 닫힌 뒤 펼치기 택이 헤더에 가려지지 않게 */
    button[data-testid="stExpandSidebarButton"],
    [data-testid="stSidebarCollapsedControl"] {
      z-index: 1000002 !important;
      position: relative !important;
    }
    a.ks-tv-link {
      color: inherit !important;
      text-decoration: none !important;
      border-bottom: 1px dashed #7aa2ff;
    }
    a.ks-tv-link:hover {
      color: #9ec1ff !important;
      border-bottom-color: #9ec1ff;
    }
    a.ks-tv-chip {
      display: inline-block;
      margin-left: 0.45rem;
      padding: 0.18rem 0.55rem;
      border-radius: 999px;
      background: #243049;
      border: 1px solid #3b4a66;
      color: #c5d4f5 !important;
      font-size: 0.78rem;
      font-weight: 700;
      text-decoration: none !important;
      vertical-align: middle;
    }
    a.ks-tv-chip:hover {
      background: #2d3c5c;
      color: #fff !important;
    }
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 380px !important;
        max-width: 380px !important;
    }
    div[data-testid="stAppViewContainer"] .main .block-container {
        max-width: 100% !important;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.3rem !important;
        align-items: center !important;
    }
    section[data-testid="stSidebar"] div[data-testid="column"] {
        min-width: 0 !important;
        overflow: visible !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stNumberInput"] {
        min-width: 0 !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stNumberInput"] input {
        padding-left: 0.35rem !important;
        padding-right: 0.35rem !important;
        font-size: 0.9rem !important;
    }
    /* +/- 스테퍼 폭 줄이기 */
    section[data-testid="stSidebar"] div[data-testid="stNumberInput"] button {
        min-width: 1.6rem !important;
        width: 1.6rem !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] {
        min-width: 0 !important;
    }
    section[data-testid="stSidebar"] .ks-unit-suffix {
        color: #b0b6c0 !important;
        font-size: 0.78rem !important;
        white-space: nowrap !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        padding-top: 0.35rem !important;
    }
    /* 필터 체크박스 라벨 한 줄 유지 */
    section[data-testid="stSidebar"] label p,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] .stCheckbox label span {
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      line-height: 1.25 !important;
    }
    /* 리스트 상세 버튼 */
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
    /* 결과 리스트: 헤더·값 세로/가로 정렬 */
    div[data-testid="stAppViewContainer"] .main div[data-testid="stHorizontalBlock"] {
      align-items: center !important;
      gap: 0.35rem !important;
    }
    div[data-testid="stAppViewContainer"] .main .ks-th,
    div[data-testid="stAppViewContainer"] .main .ks-td {
      margin: 0 !important;
      line-height: 1.35 !important;
      font-size: 0.92rem !important;
    }
    div[data-testid="stAppViewContainer"] .main .ks-th {
      font-weight: 700 !important;
      color: inherit !important;
    }
    /* 결과 리스트 헤더 고정 (HTML 바) */
    .ks-sticky-head-bar {
      position: sticky !important;
      top: 0 !important;
      z-index: 1000 !important;
      display: grid !important;
      gap: 0.35rem !important;
      align-items: center !important;
      background: #0e1117 !important;
      padding: 0.45rem 0.15rem 0.4rem 0.15rem !important;
      margin: 0 0 0.35rem 0 !important;
      border-bottom: 1px solid #c8c8c8 !important;
      box-shadow: 0 3px 10px rgba(0, 0, 0, 0.35) !important;
    }
    .ks-sticky-head-bar .ks-th {
      margin: 0 !important;
      line-height: 1.35 !important;
      font-size: 0.92rem !important;
      font-weight: 700 !important;
      color: #e8eaed !important;
      background: transparent !important;
    }
    [data-testid="stElementContainer"]:has(.ks-sticky-head-bar),
    [data-testid="element-container"]:has(.ks-sticky-head-bar) {
      position: sticky !important;
      top: 0 !important;
      z-index: 1000 !important;
      background: #0e1117 !important;
    }
    div[data-testid="stAppViewContainer"] .main .ks-align-left {
      text-align: left !important;
    }
    div[data-testid="stAppViewContainer"] .main .ks-align-center {
      text-align: center !important;
    }
    div[data-testid="stAppViewContainer"] .main .ks-align-right {
      text-align: right !important;
    }
    /* 모바일 */
    @media (max-width: 768px) {
      section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
      }
      #ks-sidebar-logo {
        margin-top: -8px !important;
      }
      #ks-sidebar-logo img {
        width: min(200px, 70vw) !important;
      }
      div[data-testid="stAppViewContainer"] .main .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-top: 1rem !important;
      }
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
_data_version = f"{_meta}|{_csv_sig}|sticky-head-2"

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
    # 필터 위젯이 사라지기 전에 백업 (Streamlit이 미렌더 위젯 키를 삭제함)
    backup_filters_from_session(FILTER_KEYS, ABS_KEYS)
    if st.session_state.get("ui_mode") == "필터 검색":
        st.session_state["_need_filter_restore"] = True
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
_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "kumo_logo.png"
with st.sidebar:
    if _LOGO_PATH.exists():
        _logo_b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
        st.markdown(
            f'<div id="ks-sidebar-logo" style="display:flex;justify-content:center;'
            f'align-items:center;margin-bottom:0.55rem;">'
            f'<img src="data:image/png;base64,{_logo_b64}" alt="KUMO$" '
            f'width="200" style="width:200px;height:auto;border-radius:4px;" />'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.title("스크리너")
    ui_mode = st.radio(
        "검색 방식",
        ["종목 검색", "필터 검색"],
        horizontal=True,
        key="ui_mode",
        on_change=_on_ui_mode_change,
        label_visibility="collapsed",
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
        # 종목검색 → 필터검색 복귀 시에만 위젯 키 복원 (매 렌더 복원 시 입력 덮어씀)
        if st.session_state.pop("_need_filter_restore", False):
            restore_filters_to_session(FILTER_KEYS, ABS_KEYS)
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
        # 현재 필터를 세션 백업에 유지
        backup_filters_from_session(FILTER_KEYS, ABS_KEYS)
        st.divider()
        c_save, c_run = st.columns(2)
        with c_save:
            save_clicked = st.button("필터 저장", use_container_width=True)
        with c_run:
            run = st.button("스크리닝", type="primary", use_container_width=True)

        if save_clicked or run:
            state = collect_filter_state(market_label, FILTER_KEYS, ABS_KEYS)
            st.session_state["_filter_backup"] = state
            where = persist_filters(state)
            if save_clicked:
                st.toast(f"필터 저장됨 ({where})")

# 모바일: 조회/스크리닝 후 사이드바 자동 닫기
if run:
    components.html(
        """
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  if (win.innerWidth > 768) return;
  function collapse() {
    const btn =
      doc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
      doc.querySelector('[data-testid="stSidebarCollapseButton"]');
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  }
  setTimeout(collapse, 80);
  setTimeout(collapse, 320);
  setTimeout(collapse, 700);
})();
</script>
        """,
        height=0,
        width=0,
    )

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
        if display_cols and display_cols[0] == "corp_name":
            widths[0] = 2.35

        def _align(col: str) -> str:
            return "left" if col == "corp_name" else "center"

        def _head(col: str) -> str:
            label = SORT_LABELS.get(col, col)
            return f'<p class="ks-th ks-align-{_align(col)}">{label}</p>'

        def _cell(text: str, col: str) -> str:
            return f'<p class="ks-td ks-align-{_align(col)}">{text}</p>'

        def _market_label(row) -> str:
            m = row.get("market", "")
            return {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(
                str(m), str(m) if pd.notna(m) else "-"
            )

        # ---------- 데스크톱: 다열 리스트 ----------
        with st.container():
            st.markdown(
                '<div class="ks-desktop-list-root" aria-hidden="true"></div>',
                unsafe_allow_html=True,
            )
            # Streamlit columns 헤더는 sticky가 잘 깨져서 HTML 그리드로 고정
            head_cells = []
            for col in display_cols:
                label = SORT_LABELS.get(col, col)
                head_cells.append(
                    f'<div class="ks-th ks-align-{_align(col)}">{escape(label)}</div>'
                )
            grid_cols = " ".join(f"{w}fr" for w in widths)
            st.markdown(
                f'<div class="ks-sticky-head-bar" style="grid-template-columns:{grid_cols};">'
                + "".join(head_cells)
                + "</div>",
                unsafe_allow_html=True,
            )

            for _, r in show.iterrows():
                code = str(r["stock_code"]).zfill(6)
                row_cols = st.columns(widths, vertical_alignment="center")
                for i, col in enumerate(display_cols):
                    if col == "corp_name":
                        with row_cols[i]:
                            n1, n2 = st.columns([3.0, 1.05], vertical_alignment="center")
                            tv = escape(tradingview_chart_url(code))
                            name = escape(str(r["corp_name"]))
                            n1.markdown(
                                _cell(
                                    f'<a class="ks-tv-link" href="{tv}" target="_blank" '
                                    f'rel="noopener noreferrer"><b>{name}</b></a>',
                                    col,
                                ),
                                unsafe_allow_html=True,
                            )
                            if n2.button("상세", type="primary", key=f"detail_btn_{code}"):
                                st.session_state["open_detail_code"] = code
                    elif col == "stock_code":
                        row_cols[i].markdown(_cell(code, col), unsafe_allow_html=True)
                    elif col == "market":
                        row_cols[i].markdown(
                            _cell(_market_label(r), col), unsafe_allow_html=True
                        )
                    elif col == "grade":
                        row_cols[i].markdown(
                            f'<div class="ks-align-center">{grade_badge_html(str(r.get("grade", "")))}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        row_cols[i].markdown(
                            _cell(escape(str(format_cell(r, col))), col),
                            unsafe_allow_html=True,
                        )

                st.markdown(
                    "<hr style='margin:0.15rem 0; border:none; border-top:1px solid #e6e6e6;'>",
                    unsafe_allow_html=True,
                )

        # ---------- 모바일: 종목 카드 ----------
        with st.container():
            st.markdown(
                '<div class="ks-mobile-list-root" aria-hidden="true"></div>',
                unsafe_allow_html=True,
            )
            for _, r in show.iterrows():
                code = str(r["stock_code"]).zfill(6)
                market_label = _market_label(r)
                score = r.get("attractiveness", "")
                score_txt = (
                    f"{int(score)}점"
                    if pd.notna(score) and str(score) != ""
                    else "—"
                )
                grade_html = grade_badge_html(str(r.get("grade", "")))
                price_txt = escape(format_cell(r, "current_price"))
                op_txt = escape(format_cell(r, "operating_margin"))
                rev_txt = escape(format_cell(r, "revenue_growth"))
                name = escape(str(r.get("corp_name", "") or ""))
                tv = escape(tradingview_chart_url(code))

                with st.container(border=True):
                    head_l, head_r = st.columns([4.2, 1.1], vertical_alignment="center")
                    with head_l:
                        st.markdown(
                            f'<div class="ks-mcard">'
                            f'<div class="ks-mcard-name">'
                            f'<a class="ks-tv-link" href="{tv}" target="_blank" '
                            f'rel="noopener noreferrer">{name}</a></div>'
                            f'<div class="ks-mcard-meta">{escape(code)} · {escape(market_label)} · '
                            f"{escape(score_txt)} {grade_html}</div>"
                            f'<div class="ks-mcard-metrics">'
                            f'<div class="cell"><span class="lab">현재가</span>'
                            f'<span class="val">{price_txt}</span></div>'
                            f'<div class="cell"><span class="lab">영업이익률</span>'
                            f'<span class="val">{op_txt}</span></div>'
                            f'<div class="cell"><span class="lab">매출성장</span>'
                            f'<span class="val">{rev_txt}</span></div>'
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                    with head_r:
                        if st.button(
                            "상세",
                            type="primary",
                            key=f"detail_btn_m_{code}",
                            use_container_width=True,
                        ):
                            st.session_state["open_detail_code"] = code

        # PC/모바일 목록 전환 + 데스크톱 헤더 sticky 보강
        components.html(
            """
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  let timer = null;

  function pinStickyBars() {
    doc.querySelectorAll('.ks-sticky-head-bar').forEach(function (bar) {
      const wrap =
        bar.closest('[data-testid="stElementContainer"]') ||
        bar.closest('[data-testid="element-container"]') ||
        bar.parentElement;
      if (wrap) {
        wrap.style.position = 'sticky';
        wrap.style.top = '0px';
        wrap.style.zIndex = '1000';
        wrap.style.background = '#0e1117';
      }
      bar.style.position = 'sticky';
      bar.style.top = '0px';
      bar.style.zIndex = '1001';
      bar.style.background = '#0e1117';

      let p = (wrap || bar).parentElement;
      let guard = 0;
      while (p && guard < 12) {
        const cs = win.getComputedStyle(p);
        if (['hidden', 'clip'].indexOf(cs.overflow) >= 0 ||
            ['hidden', 'clip'].indexOf(cs.overflowY) >= 0) {
          p.style.overflow = 'visible';
          p.style.overflowY = 'visible';
        }
        if (p.getAttribute && p.getAttribute('data-testid') === 'stAppViewContainer') break;
        p = p.parentElement;
        guard += 1;
      }
    });
  }

  function sync() {
    const mobile = win.innerWidth <= 768;
    doc.querySelectorAll('.ks-desktop-list-root').forEach(function (el) {
      const block = el.closest('[data-testid="stVerticalBlock"]');
      if (block) block.style.display = mobile ? 'none' : '';
    });
    doc.querySelectorAll('.ks-mobile-list-root').forEach(function (el) {
      const block = el.closest('[data-testid="stVerticalBlock"]');
      if (block) block.style.display = mobile ? '' : 'none';
    });
    if (!mobile) pinStickyBars();
  }
  function schedule() {
    if (timer) win.clearTimeout(timer);
    timer = win.setTimeout(sync, 50);
  }
  sync();
  win.addEventListener('resize', schedule);
  new win.MutationObserver(schedule).observe(doc.body, { childList: true, subtree: true });
})();
</script>
            """,
            height=0,
            width=0,
        )

        open_code = st.session_state.pop("open_detail_code", None)
        if open_code:
            hit = filtered[filtered["stock_code"].astype(str).str.zfill(6) == open_code]
            if not hit.empty:
                open_detail_for_row(hit.iloc[0])

else:
    if search_mode:
        st.info("왼쪽에서 종목을 선택하세요. (엔터로 선택하면 바로 조회됩니다)")
    else:
        st.info("왼쪽에서 필터를 고른 뒤 **스크리닝**을 누르세요.")
