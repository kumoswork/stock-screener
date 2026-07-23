"""Detail modal — 한눈에 보이는 큰 글씨 레이아웃 (토글 없음)."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from criteria import BADGE_SCORE, PRICE_FILTER_KEYS, categories_order, score_row, specs_in_category
from screener import format_account_krw, format_cell
from ui_theme import GRADE_UI, grade_badge_html, status_html

DETAIL_READABLE_CSS = """
<style>
div[data-testid="stDialog"] {
  font-size: 1.05rem;
}
div[data-testid="stDialog"] h3 {
  font-size: 1.55rem !important;
  font-weight: 800 !important;
  margin-bottom: 0.4rem !important;
}
div[data-testid="stDialog"] h4 {
  font-size: 1.15rem !important;
  font-weight: 700 !important;
  margin: 0.85rem 0 0.45rem 0 !important;
}
</style>
"""


@st.dialog("종목 상세", width="large")
def detail_dialog(row_dict: dict) -> None:
    st.markdown(DETAIL_READABLE_CSS, unsafe_allow_html=True)

    row = pd.Series(_restore_row(row_dict))
    sc = score_row(row)
    name = str(row.get("corp_name", "") or "")
    code = str(row.get("stock_code", "") or "").zfill(6)
    score = int(sc["attractiveness"])
    grade = str(sc["grade"])
    grade_label = GRADE_UI.get(grade, (grade, "neutral"))[0]
    fin_s, price_s = _partial_scores(sc)
    badges = sc["badges"]

    # ---- 상단 요약 ----
    st.markdown(f"### {escape(name)}  ·  {code}")
    left, right = st.columns([2.3, 1.1])
    with left:
        st.markdown(
            f"<div style='color:#666;font-size:1rem;margin-bottom:0.2rem;'>통합 점수</div>"
            f"<div style='display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;'>"
            f"<span style='font-size:3rem;font-weight:800;line-height:1.05;'>{score}점</span>"
            f"<span style='font-size:1.05rem;'>{grade_badge_html(grade)}</span>"
            f"</div>"
            f"<div style='color:#666;font-size:0.95rem;margin-top:0.35rem;'>"
            f"등급 {escape(grade_label)} · 가중치 재무 60 : 주가 현위치 40</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"<div style='border:1px solid #ddd;border-radius:12px;padding:0.85rem 1rem;'>"
            f"<div style='color:#666;font-size:0.95rem;'>재무</div>"
            f"<div style='font-size:1.7rem;font-weight:800;margin:0.15rem 0 0.55rem 0;'>{escape(fin_s)}</div>"
            f"<div style='color:#666;font-size:0.95rem;'>주가 현위치</div>"
            f"<div style='font-size:1.7rem;font-weight:800;'>{escape(price_s)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ---- 카테고리별 지표 (전부 펼침) ----
    # 주가 관련 보조 타일 먼저
    price_extra = [
        ("현재가", _price(row.get("current_price")), "해당없음"),
        (
            "52주 저가/고가",
            f"{_price(row.get('low_52w'))} / {_price(row.get('high_52w'))}"
            if _has(row.get("low_52w"))
            else "-",
            "해당없음",
        ),
    ]

    for category in categories_order():
        st.markdown(f"#### {category}")
        tiles: list[tuple[str, str, str]] = []
        if category == "주가 현위치":
            tiles.extend(price_extra)
        for spec in specs_in_category(category):
            val = row.get(spec.key)
            if spec.key in ("revenue", "operating_profit", "net_income") or spec.key in row.index:
                display = (
                    format_cell(row, spec.key)
                    if spec.key in ("revenue", "operating_profit", "net_income", "current_price")
                    else _fmt_metric(spec.key, val)
                )
            else:
                display = _fmt_metric(spec.key, val)
            tiles.append((spec.label, display, badges.get(spec.key, "해당없음")))
        _render_metric_tiles(tiles)

    # ---- 절대 금액 요약 ----
    abs_tiles = []
    for key, label in [
        ("revenue", "매출액"),
        ("operating_profit", "영업이익"),
        ("net_income", "당기순이익"),
    ]:
        if key in row.index and _has(row.get(key)):
            abs_tiles.append((label, format_cell(row, key), "해당없음"))
    if abs_tiles:
        st.markdown("#### 손익 요약")
        _render_metric_tiles(abs_tiles)

    # ---- 재무제표 계정 (토글 없이 전부 표시) ----
    st.markdown("#### 주요 금액 · 재무제표")
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
    shown_accounts = [(lab, format_account_krw(row.get(k))) for k, lab in account_rows if k in row.index and _has(row.get(k))]
    if shown_accounts:
        _render_account_rows(shown_accounts)
    else:
        st.markdown(
            "<div style='font-size:1rem;color:#666;'>원장 계정이 스냅샷에 없으면 위 지표·금액만 표시됩니다.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div style='font-size:0.95rem;color:#666;margin-top:0.6rem;'>"
        "뱃지: 매우우수/양호=녹색 · 주의/약세=빨강</div>",
        unsafe_allow_html=True,
    )


def _render_metric_tiles(items: list[tuple[str, str, str]]) -> None:
    cols_per_row = 4
    for i in range(0, len(items), cols_per_row):
        chunk = items[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (lab, val, badge) in zip(cols, chunk):
            with col:
                st.markdown(
                    f"<div style='border:1px solid #d0d4dc;border-radius:12px;"
                    f"padding:0.85rem 0.9rem;background:#f7f8fb;min-height:110px;'>"
                    f"<div style='color:#5c6575;font-size:0.92rem;margin-bottom:0.35rem;font-weight:600;'>"
                    f"{escape(lab)}</div>"
                    f"<div style='color:#111;font-size:1.35rem;font-weight:800;margin-bottom:0.4rem;"
                    f"line-height:1.25;'>{escape(str(val))}</div>"
                    f"<div style='font-size:0.95rem;'>{status_html(badge)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _render_account_rows(rows: list[tuple[str, str]]) -> None:
    # 2열로 계정/금액 표시
    for i in range(0, len(rows), 2):
        chunk = rows[i : i + 2]
        cols = st.columns(2)
        for col, (lab, val) in zip(cols, chunk):
            with col:
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"border-bottom:1px solid #e4e7ee;padding:0.55rem 0.15rem;'>"
                    f"<span style='font-size:1.05rem;color:#333;'>{escape(lab)}</span>"
                    f"<span style='font-size:1.15rem;font-weight:700;'>{escape(val)}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def open_detail_for_row(row: pd.Series) -> None:
    raw = row.drop(labels=[c for c in row.index if str(c).startswith("_")], errors="ignore")
    detail_dialog(_json_safe(raw.to_dict()))


def _json_safe(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        if v is None:
            out[str(k)] = None
            continue
        try:
            if pd.isna(v):
                out[str(k)] = None
                continue
        except (TypeError, ValueError):
            pass
        if hasattr(v, "item"):
            try:
                v = v.item()
            except Exception:
                pass
        if isinstance(v, float) and (v != v):
            out[str(k)] = None
        else:
            out[str(k)] = v
    return out


def _restore_row(row_dict: dict) -> dict:
    return {k: (None if v == "" else v) for k, v in row_dict.items()}


def _has(v) -> bool:
    if v is None:
        return False
    try:
        return not pd.isna(v)
    except (TypeError, ValueError):
        return True


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
    if not _has(v):
        return "-"
    return f"{float(v):,.0f}"


def _fmt_metric(key: str, v) -> str:
    if not _has(v):
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
