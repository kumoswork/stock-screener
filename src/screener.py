"""Filter and sort logic for the stock screener."""

from __future__ import annotations

import pandas as pd

SORT_LABELS = {
    "corp_name": "종목명",
    "stock_code": "종목코드",
    # B경제
    "cash_survival_years": "현금생존력(년)",
    "inventory_months": "재고보유(월)",
    "cash_flow_match": "현금흐름일치도",
    "cash_to_revenue": "현금/매출(%)",
    "cash_to_op_profit_x3": "현금/영업이익x3(%)",
    "happy_debt_growth": "행복한부채성장(%)",
    "sga_ratio": "판관비율(%)",
    "sga_ratio_change": "판관비율변화(%p)",
    # 안전성
    "current_ratio": "유동비율(%)",
    "quick_ratio": "당좌비율(%)",
    "debt_ratio": "부채비율(%)",
    "cash_months": "현금규모(개월)",
    # 수익/성장성
    "revenue_growth": "매출성장률(%)",
    "gross_margin": "매출총이익률(%)",
    "operating_margin": "영업이익률(%)",
    "net_margin": "당기순이익률(%)",
    # 효율성
    "roa": "ROA(%)",
    "roe": "ROE(%)",
    "inventory_turnover": "재고자산회전율",
    "receivable_turnover": "매출채권회전율",
    # check!!
    "debt_growth": "부채증가율(%)",
    "revenue_minus_debt_growth": "매출증가-부채증가(%)",
    # 절대금액
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
    # 주가
    "current_price": "현재가",
    "pct_from_low": "저점대비상승(%)",
    "range_position": "52주위치(%)",
    "bottom_dwell_ratio": "바닥체류(%)",
}

FILTER_CATEGORIES = {
    "B경제 · 현금 생존력": [
        ("cash_survival_years", "현금 생존력 (년)", "(현금+단기금융)/순손실. 2년 이상 권장"),
        ("inventory_months", "재고 보유 월수", "재고/월매출원가. 3개월 이상이면 현금흐름 압박"),
        ("cash_flow_match", "현금흐름 일치도", "영업CF/당기순이익. 1에 가까울수록 이익의 질 좋음"),
        ("cash_to_revenue", "현금/매출 (%)", "현금 과다 여부. 너무 높으면 효율 저하"),
        ("cash_to_op_profit_x3", "현금/영업이익×3 (%)", "현금 과다 체크 보조지표"),
        ("happy_debt_growth", "행복한 부채 성장 (%)", "(당기선수금-전기선수금)/전기"),
        ("sga_ratio", "판관비율 (%)", "판관비/매출"),
        ("sga_ratio_change", "판관비율 변화 (%p)", "전년 대비 감소가 좋음 (음수)"),
    ],
    "안전성 check!": [
        ("current_ratio", "유동비율 (%)", "100% 이상 안전"),
        ("quick_ratio", "당좌비율 (%)", "70% 이상 안전"),
        ("debt_ratio", "부채비율 (%)", "200% 초과 위험 / 50% 미만 성장 정체 우려"),
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
        ("inventory_turnover", "재고자산회전율", "매출/재고"),
        ("receivable_turnover", "매출채권회전율", "매출/매출채권"),
    ],
    "check!!": [
        ("revenue_minus_debt_growth", "매출증가율 - 부채증가율 (%)", "매출성장 > 부채성장"),
        ("debt_growth", "부채증가율 (%)", "보조 참고"),
    ],
    "바닥 위치 (주가)": [
        ("pct_from_low", "저점대비상승 (%)", "낮을수록 바닥 근처"),
        ("range_position", "52주위치 (%)", "0~30% 구간 하단"),
        ("bottom_dwell_ratio", "바닥체류 (%)", "높을수록 오래 바닥권"),
    ],
}


def merge_financial_and_price(financials: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if financials.empty:
        return pd.DataFrame()
    if prices.empty:
        return financials.copy()
    return financials.merge(
        prices[
            [
                "stock_code",
                "current_price",
                "low_52w",
                "high_52w",
                "pct_from_low",
                "range_position",
                "bottom_dwell_ratio",
            ]
        ],
        on="stock_code",
        how="left",
    )


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


def render_filter_group(filters: dict, category: str, items: list, key_prefix: str) -> None:
    import streamlit as st

    cols = st.columns(2)
    for i, (key, label, help_text) in enumerate(items):
        with cols[i % 2]:
            if st.checkbox(label, key=f"{key_prefix}_{key}"):
                c1, c2 = st.columns(2)
                with c1:
                    lo = st.number_input("최소", key=f"{key_prefix}_{key}_lo", help=help_text)
                with c2:
                    hi = st.number_input("최대", key=f"{key_prefix}_{key}_hi")
                filters[key] = (lo, hi if hi != 0 else None)


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
