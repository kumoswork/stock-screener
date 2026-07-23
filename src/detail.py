"""Detail modal content: badges, scores, metrics."""

from __future__ import annotations

import pandas as pd

from criteria import BADGE_COLOR, FILTER_SPECS, categories_order, score_row, specs_in_category
from screener import format_account_krw


def show_detail_dialog(row: pd.Series) -> None:
    import streamlit as st

    sc = score_row(row)
    name = row.get("corp_name", "")
    code = str(row.get("stock_code", "")).zfill(6)

    @st.dialog(f"{name} ({code})", width="large")
    def _dialog():
        c1, c2, c3 = st.columns(3)
        c1.metric("매력도", f"{sc['attractiveness']}점")
        c2.metric("등급", sc["grade"])
        counts = sc["badge_counts"]
        c3.metric(
            "뱃지",
            f"매우우수 {counts.get('매우우수', 0)} · 우수 {counts.get('우수', 0)}",
        )
        st.caption(
            f"주의 {counts.get('주의', 0)} · 위험 {counts.get('위험', 0)} · "
            f"보통 {counts.get('보통', 0)} · 해당없음 {counts.get('해당없음', 0)}"
        )

        st.subheader("주가 현위치")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("현재가", _price(row.get("current_price")))
        p2.metric("저점대비", _pct(row.get("pct_from_low")), sc["badges"].get("pct_from_low", ""))
        p3.metric("52주위치", _pct(row.get("range_position")))
        p4.metric("바닥체류", _pct(row.get("bottom_dwell_ratio")), sc["badges"].get("bottom_dwell_ratio", ""))
        if row.get("low_52w") is not None:
            st.caption(f"52주 최저 {_price(row.get('low_52w'))} / 최고 {_price(row.get('high_52w'))}")

        st.subheader("지표 평가")
        for category in categories_order():
            with st.expander(category, expanded=(category.startswith("주가"))):
                for spec in specs_in_category(category):
                    val = row.get(spec.key)
                    badge = sc["badges"].get(spec.key, "해당없음")
                    icon = BADGE_COLOR.get(badge, "")
                    st.markdown(
                        f"{icon} **{spec.label}**: {_fmt_metric(spec.key, val)} "
                        f"— `{badge}`"
                    )
                    st.caption(spec.help_text)

        st.subheader("주요 금액 · 재무제표")
        account_rows = [
            ("current_assets", "유동자산"),
            ("cash", "현금및현금성자산"),
            ("short_term_financial", "단기금융상품"),
            ("receivables", "매출채권"),
            ("inventory", "재고자산"),
            ("total_assets", "자산총계"),
            ("current_liabilities", "유동부채"),
            ("total_liabilities", "부채총계"),
            ("total_equity", "자본총계"),
            ("advances", "선수금/예수금"),
            ("revenue", "매출액"),
            ("cogs", "매출원가"),
            ("gross_profit", "매출총이익"),
            ("sga", "판매비와관리비"),
            ("operating_profit", "영업이익"),
            ("net_income", "당기순이익"),
            ("operating_cash_flow", "영업활동현금흐름"),
            ("capex", "시설투자(Capex)"),
            ("dividends_paid", "배당금지급"),
        ]
        shown = 0
        for k, lab in account_rows:
            if k in row.index and pd.notna(row.get(k)):
                st.write(f"- **{lab}**: {format_account_krw(row.get(k))}")
                shown += 1
        if shown < 3:
            st.caption("원장 계정이 스냅샷에 없으면 지표·금액(매출/이익)만 표시됩니다. 다음 빌드 시 계정이 채워집니다.")
        else:
            st.caption("Capex·배당은 계정 매핑 후 표시됩니다.")

    _dialog()


def _price(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):,.0f}원"


def _pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):.1f}%"


def _fmt_metric(key: str, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    if key == "cash_flow_match":
        return f"{v * 100:.1f}%" if abs(v) < 20 else f"{v:.2f}"
    if key in ("cash_survival_years", "inventory_months", "cash_months", "inventory_turnover", "receivable_turnover"):
        return f"{v:.2f}"
    return f"{v:.1f}"
