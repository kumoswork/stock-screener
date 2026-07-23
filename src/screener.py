"""Filter UI helpers and display formatting."""

from __future__ import annotations

import pandas as pd

from criteria import (
    ABS_SPECS,
    FILTER_SPECS,
    LIST_COLUMNS,
    PRICE_FILTER_KEYS,
    SPEC_BY_KEY,
    categories_order,
    score_row,
    specs_in_category,
)

SORT_LABELS = {
    "corp_name": "종목명",
    "stock_code": "코드",
    "market": "시장",
    "attractiveness": "매력도",
    "grade": "등급",
    "current_price": "현재가",
    "pct_from_low": "저점대비(%)",
    "range_position": "52주위치(%)",
    "bottom_dwell_ratio": "바닥체류(%)",
    "current_ratio": "유동비율(%)",
    "quick_ratio": "당좌비율(%)",
    "debt_ratio": "부채비율(%)",
    "roe": "ROE(%)",
    "roa": "ROA(%)",
    "operating_margin": "영업이익률(%)",
    "revenue_growth": "매출성장(%)",
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
}


def all_filter_keys() -> list[str]:
    return [s.key for s in FILTER_SPECS]


def split_filters(filters: dict) -> tuple[dict, dict]:
    fin, price = {}, {}
    for key, bounds in filters.items():
        if key in PRICE_FILTER_KEYS:
            price[key] = bounds
        else:
            fin[key] = bounds
    return fin, price


def apply_range_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df.copy()
    for column, (min_val, max_val) in filters.items():
        if column not in result.columns:
            continue
        adj_min, adj_max = min_val, max_val
        if column == "cash_flow_match":
            if adj_min is not None:
                adj_min = adj_min / 100.0 if adj_min > 5 else adj_min
            if adj_max is not None:
                adj_max = adj_max / 100.0 if adj_max > 5 else adj_max
        if adj_min is not None:
            result = result[result[column].fillna(-float("inf")) >= adj_min]
        if adj_max is not None:
            result = result[result[column].fillna(float("inf")) <= adj_max]
    return result


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


def attach_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rows = []
    for _, row in df.iterrows():
        sc = score_row(row)
        rows.append(
            {
                "attractiveness": sc["attractiveness"],
                "grade": sc["grade"],
                "score_raw": sc["score_raw"],
                "badge_counts": sc["badge_counts"],
                "badges": sc["badges"],
            }
        )
    scored = pd.DataFrame(rows)
    out = df.reset_index(drop=True).copy()
    out["attractiveness"] = scored["attractiveness"]
    out["grade"] = scored["grade"]
    out["score_raw"] = scored["score_raw"]
    out["_badges"] = scored["badges"]
    out["_badge_counts"] = scored["badge_counts"]
    return out


def _on_filter_toggle(key: str) -> None:
    import streamlit as st

    spec = SPEC_BY_KEY[key]
    if not st.session_state.get(f"f_{key}", False):
        st.session_state.pop(f"_defaulted_{key}", None)
        return
    if spec.direction == "min" and spec.excellent_min is not None:
        val = spec.excellent_min * 100 if key == "cash_flow_match" else spec.excellent_min
        st.session_state[f"f_{key}_min"] = float(val)
    elif spec.direction in ("max", "max_change") and spec.excellent_max is not None:
        st.session_state[f"f_{key}_max"] = float(spec.excellent_max)
    elif spec.direction == "range":
        if spec.excellent_min is not None:
            st.session_state[f"f_{key}_min"] = float(spec.excellent_min)
        if spec.excellent_max is not None:
            st.session_state[f"f_{key}_max"] = float(spec.excellent_max)
    st.session_state[f"_defaulted_{key}"] = True


def _ensure_defaults(spec) -> None:
    import streamlit as st

    if not st.session_state.get(f"f_{spec.key}"):
        return
    if st.session_state.get(f"_defaulted_{spec.key}"):
        return
    _on_filter_toggle(spec.key)


