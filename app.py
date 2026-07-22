"""국내 상장주 재무 + 바닥 위치 스크리너."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from dart_api import DartClient, load_listed_corps  # noqa: E402
from metrics import load_financial_metrics  # noqa: E402
from price import fetch_price_metrics, load_price_metrics, save_price_metrics  # noqa: E402
from screener import (  # noqa: E402
    SORT_LABELS,
    apply_range_filters,
    format_display_df,
    merge_financial_and_price,
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
st.caption("재무 건전성으로 1차 필터 → 바닥권 종목 위주로 2차 필터")

if not API_KEY:
    st.error("DART API 키가 없습니다. 로컬은 `.env`, 클라우드는 Streamlit Secrets에 `DART_API_KEY`를 설정하세요.")
    st.stop()

client = DartClient(API_KEY)

with st.sidebar:
    st.header("데이터 설정")
    market = st.selectbox("시장", ["ALL", "KOSPI", "KOSDAQ"])
    bsns_year = st.text_input("사업연도", value="2023")
    prev_year = st.text_input("전년도 (성장률용)", value="2022")

    st.divider()
    st.subheader("데이터 동기화")

    if st.button("1) DART 회사목록 불러오기", use_container_width=True):
        with st.spinner("회사 목록 다운로드 중..."):
            count = client.sync_corp_codes()
        st.success(f"상장사 {count}개 저장 완료")

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

            with st.spinner("DART 재무제표 수집 중..."):
                saved = client.sync_financials(codes, bsns_year, on_progress)
            st.success(f"{saved}개 종목 재무제표 저장 ({bsns_year}년)")

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

tab_fin, tab_price, tab_abs, tab_sort = st.tabs(
    ["재무 비율", "바닥 위치 (주가)", "절대 금액", "정렬"]
)

filters: dict[str, tuple[float | None, float | None]] = {}

with tab_fin:
    st.markdown("**재무 비율** — 체크한 항목만 필터 적용")
    fin_items = [
        ("current_ratio", "유동비율 (%)", "100 이상 권장"),
        ("quick_ratio", "당좌비율 (%)", "70 이상 권장"),
        ("debt_ratio", "부채비율 (%)", "낮을수록 안전. 50 이하 등"),
        ("revenue_growth", "매출성장률 (%)", ""),
        ("gross_margin", "매출총이익률 (%)", ""),
        ("operating_margin", "영업이익률 (%)", ""),
        ("net_margin", "당기순이익률 (%)", ""),
        ("roa", "ROA (%)", ""),
        ("roe", "ROE (%)", ""),
        ("inventory_turnover", "재고자산회전율", ""),
        ("receivable_turnover", "매출채권회전율", ""),
        ("cash_months", "현금규모 (개월)", "현금 / 월간 소진"),
    ]
    cols = st.columns(3)
    for i, (key, label, help_text) in enumerate(fin_items):
        with cols[i % 3]:
            if st.checkbox(label, key=f"fin_{key}"):
                c1, c2 = st.columns(2)
                with c1:
                    lo = st.number_input("최소", key=f"fin_{key}_lo", help=help_text)
                with c2:
                    hi = st.number_input("최대", key=f"fin_{key}_hi")
                filters[key] = (lo, hi if hi != 0 else None)

with tab_price:
    st.markdown(
        """
        **바닥 다진 종목** 찾기용 지표입니다.
        - **저점대비상승(%)**: 52주 최저가 대비 몇 % 올랐는지. **낮을수록** 바닥 근처
        - **52주위치(%)**: 저점~고점 구간에서 현재 위치. **0%에 가까울수록** 바닥
        - **바닥체류(%)**: 최근 120일 중 하위 25% 구간에 머문 비율. **높을수록** 오랫동안 바닥권
        """
    )
    price_items = [
        ("pct_from_low", "저점대비상승 (%)", "예: 0 ~ 15 (바닥에서 조금만 오른 종목)"),
        ("range_position", "52주위치 (%)", "예: 0 ~ 30 (구간 하단)"),
        ("bottom_dwell_ratio", "바닥체류 (%)", "예: 60 이상 (오래 바닥권)"),
    ]
    for key, label, help_text in price_items:
        if st.checkbox(label, key=f"px_{key}"):
            c1, c2 = st.columns(2)
            with c1:
                lo = st.number_input("최소", key=f"px_{key}_lo", help=help_text)
            with c2:
                hi = st.number_input("최대", key=f"px_{key}_hi")
            filters[key] = (lo, hi if hi != 0 else None)

with tab_abs:
    st.markdown("**절대 금액** 필터 — 매출액·영업이익·당기순이익 (단위: 원)")
    abs_items = [
        ("revenue", "매출액"),
        ("operating_profit", "영업이익"),
        ("net_income", "당기순이익"),
    ]
    c1, c2, c3 = st.columns(3)
    for col, (key, label) in zip([c1, c2, c3], abs_items):
        with col:
            if st.checkbox(label, key=f"abs_{key}"):
                unit = st.selectbox("단위", ["억원", "조원"], key=f"abs_{key}_unit")
                multiplier = 1e8 if unit == "억원" else 1e12
                lo = st.number_input("최소", key=f"abs_{key}_lo", value=0.0)
                hi = st.number_input("최대", key=f"abs_{key}_hi", value=0.0)
                filters[key] = (
                    lo * multiplier if lo else None,
                    hi * multiplier if hi else None,
                )

sort_rules: list[tuple[str, bool]] = []
with tab_sort:
    st.markdown("정렬 기준을 최대 3개까지 지정 (위에서부터 우선순위)")
    sort_options = list(SORT_LABELS.keys())
    for i in range(3):
        c1, c2 = st.columns([3, 1])
        with c1:
            col = st.selectbox(
                f"정렬 {i+1}",
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
            "corp_name",
            "stock_code",
            "current_ratio",
            "quick_ratio",
            "debt_ratio",
            "roe",
            "revenue",
            "operating_profit",
            "net_income",
            "pct_from_low",
            "range_position",
            "bottom_dwell_ratio",
            "current_price",
        ]
        show_cols = [c for c in show_cols if c in filtered.columns]
        display = format_display_df(filtered[show_cols])
        display = display.rename(columns={k: SORT_LABELS.get(k, k) for k in display.columns if k in SORT_LABELS})
        display = display.rename(columns={"corp_name": "종목명", "stock_code": "종목코드"})

        st.dataframe(display, use_container_width=True, hide_index=True)

        csv = filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV 다운로드", csv, file_name="screener_result.csv", mime="text/csv")

with st.expander("사용 팁"):
    st.markdown(
        """
        ### 바닥 다진 종목 찾기 예시
        1. 재무: ROE 10% 이상, 부채비율 50% 이하
        2. 바닥: 저점대비상승 0~20%, 52주위치 0~30%, 바닥체류 50% 이상
        3. 정렬: 바닥체류 내림차순 → ROE 내림차순

        ### 데이터 주기
        - 재무: 연간 (사업보고서 기준)
        - 주가: 최근 52주 일봉 기준

        ### API 키 보안
        - `.env` 파일에만 저장하고 Git에 올리지 마세요
        - 채팅에 노출된 키는 DART에서 재발급을 권장합니다
        """
    )
