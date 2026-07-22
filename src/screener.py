"""Filter and sort logic for the stock screener."""

from __future__ import annotations

import pandas as pd

SORT_LABELS = {
    "corp_name": "종목명",
    "stock_code": "종목코드",
    "market": "시장",
    "cash_survival_years": "현금생존력(년)",
    "inventory_months": "재고보유(월)",
    "cash_flow_match": "현금흐름일치도",
    "cash_to_revenue": "현금/매출(%)",
    "cash_to_op_profit_x3": "현금/영업이익x3(%)",
    "happy_debt_growth": "행복한부채성장(%)",
    "sga_ratio": "판관비율(%)",
    "sga_ratio_change": "판관비율변화(%p)",
    "current_ratio": "유동비율(%)",
    "quick_ratio": "당좌비율(%)",
    "debt_ratio": "부채비율(%)",
    "cash_months": "현금규모(개월)",
    "revenue_growth": "매출성장률(%)",
    "gross_margin": "매출총이익률(%)",
    "operating_margin": "영업이익률(%)",
    "net_margin": "당기순이익률(%)",
    "roa": "ROA(%)",
    "roe": "ROE(%)",
    "inventory_turnover": "재고자산회전율",
    "receivable_turnover": "매출채권회전율",
    "debt_growth": "부채증가율(%)",
    "revenue_minus_debt_growth": "매출증가-부채증가(%)",
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
    "current_price": "현재가",
    "pct_from_low": "저점대비상승(%)",
    "range_position": "52주위치(%)",
    "bottom_dwell_ratio": "바닥체류(%)",
}

FILTER_CATEGORIES = {
    "B경제 · 현금 생존력": [
        ("cash_survival_years", "현금 생존력 (년)", "2년 이상 권장"),
        ("inventory_months", "재고 보유 월수", "3개월 이상이면 압박"),
        ("cash_flow_match", "현금흐름 일치도", "영업CF/순이익"),
        ("cash_to_revenue", "현금/매출 (%)", "과다 시 효율 저하"),
        ("cash_to_op_profit_x3", "현금/영업이익×3 (%)", ""),
        ("happy_debt_growth", "행복한 부채 성장 (%)", "선수금 증가"),
        ("sga_ratio", "판관비율 (%)", ""),
        ("sga_ratio_change", "판관비율 변화 (%p)", "감소(음수) 선호"),
    ],
    "안전성 check!": [
        ("current_ratio", "유동비율 (%)", "100% 이상"),
        ("quick_ratio", "당좌비율 (%)", "70% 이상"),
        ("debt_ratio", "부채비율 (%)", "200% 초과 위험"),
        ("cash_months", "현금규모 (개월)", "현금/월판관비"),
    ],
    "수익/성장성 check!": [
        ("revenue_growth", "매출성장률 (%)", ""),
        ("gross_margin", "매출총이익률 (%)", ""),
        ("operating_margin", "영업이익률 (%)", ""),
        ("net_margin", "당기순이익률 (%)", ""),
    ],
    "효율성 check!": [
        ("roa", "ROA (%)", ""),
        ("roe", "ROE (%)", "15% 이상 선호"),
        ("inventory_turnover", "재고자산회전율", ""),
        ("receivable_turnover", "매출채권회전율", ""),
    ],
    "check!!": [
        ("revenue_minus_debt_growth", "매출증가−부채증가 (%)", ""),
        ("debt_growth", "부채증가율 (%)", ""),
    ],
    "바닥 위치 (주가)": [
        ("pct_from_low", "저점대비상승 (%)", "낮을수록 바닥"),
        ("range_position", "52주위치 (%)", "0~30 하단"),
        ("bottom_dwell_ratio", "바닥체류 (%)", "높을수록 오래 바닥"),
    ],
}


