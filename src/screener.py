"""Filter UI helpers and display formatting."""

from __future__ import annotations

import pandas as pd

from criteria import (
    ABS_SPECS,
    FILTER_SPECS,
    LIST_COLUMNS,
    MARGIN_BADGE_THRESHOLDS,
    PRICE_FILTER_KEYS,
    REVENUE_GROWTH_KEY,
    SPEC_BY_KEY,
    categories_order,
    score_row,
    specs_in_category,
)

SORT_LABELS = {
    "corp_name": "종목명",
    "stock_code": "코드",
    "market": "시장",
    "attractiveness": "점수",
    "grade": "등급",
    "current_price": "현재가",
    "pct_from_avg_52w": "평균대비(%)",
    "range_position": "52주위치(%)",
    "bottom_dwell_ratio": "바닥체류(%)",
    "current_ratio": "유동비율(%)",
    "quick_ratio": "당좌비율(%)",
    "debt_ratio": "부채비율(%)",
    "roe": "ROE(%)",
    "roa": "ROA(%)",
    "operating_margin": "영업이익률",
    "revenue_growth": "매출성장",
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
}

# 결과 리스트 열 폭 (종목명+상세 포함)
LIST_WIDTHS = [2.2, 0.8, 0.7, 0.95, 0.95, 0.95, 0.95, 0.7, 0.85]

# 헤더/값 정렬: 종목명만 왼쪽, 나머지 가운데
LIST_ALIGN = {
    "corp_name": "left",
}


def tradingview_chart_url(stock_code: str) -> str:
    """국내 상장주 TradingView 차트 URL (KRX)."""
    code = str(stock_code).zfill(6)
    return f"https://kr.tradingview.com/chart/?symbol=KRX%3A{code}"


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
    for c in ["current_price", "low_52w", "high_52w", "avg_52w", "pct_from_avg_52w", "range_position", "bottom_dwell_ratio"]:
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
            "avg_52w",
            "pct_from_avg_52w",
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
                "category_scores": sc["category_scores"],
            }
        )
    scored = pd.DataFrame(rows)
    out = df.reset_index(drop=True).copy()
    out["attractiveness"] = scored["attractiveness"]
    out["grade"] = scored["grade"]
    out["score_raw"] = scored["score_raw"]
    out["_badges"] = scored["badges"]
    out["_badge_counts"] = scored["badge_counts"]
    out["_category_scores"] = scored["category_scores"]
    return out


def _on_filter_toggle(key: str) -> None:
    import streamlit as st

    spec = SPEC_BY_KEY[key]
    if not st.session_state.get(f"f_{key}", False):
        st.session_state.pop(f"_defaulted_{key}", None)
        return
    if spec.direction == "min" and spec.excellent_min is not None:
        val = spec.excellent_min * 100 if key == "cash_flow_match" else spec.excellent_min
        st.session_state[f"f_{key}_min"] = int(round(float(val)))
    elif spec.direction in ("max", "max_change") and spec.excellent_max is not None:
        st.session_state[f"f_{key}_max"] = int(round(float(spec.excellent_max)))
    elif spec.direction == "range":
        if spec.excellent_min is not None:
            st.session_state[f"f_{key}_min"] = int(round(float(spec.excellent_min)))
        if spec.excellent_max is not None:
            st.session_state[f"f_{key}_max"] = int(round(float(spec.excellent_max)))
    st.session_state[f"_defaulted_{key}"] = True


def _ensure_defaults(spec) -> None:
    import streamlit as st

    if not st.session_state.get(f"f_{spec.key}"):
        return
    if st.session_state.get(f"_defaulted_{spec.key}"):
        return
    _on_filter_toggle(spec.key)


def _filter_unit(spec) -> str:
    """필터 입력 UI용 단위. 현금흐름일치도는 화면에서 %로 입력."""
    if spec.key == "cash_flow_match":
        return "%"
    return spec.unit_hint or ""


def _unit_after_label(spec, kind: str) -> str:
    """입력칸 뒤에 붙일 문구. kind: min|max|range."""
    unit = _filter_unit(spec)
    if kind == "min":
        return f"{unit} 이상".strip() if unit else "이상"
    if kind == "max":
        return f"{unit} 이하".strip() if unit else "이하"
    return unit


def _int_number_input(label: str, key: str, help_text: str | None = None) -> int:
    import streamlit as st

    kwargs = {
        "label": label,
        "key": key,
        "step": 1,
        "format": "%d",
        "label_visibility": "collapsed",
    }
    if help_text:
        kwargs["help"] = help_text
    # 기존 세션 값이 float(100.0)이면 정수로 정규화
    if key in st.session_state:
        try:
            st.session_state[key] = int(round(float(st.session_state[key])))
        except (TypeError, ValueError):
            pass
    return int(st.number_input(**kwargs))


