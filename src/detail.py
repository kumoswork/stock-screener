"""Detail modal: score card + metric grid style."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from criteria import BADGE_SCORE, PRICE_FILTER_KEYS, categories_order, score_row, specs_in_category
from screener import format_account_krw, format_cell
from ui_theme import inject_list_detail_css, render_metric_grid, render_score_card


@st.dialog("종목 상세", width="large")
def detail_dialog(row_dict: dict) -> None:
    inject_list_detail_css()
    row = pd.Series(row_dict)
    sc = score_row(row)
    name = str(row.get("corp_name", ""))
    code = str(row.get("stock_code", "")).zfill(6)
    fin_s, price_s = _partial_scores(sc)

    st.markdown(
        render_score_card(
            name=name,
            code=code,
            score=int(sc["attractiveness"]),
            grade=str(sc["grade"]),
            fin_score=fin_s,
            price_score=price_s,
            caption="통합 매력도 · 재무 + 주가 현위치",
        ),
        unsafe_allow_html=True,
    )

    badges = sc["badges"]
    price_items = [
        ("현재가", _price(row.get("current_price")), "해당없음"),
        ("저점대비", _pct(row.get("pct_from_low")), badges.get("pct_from_low", "해당없음")),
        ("52주위치", _pct(row.get("range_position")), badges.get("range_position", "해당없음")),
        ("바닥체류", _pct(row.get("bottom_dwell_ratio")), badges.get("bottom_dwell_ratio", "해당없음")),
        (
            "52주 범위",
            f"{_price(row.get('low_52w'))} ~ {_price(row.get('high_52w'))}"
            if pd.notna(row.get("low_52w"))
            else "-",
            "해당없음",
        ),
    ]
    st.markdown(render_metric_grid("주가 현위치", price_items), unsafe_allow_html=True)

    fin_items = []
    for key, label in [
        ("operating_margin", "영업이익률"),
        ("revenue_growth", "매출성장률"),
        ("revenue", "매출액"),
        ("roe", "ROE"),
        ("roa", "ROA"),
        ("current_ratio", "유동비율"),
        ("debt_ratio", "부채비율"),
        ("quick_ratio", "당좌비율"),
    ]:
        if key not in row.index:
            continue
        fin_items.append((label, format_cell(row, key), badges.get(key, "해당없음")))
    if fin_items:
        st.markdown(render_metric_grid("핵심 재무", fin_items), unsafe_allow_html=True)

    with st.expander("지표 평가 전체", expanded=False):
        for category in categories_order():
            st.markdown(f"**{category}**")
            for spec in specs_in_category(category):
                val = row.get(spec.key)
                badge = badges.get(spec.key, "해당없음")
                st.markdown(f"- **{spec.label}**: {_fmt_metric(spec.key, val)} — `{badge}`")

    with st.expander("주요 금액 · 재무제표", expanded=False):
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
            st.caption("원장 계정이 스냅샷에 없으면 지표·금액만 표시됩니다.")


def open_detail_for_row(row: pd.Series) -> None:
    data = row.drop(labels=[c for c in row.index if str(c).startswith("_")], errors="ignore").to_dict()
    detail_dialog(data)


def _partial_scores(sc: dict) -> tuple[str, str]:
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


def _price(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):,.0f}"


def _pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):.1f}"


def _fmt_metric(key: str, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    if key == "cash_flow_match":
        return f"{v * 100:.1f}%" if abs(v) < 20 else f"{v:.2f}"
    if key in (
        "cash_survival_years",
        "inventory_months",
        "cash_months",
        "inventory_turnover",
        "receivable_turnover",
    ):
        return f"{v:.2f}"
    return f"{v:.1f}"