def render_sidebar_filters(filters: dict) -> None:
    import streamlit as st

    for category in categories_order():
        st.markdown(f"**{category}**")
        for spec in specs_in_category(category):
            st.checkbox(
                spec.label,
                key=f"f_{spec.key}",
                help=f"{spec.help_text} | 우수: {_excellent_hint(spec)}",
                on_change=_on_filter_toggle,
                args=(spec.key,),
            )
            if st.session_state.get(f"f_{spec.key}"):
                _ensure_defaults(spec)
                _render_inline_inputs(spec, filters)
        st.divider()


def render_abs_filters(filters: dict) -> None:
    import streamlit as st

    st.markdown("**절대 금액**")
    for key, label in ABS_SPECS:
        st.checkbox(label, key=f"abs_{key}")
        if st.session_state.get(f"abs_{key}"):
            unit = st.radio(
                "단위",
                ["억원", "조원"],
                horizontal=True,
                key=f"abs_{key}_unit",
                label_visibility="collapsed",
            )
            mult = 1e8 if unit == "억원" else 1e12
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                st.caption("이상")
            with c2:
                lo = st.number_input("lo", key=f"abs_{key}_lo", label_visibility="collapsed")
            with c3:
                st.caption(unit)
            filters[key] = (lo * mult if lo else None, None)
    st.divider()


def _excellent_hint(spec) -> str:
    if spec.direction == "min":
        v = spec.excellent_min
        if spec.key == "cash_flow_match":
            return f"{v * 100:g}% 이상"
        return f"{v:g}{spec.unit_hint} 이상"
    if spec.direction in ("max", "max_change"):
        return f"{spec.excellent_max:g}{spec.unit_hint} 이하"
    if spec.direction == "range":
        return f"{spec.excellent_min:g}~{spec.excellent_max:g}{spec.unit_hint}"
    return ""


def _render_inline_inputs(spec, filters: dict) -> None:
    import streamlit as st

    if spec.direction == "min":
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.caption("이상")
        with c2:
            lo = st.number_input("min", key=f"f_{spec.key}_min", label_visibility="collapsed")
        filters[spec.key] = (lo, None)
    elif spec.direction in ("max", "max_change"):
        c1, c2 = st.columns([1.1, 1.4])
        with c1:
            st.caption("이하")
        with c2:
            hi = st.number_input("max", key=f"f_{spec.key}_max", label_visibility="collapsed")
        filters[spec.key] = (None, hi)
    elif spec.direction == "range":
        c1, c2, c3, c4 = st.columns([0.9, 1.1, 0.9, 1.1])
        with c1:
            st.caption("이상")
        with c2:
            lo = st.number_input("rmin", key=f"f_{spec.key}_min", label_visibility="collapsed")
        with c3:
            st.caption("이하")
        with c4:
            hi = st.number_input("rmax", key=f"f_{spec.key}_max", label_visibility="collapsed")
        filters[spec.key] = (lo, hi)


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    if "current_price" in display.columns:
        display["current_price"] = display["current_price"].apply(_format_price)
    for col in ["revenue", "operating_profit", "net_income"]:
        if col in display.columns:
            display[col] = display[col].apply(_format_krw_big)

    pct_cols = [
        "pct_from_low",
        "range_position",
        "bottom_dwell_ratio",
        "current_ratio",
        "quick_ratio",
        "debt_ratio",
        "roe",
        "roa",
        "operating_margin",
        "revenue_growth",
    ]
    for col in pct_cols:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "-")
    if "attractiveness" in display.columns:
        display["attractiveness"] = display["attractiveness"].apply(
            lambda x: f"{int(x)}" if pd.notna(x) else "-"
        )
    return display


def _format_price(value) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value):,.0f}"


def _format_krw_big(value) -> str:
    if pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 1_0000_0000_0000:
        return f"{value / 1_0000_0000_0000:.1f}조"
    if abs(value) >= 1_0000_0000:
        return f"{value / 1_0000_0000:.0f}억"
    return f"{value:,.0f}"


def format_account_krw(value) -> str:
    return _format_krw_big(value)
