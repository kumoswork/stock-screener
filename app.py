"""국내 상장주 스크리너 — 다크 대시보드 UI."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from criteria import BADGE_SCORE, PRICE_FILTER_KEYS, score_row  # noqa: E402
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
from snapshot import (  # noqa: E402
    financials_basis_caption,
    financials_exists,
    financials_meta,
    load_financials,
)
from ui_theme import (  # noqa: E402
    inject_theme,
    render_metric_grid,
    render_result_table,
    render_score_card,
)

st.set_page_config(
    page_title="국내주식 스크리너",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_theme()

if not financials_exists():
    st.error("재무 스냅샷이 없습니다. PC에서 `python scripts/build_snapshot.py` 실행 후 push 하세요.")
    st.stop()

seed_session_from_saved(load_saved_filters())

# 이전 모드 라벨 호환
_legacy_mode = st.session_state.get("ui_mode")
if _legacy_mode == "종목 검색":
    st.session_state["ui_mode"] = "단일 점검"
elif _legacy_mode == "필터 검색":
    st.session_state["ui_mode"] = "조건 검색"


@st.cache_data
def get_financials(_version: str):
    return load_financials()


_meta = financials_meta()
financials = get_financials(_meta)
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
        status.empty()
        bar.empty()

    return cached_prices_df(codes)


def _on_ui_mode_change() -> None:
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_candidate_count", None)
    st.session_state.pop("open_detail_code", None)


def partial_scores(sc: dict) -> tuple[str, str]:
    """재무 / 주가 현위치 부분 점수(0~100 스케일 근사)."""
    badges = sc.get("badges", {})
    fin_raw = price_raw = 0
    fin_n = price_n = 0
    for key, badge in badges.items():
        if badge == "해당없음":
            continue
        pts = BADGE_SCORE.get(badge, 0)
        if key in PRICE_FILTER_KEYS:
            price_raw += pts
            price_n += 1
        else:
            fin_raw += pts
            fin_n += 1

    def to_score(raw: int, n: int) -> str:
        if n == 0:
            return "—"
        return str(int(max(0, min(100, 50 + raw * 3))))

    return to_score(fin_raw, fin_n), to_score(price_raw, price_n)


def run_pipeline(candidates: pd.DataFrame, apply_price_filters: bool, price_filters: dict) -> pd.DataFrame:
    max_fetch = 300
    if candidates.empty:
        return candidates
    fetch_df = candidates.head(max_fetch)
    if len(candidates) > max_fetch:
        st.warning(f"통과 {len(candidates)}종목 → 주가는 상위 {max_fetch}개만 조회")
    codes = fetch_df["stock_code"].astype(str).str.zfill(6).tolist()
    name_map = dict(zip(codes, fetch_df["corp_name"]))
    prices = fetch_prices_for_codes(codes, name_map)
    merged = merge_financial_and_price(fetch_df, prices)
    if apply_price_filters:
        merged = apply_range_filters(merged, price_filters)
    merged = attach_scores(merged)
    return merged.sort_values("attractiveness", ascending=False, na_position="last")


# ---------- Top: mode tabs ----------
st.markdown(
    '<div class="ks-hint">종목 하나 점검하거나, 조건으로 한꺼번에 스크리닝하세요.</div>',
    unsafe_allow_html=True,
)
ui_mode = st.radio(
    "모드",
    ["단일 점검", "조건 검색"],
    horizontal=True,
    key="ui_mode",
    label_visibility="collapsed",
    on_change=_on_ui_mode_change,
)

basis = financials_basis_caption()
filters: dict = {}
market_label = st.session_state.get("market_radio", "전체")
market_map = {"전체": "ALL", "코스피": "KOSPI", "코스닥": "KOSDAQ"}
run = False
save_clicked = False
search_choice = "종목을 선택하세요"

if ui_mode == "단일 점검":
    c_search, c_btn = st.columns([5.2, 1.0])
    with c_search:
        search_choice = st.selectbox(
            "종목",
            options=["종목을 선택하세요"] + _stock_labels,
            key="stock_search_select",
            label_visibility="collapsed",
        )
    with c_btn:
        st.write("")  # align
        run = st.button("점검", type="primary", use_container_width=True)
    market = "ALL"
else:
    m1, m2 = st.columns([1.2, 4])
    with m1:
        market_label = st.selectbox("시장", ["전체", "코스피", "코스닥"], key="market_radio")
    market = market_map[market_label]

    with st.expander("필터 조건", expanded=True):
        render_abs_filters(filters)
        render_sidebar_filters(filters)

    b1, b2, b3 = st.columns([1.0, 1.0, 4.0])
    with b1:
        run = st.button("검색", type="primary", use_container_width=True)
    with b2:
        save_clicked = st.button("필터 저장", use_container_width=True)
    if save_clicked or run:
        state = collect_filter_state(market_label, FILTER_KEYS, ABS_KEYS)
        where = persist_filters(state)
        if save_clicked:
            st.success(f"필터 저장됨 ({where})")

view = financials.copy()
if market != "ALL" and "market" in view.columns:
    view = view[view["market"] == market].copy()

search_mode = ui_mode == "단일 점검"
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
            filtered = run_pipeline(candidates, apply_price_filters=False, price_filters={})
        else:
            candidates = apply_range_filters(view, fin_filters)
            filtered = run_pipeline(candidates, apply_price_filters=True, price_filters=price_filters)

        st.session_state["last_result"] = filtered
        st.session_state["last_candidate_count"] = len(candidates)
    else:
        filtered = st.session_state["last_result"]

    if filtered.empty:
        st.info("조건에 맞는 종목이 없습니다.")
    elif search_mode:
        row = filtered.iloc[0]
        sc = score_row(row)
        fin_s, price_s = partial_scores(sc)
        name = str(row.get("corp_name", ""))
        code = str(row.get("stock_code", "")).zfill(6)
        st.markdown(
            render_score_card(
                name=name,
                code=code,
                score=int(sc["attractiveness"]),
                grade=str(sc["grade"]),
                fin_score=fin_s,
                price_score=price_s,
                caption=f"통합 매력도 · {basis}",
            ),
            unsafe_allow_html=True,
        )

        badges = sc["badges"]
        items = [
            ("현재가", format_cell(row, "current_price"), "해당없음"),
            ("영업이익률", format_cell(row, "operating_margin"), badges.get("operating_margin", "해당없음")),
            ("매출성장률", format_cell(row, "revenue_growth"), badges.get("revenue_growth", "해당없음")),
            ("매출액", format_cell(row, "revenue"), "해당없음"),
            ("ROE", format_cell(row, "roe") if "roe" in row.index else "-", badges.get("roe", "해당없음")),
            ("유동비율", format_cell(row, "current_ratio") if "current_ratio" in row.index else "-", badges.get("current_ratio", "해당없음")),
            ("부채비율", format_cell(row, "debt_ratio") if "debt_ratio" in row.index else "-", badges.get("debt_ratio", "해당없음")),
            ("저점대비", format_cell(row, "pct_from_low"), badges.get("pct_from_low", "해당없음")),
            ("바닥체류", format_cell(row, "bottom_dwell_ratio"), badges.get("bottom_dwell_ratio", "해당없음")),
            ("52주위치", format_cell(row, "range_position"), badges.get("range_position", "해당없음")),
        ]
        st.markdown(render_metric_grid(items), unsafe_allow_html=True)
        st.markdown(
            f'<div class="ks-foot">{basis} · 주가 데이터는 조회 시점 기준</div>',
            unsafe_allow_html=True,
        )

        if st.button("상세 재무 보기", key=f"detail_single_{code}"):
            open_detail_for_row(row)
    else:
        st.markdown(
            f'<div class="ks-status">스캔 {len(view)}종목 · {basis} · 조건 충족 {len(filtered)}개</div>',
            unsafe_allow_html=True,
        )
        show = filtered.head(200)
        cols = [c for c in LIST_COLUMNS if c in show.columns]
        st.markdown(
            render_result_table(show, cols, SORT_LABELS, format_cell),
            unsafe_allow_html=True,
        )
        if len(filtered) > 200:
            st.markdown(
                f'<div class="ks-foot">상위 200개만 표시 (전체 {len(filtered)})</div>',
                unsafe_allow_html=True,
            )

        detail_opts = [
            f"{r['corp_name']} ({str(r['stock_code']).zfill(6)})" for _, r in show.iterrows()
        ]
        d1, d2 = st.columns([4, 1])
        with d1:
            pick = st.selectbox("상세 볼 종목", ["—"] + detail_opts, key="detail_pick")
        with d2:
            st.write("")
            open_btn = st.button("상세", use_container_width=True)
        if open_btn and pick != "—":
            code = pick.rsplit("(", 1)[-1].rstrip(")")
            hit = filtered[filtered["stock_code"].astype(str).str.zfill(6) == code.zfill(6)]
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
        st.markdown(
            '<div class="ks-status">종목을 고른 뒤 <b>점검</b>을 누르세요.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ks-status">필터를 고른 뒤 <b>검색</b>을 누르세요.</div>',
            unsafe_allow_html=True,
        )
