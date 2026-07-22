"""Filter and sort logic for the stock screener."""

from __future__ import annotations

import pandas as pd


NUMERIC_COLUMNS = [
    "current_ratio",
    "quick_ratio",
    "debt_ratio",
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roa",
    "roe",
    "inventory_turnover",
    "receivable_turnover",
    "cash_months",
    "revenue",
    "operating_profit",
    "net_income",
    "current_price",
    "pct_from_low",
    "range_position",
    "bottom_dwell_ratio",
]

SORT_LABELS = {
    "corp_name": "종목명",
    "current_ratio": "유동비율(%)",
    "quick_ratio": "당좌비율(%)",
    "debt_ratio": "부채비율(%)",
    "revenue_growth": "매출성장률(%)",
    "gross_margin": "매출총이익률(%)",
    "operating_margin": "영업이익률(%)",
    "net_margin": "당기순이익률(%)",
    "roa": "ROA(%)",
    "roe": "ROE(%)",
    "inventory_turnover": "재고자산회전율",
    "receivable_turnover": "매출채권회전율",
    "cash_months": "현금규모(개월)",
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
    "current_price": "현재가",
    "pct_from_low": "저점대비상승(%)",
    "range_position": "52주위치(%)",
    "bottom_dwell_ratio": "바닥체류(%)",
}


def merge_financial_and_price(financials: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if financials.empty:
        return pd.DataFrame()
    if prices.empty:
        return financials.copy()
    merged = financials.merge(
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
    return merged


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
    columns = []
    ascending = []
    for col, asc in sort_by:
        if col in df.columns:
            columns.append(col)
            ascending.append(asc)
    if not columns:
        return df
    return df.sort_values(columns, ascending=ascending, na_position="last")


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    money_cols = ["revenue", "operating_profit", "net_income", "current_price", "low_52w", "high_52w"]
    for col in money_cols:
        if col in display.columns:
            display[col] = display[col].apply(_format_krw)
    pct_cols = [
        "current_ratio",
        "quick_ratio",
        "debt_ratio",
        "revenue_growth",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roa",
        "roe",
        "pct_from_low",
        "range_position",
        "bottom_dwell_ratio",
    ]
    for col in pct_cols:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    ratio_cols = ["inventory_turnover", "receivable_turnover", "cash_months"]
    for col in ratio_cols:
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