def render_sidebar_filters(filters: dict) -> None:
    """체크 | 입력 | 단위 — 한 줄 배치."""
    import streamlit as st

    for category in categories_order():
        st.markdown(f"**{category}**")
        for spec in specs_in_category(category):
            if spec.direction == "range":
                c_chk, c_lo, c_tilde, c_hi, c_unit = st.columns([1.25, 0.9, 0.25, 0.9, 0.55])
                with c_chk:
                    st.checkbox(
                        spec.label,
                        key=f"f_{spec.key}",
                        help=f"{spec.help_text} | 우수: {_excellent_hint(spec)}",
                        on_change=_on_filter_toggle,
                        args=(spec.key,),
                    )
                if st.session_state.get(f"f_{spec.key}"):
                    _ensure_defaults(spec)
                    unit = _unit_after_label(spec, "range")
                    with c_lo:
                        lo = _int_number_input("이상", f"f_{spec.key}_min", "이상")
                    with c_tilde:
                        st.markdown(
                            '<p class="ks-unit-suffix" style="text-align:center;">～</p>',
                            unsafe_allow_html=True,
                        )
                    with c_hi:
                        hi = _int_number_input("이하", f"f_{spec.key}_max", "이하")
                    with c_unit:
                        if unit:
                            st.markdown(
                                f'<p class="ks-unit-suffix">{unit}</p>',
                                unsafe_allow_html=True,
                            )
                    filters[spec.key] = (lo, hi)
            else:
                c_chk, c_val, c_unit = st.columns([1.35, 1.0, 0.9])
                with c_chk:
                    st.checkbox(
                        spec.label,
                        key=f"f_{spec.key}",
                        help=f"{spec.help_text} | 우수: {_excellent_hint(spec)}",
                        on_change=_on_filter_toggle,
                        args=(spec.key,),
                    )
                if st.session_state.get(f"f_{spec.key}"):
                    _ensure_defaults(spec)
                    kind = "min" if spec.direction == "min" else "max"
                    suffix = _unit_after_label(spec, kind)
                    with c_val:
                        if spec.direction == "min":
                            lo = _int_number_input("min", f"f_{spec.key}_min")
                            filters[spec.key] = (lo, None)
                        else:
                            hi = _int_number_input("max", f"f_{spec.key}_max")
                            filters[spec.key] = (None, hi)
                    with c_unit:
                        st.markdown(
                            f'<p class="ks-unit-suffix">{suffix}</p>',
                            unsafe_allow_html=True,
                        )
        st.divider()


def render_abs_filters(filters: dict) -> None:
    import streamlit as st

    st.markdown("**절대 금액**")
    for key, label in ABS_SPECS:
        c_chk, c_val, c_unit, c_suf = st.columns([1.15, 0.95, 0.9, 0.55])
        with c_chk:
            st.checkbox(label, key=f"abs_{key}")
        if st.session_state.get(f"abs_{key}"):
            with c_val:
                lo = _int_number_input("lo", f"abs_{key}_lo")
            with c_unit:
                unit = st.selectbox(
                    "단위",
                    ["억원", "조원"],
                    key=f"abs_{key}_unit",
                    label_visibility="collapsed",
                )
            with c_suf:
                st.markdown(
                    '<p class="ks-unit-suffix">이상</p>',
                    unsafe_allow_html=True,
                )
            mult = 1e8 if unit == "억원" else 1e12
            filters[key] = (lo * mult if lo else None, None)
    st.divider()


def _excellent_hint(spec) -> str:
    if spec.key == REVENUE_GROWTH_KEY:
        return "0%↑양호 · 40%↑우수 · 80%↑매우우수"
    if spec.key in MARGIN_BADGE_THRESHOLDS:
        good, excellent, _very = MARGIN_BADGE_THRESHOLDS[spec.key]
        return f"{good:g}%↑양호 · {excellent:g}%↑우수"
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


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    if "current_price" in display.columns:
        display["current_price"] = display["current_price"].apply(_format_price)
    for col in ["revenue", "operating_profit", "net_income"]:
        if col in display.columns:
            display[col] = display[col].apply(_format_krw_big)

    pct_cols = [
        "pct_from_avg_52w",
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
        return f"{value / 1_0000_0000_0000:,.1f}조"
    if abs(value) >= 1_0000_0000:
        return f"{value / 1_0000_0000:,.0f}억"
    return f"{value:,.0f}"


def format_account_krw(value) -> str:
    return _format_krw_big(value)


PCT_FORMAT_COLS = {
    "pct_from_avg_52w",
    "range_position",
    "bottom_dwell_ratio",
    "current_ratio",
    "quick_ratio",
    "debt_ratio",
    "roe",
    "roa",
    "operating_margin",
    "revenue_growth",
    "gross_margin",
    "net_margin",
    "sga_ratio",
    "sga_ratio_change",
    "cash_to_revenue",
    "revenue_minus_debt_growth",
    "debt_growth",
    "happy_debt_growth",
}


def format_pct(value, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{float(value):,.{digits}f}%"


def format_metric_value(key: str, value) -> str:
    """상세/리스트 공통 표시."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if key in ("revenue", "operating_profit", "net_income", "current_price"):
        if key == "current_price":
            return _format_price(value)
        return _format_krw_big(value)
    if key in ("sga_ratio_change", "revenue_minus_debt_growth", "debt_growth", "happy_debt_growth"):
        return f"{float(value):,.1f}%p"
    if key == "cash_flow_match":
        v = float(value)
        return f"{v * 100:,.1f}%" if abs(v) < 20 else f"{v:,.2f}"
    if key in (
        "cash_survival_years",
        "inventory_months",
        "cash_months",
        "inventory_turnover",
        "receivable_turnover",
    ):
        return f"{float(value):,.2f}"
    if key in PCT_FORMAT_COLS:
        return format_pct(value)
    if key == "attractiveness":
        return f"{int(value):,}"
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)


def format_cell(row: pd.Series, col: str) -> str:
    if col not in row.index or pd.isna(row.get(col)):
        return "-"
    return format_metric_value(col, row[col])
