"""국내 상장주 재무 + 바닥 위치 스크리너."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
import os
from requests.exceptions import ConnectTimeout, RequestException

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from dart_api import DartClient, count_listed_corps, load_listed_corps  # noqa: E402
from metrics import load_financial_metrics  # noqa: E402
from price import fetch_price_metrics, load_price_metrics, save_price_metrics  # noqa: E402
from screener import (  # noqa: E402
    FILTER_CATEGORIES,
    SORT_LABELS,
    apply_range_filters,
    format_display_df,
    merge_financial_and_price,
    render_filter_group,
    sort_dataframe,
)

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(page_title="국내주식 스크리너", page_icon="📊", layout="wide")


def get_api_key() -> str:
    try:
        return st.secrets["DART_API_KEY"]
    except Exception:
        return os.getenv("DART_API_KEY", "")


API_KEY = get_api_key()

st.title("📊 국내 상장주 스크리너")
st.caption("재무 건전성 1차 필터 → 바닥권 종목 2차 필터")

if not API_KEY:
    st.error("DART API 키가 없습니다. 로컬은 `.env`, 클라우드는 Streamlit Secrets에 `DART_API_KEY`를 설정하세요.")
    st.stop()

client = DartClient(API_KEY)

with st.sidebar:
    st.header("데이터 설정")
    market = st.selectbox("시장", ["ALL", "KOSPI", "KOSDAQ"])
    bsns_year = st.text_input("사업연도", value="2025")
    prev_year = st.text_input("전년도 (성장률·비교용)", value="2024")

    st.divider()
    st.subheader("데이터 동기화")

    cached_count = count_listed_corps()
    if cached_count > 0:
        st.caption(f"저장된 회사목록: {cached_count}개")

    st.caption("클라우드에서는 저장소에 포함된 상장사 목록(번들)을 사용합니다. 체크 없이 불러오세요.")

    if st.button("1) 회사목록 불러오기", use_container_width=True):
        try:
            with st.spinner("상장사 목록 로드 중..."):
                count, source = client.sync_corp_codes(force_dart=False)
            if source == "cached":
                st.info(f"이미 {count}개 목록이 있습니다.")
            elif source == "bundled":
                st.success(f"번들 목록에서 {count}개 상장사 로드 완료 (즉시)")
            else:
                st.success(f"{count}개 상장사 로드 완료 ({source})")
        except RuntimeError as exc:
            st.error(str(exc))
        except (ConnectTimeout, RequestException) as exc:
            st.error(f"네트워크 오류: {exc}")

    corps = load_listed_corps(market)
    st.info(f"대상 종목: {len(corps)}개")

    max_fetch = st.slider("재무제표 조회 종목 수 (테스트용)", 10, 500, 100, step=10)

    if st.button("2) 재무제표 불러오기", use_container_width=True):
        if corps.empty:
            st.warning("먼저 회사목록을 불러오세요.")
        else:
            codes = corps["stock_code"].head(max_fetch).tolist()
            bar = st.progress(0)
            status = st.empty()

            def on_progress(cur, total, name):
                bar.progress(cur / total)
                status.text(f"{cur}/{total} {name}")

            with st.spinner(f"재무제표 수집 중 ({prev_year}, {bsns_year})..."):
                saved_prev = client.sync_financials(codes, prev_year, on_progress)
                saved_cur = client.sync_financials(codes, bsns_year, on_progress)
            st.success(f"{saved_cur}개 종목 저장 ({prev_year}→{bsns_year})")

    if st.button("3) 주가/바닥지표 불러오기", use_container_width=True):
        fin = load_financial_metrics(bsns_year, prev_year)
        if fin.empty:
            st.warning("먼저 재무제표를 불러오세요.")
        else:
            name_map = dict(zip(fin["stock_code"], fin["corp_name"]))
            codes = fin["stock_code"].tolist()
            bar = st.progress(0)
            status = st.empty()

            def on_price_progress(cur, total, name):
                bar.progress(cur / total)
                status.text(f"{cur}/{total} {name}")

            with st.spinner("KRX 주가 데이터 수집 중..."):
                prices = fetch_price_metrics(codes, name_map, progress_callback=on_price_progress)
                save_price_metrics(prices)
            st.success(f"{len(prices)}개 종목 주가 지표 저장")

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
    abs_items = [("revenue", "매출액", ""), ("operating_profit", "영업이익", ""), ("net_income", "당기순이익", "")]
    for key, label, help_text in abs_items:
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
    sort_options = list(SORT_LABELS.keys())
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
    financials = load_financial_metrics(bsns_year, prev_year)
    prices = load_price_metrics()
    merged = merge_financial_and_price(financials, prices)

    if merged.empty:
        st.warning("데이터가 없습니다. 사이드바에서 데이터를 먼저 불러오세요.")
    else:
        filtered = apply_range_filters(merged, filters)
        filtered = sort_dataframe(filtered, sort_rules)

        st.subheader(f"결과: {len(filtered)}종목 / 전체 {len(merged)}종목")

        show_cols = [
            "corp_name", "stock_code",
            "cash_survival_years", "current_ratio", "quick_ratio", "debt_ratio",
            "revenue_growth", "roe", "revenue_minus_debt_growth",
            "pct_from_low", "range_position", "bottom_dwell_ratio",
            "revenue", "operating_profit", "net_income", "current_price",
        ]
        show_cols = [c for c in show_cols if c in filtered.columns]
        display = format_display_df(filtered[show_cols])
        rename_map = {k: SORT_LABELS.get(k, k) for k in display.columns if k in SORT_LABELS}
        rename_map.update({"corp_name": "종목명", "stock_code": "종목코드"})
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