def merge_financial_and_price(financials: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if financials.empty:
        return pd.DataFrame()
    base = financials.copy()
    for c in ["current_price", "low_52w", "high_52w", "pct_from_low", "range_position", "bottom_dwell_ratio"]:
        if c in base.columns:
            base = base.drop(columns=[c])
    if prices is None or prices.empty:
        return base
    cols = [
        c
        for c in [
            "stock_code",
            "current_price",
            "low_52w",
            "high_52w",
            "pct_from_low",
            "range_position",
            "bottom_dwell_ratio",
        ]
        if c in prices.columns
    ]
    return base.merge(prices[cols], on="stock_code", how="left")


def apply_range_filters(df: pd.DataFrame, filters: dict[str, tuple[float | None, float | None]]) -> pd.DataFrame:
    result = df.copy()
    for column, (min_val, max_val) in filters.items():
        if column not in result.columns:
            continue
        if min_val is not None:
            result = result[result[column].fillna(-float("inf")) >= min_val]
        if max_val is not None:
            result = result[result[column].fillna(float("inf")) <= max_val]
    return result


def sort_dataframe(df: pd.DataFrame, sort_by: list[tuple[str, bool]]) -> pd.DataFrame:
    if df.empty or not sort_by:
        return df
    columns, ascending = [], []
    for col, asc in sort_by:
        if col in df.columns:
            columns.append(col)
            ascending.append(asc)
    if not columns:
        return df
    return df.sort_values(columns, ascending=ascending, na_position="last")


def render_sidebar_filters(filters: dict) -> list[tuple[str, bool]]:
    import streamlit as st

    for category, items in FILTER_CATEGORIES.items():
        st.markdown(f"**{category}**")
        for key, label, help_text in items:
            enabled = st.checkbox(label, key=f"f_{key}", help=help_text or None)
            if enabled:
                c1, c2 = st.columns(2)
                with c1:
                    lo = st.number_input("min", key=f"f_{key}_lo", value=0.0, label_visibility="collapsed")
                with c2:
                    hi = st.number_input("max", key=f"f_{key}_hi", value=0.0, label_visibility="collapsed")
                filters[key] = (None if lo == 0 else lo, None if hi == 0 else hi)
        st.divider()

    st.markdown("**절대 금액**")
    for key, label in [("revenue", "매출액"), ("operating_profit", "영업이익"), ("net_income", "당기순이익")]:
        if st.checkbox(label, key=f"abs_{key}"):
            unit = st.radio("단위", ["억원", "조원"], horizontal=True, key=f"abs_{key}_unit")
            multiplier = 1e8 if unit == "억원" else 1e12
            c1, c2 = st.columns(2)
            with c1:
                lo = st.number_input("min", key=f"abs_{key}_lo", value=0.0, label_visibility="collapsed")
            with c2:
                hi = st.number_input("max", key=f"abs_{key}_hi", value=0.0, label_visibility="collapsed")
            filters[key] = (lo * multiplier if lo else None, hi * multiplier if hi else None)
    st.divider()

    st.markdown("**정렬**")
    sort_rules: list[tuple[str, bool]] = []
    sort_options = list(SORT_LABELS.keys())
    for i in range(2):
        col = st.selectbox(
            f"기준 {i + 1}",
            [""] + sort_options,
            format_func=lambda x: "—" if x == "" else SORT_LABELS.get(x, x),
            key=f"sort_{i}",
        )
        if col:
            asc = (
                st.radio(f"순서 {i + 1}", ["내림차순", "오름차순"], horizontal=True, key=f"sort_dir_{i}")
                == "오름차순"
            )
            sort_rules.append((col, asc))
    return sort_rules


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    money_cols = ["revenue", "operating_profit", "net_income", "current_price", "low_52w", "high_52w"]
    for col in money_cols:
        if col in display.columns:
            display[col] = display[col].apply(_format_krw)

    pct_cols = [
        "current_ratio", "quick_ratio", "debt_ratio", "revenue_growth", "gross_margin",
        "operating_margin", "net_margin", "roa", "roe", "pct_from_low", "range_position",
        "bottom_dwell_ratio", "cash_to_revenue", "cash_to_op_profit_x3", "happy_debt_growth",
        "sga_ratio", "sga_ratio_change", "debt_growth", "revenue_minus_debt_growth",
    ]
    for col in pct_cols:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "-")

    float_cols = [
        "inventory_turnover", "receivable_turnover", "cash_months", "cash_flow_match",
        "cash_survival_years", "inventory_months",
    ]
    for col in float_cols:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    return display


def _format_krw(value) -> str:
    if pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 1_0000_0000_0000:
        return f"{value / 1_0000_0000_0000:.1f}조"
    if abs(value) >= 1_0000_0000:
        return f"{value / 1_0000_0000:.0f}억"
    if abs(value) >= 1_0000:
        return f"{value / 1_0000:.0f}만"
    return f"{value:,.0f}"
