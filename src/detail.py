"""Detail modal — 점수+뱃지 상단, 카테고리 순서 고정, 6열 카드."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from criteria import score_row, specs_in_category
from screener import format_account_krw, format_cell
from ui_theme import GRADE_UI, grade_badge_html, status_html

DETAIL_READABLE_CSS = """
<style>
div[data-testid="stDialog"] h3 {
  font-size: 1.55rem !important;
  font-weight: 800 !important;
  margin-bottom: 0.35rem !important;
}
div[data-testid="stDialog"] h4 {
  font-size: 1.12rem !important;
  font-weight: 700 !important;
  margin: 0.9rem 0 0.4rem 0 !important;
}
</style>
"""

# 표시 제목, 내부 category 키 (None이면 특수 섹션)
DETAIL_SECTION_ORDER: list[tuple[str, str | None]] = [
    ("주가 현위치", "주가 현위치"),
    ("손익 요약", None),
    ("B경제", "B경제"),
    ("안전성", "안전성 check!"),
    ("수익/성장성", "수익/성장성 check!"),
    ("효율성", "효율성 check!"),
    ("매출증가율−부채증가율", "check!!"),
]


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
    badges = sc["badges"]

    # ---- 상단: 점수 + 뱃지만 ----
    st.markdown(f"### {escape(name)}  ·  {code}")
    st.markdown(
        f"<div style='color:#666;font-size:1rem;margin-bottom:0.15rem;'>통합 점수</div>"
        f"<div style='display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;'>"
        f"<span style='font-size:3rem;font-weight:800;line-height:1.05;'>{score}점</span>"
        f"<span style='font-size:1.05rem;'>{grade_badge_html(grade)}</span>"
        f"</div>"
        f"<div style='color:#666;font-size:0.95rem;margin-top:0.3rem;'>등급 {escape(grade_label)}</div>",
        unsafe_allow_html=True,
    )

    for title, cat_key in DETAIL_SECTION_ORDER:
        st.markdown(f"#### {title}")
        if cat_key is None:
            # 손익 요약
            tiles = []
            for key, label in [
                ("revenue", "매출액"),
                ("operating_profit", "영업이익"),
                ("net_income", "당기순이익"),
            ]:
                if key in row.index and _has(row.get(key)):
                    tiles.append((label, format_cell(row, key), "해당없음"))
            if not tiles:
                st.caption("데이터 없음")
            else:
                _render_metric_tiles(tiles)
            continue

        tiles = []
        if cat_key == "주가 현위치":
            tiles.append(("현재가", _price(row.get("current_price")), "해당없음"))
            if _has(row.get("range_position")):
                tiles.append(
                    ("52주위치(%)", _fmt_metric("range_position", row.get("range_position")), "해당없음")
                )
            if _has(row.get("low_52w")):
                tiles.append(
                    (
                        "52주 저가/고가",
                        f"{_price(row.get('low_52w'))} / {_price(row.get('high_52w'))}",
                        "해당없음",
                    )
                )

        for spec in specs_in_category(cat_key):
            val = row.get(spec.key)
            display = _fmt_metric(spec.key, val)
            tiles.append((spec.label, display, badges.get(spec.key, "해당없음")))

        if tiles:
            _render_metric_tiles(tiles)
        else:
            st.caption("데이터 없음")

    # 재무제표 계정 (맨 아래)
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
    shown_accounts = [
        (lab, format_account_krw(row.get(k)))
        for k, lab in account_rows
        if k in row.index and _has(row.get(k))
    ]
    if shown_accounts:
        _render_account_rows(shown_accounts)
    else:
        st.caption("원장 계정이 스냅샷에 없으면 위 지표·금액만 표시됩니다.")


def _render_metric_tiles(items: list[tuple[str, str, str]]) -> None:
    cols_per_row = 6
    for i in range(0, len(items), cols_per_row):
        chunk = items[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (lab, val, badge) in zip(cols, chunk):
            with col:
                # 배경색 없이 기본 톤 + 얇은 구분만
                st.markdown(
                    f"<div style='border:1px solid rgba(49,51,63,0.2);border-radius:10px;"
                    f"padding:0.7rem 0.55rem;min-height:100px;'>"
                    f"<div style='font-size:0.88rem;margin-bottom:0.3rem;opacity:0.75;font-weight:600;'>"
                    f"{escape(lab)}</div>"
                    f"<div style='font-size:1.2rem;font-weight:800;margin-bottom:0.35rem;line-height:1.25;'>"
                    f"{escape(str(val))}</div>"
                    f"<div style='font-size:0.9rem;'>{status_html(badge)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def _render_account_rows(rows: list[tuple[str, str]]) -> None:
    for i in range(0, len(rows), 2):
        chunk = rows[i : i + 2]
        cols = st.columns(2)
        for col, (lab, val) in zip(cols, chunk):
            with col:
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"border-bottom:1px solid rgba(49,51,63,0.15);padding:0.5rem 0.1rem;'>"
                    f"<span style='font-size:1.02rem;'>{escape(lab)}</span>"
                    f"<span style='font-size:1.1rem;font-weight:700;'>{escape(val)}</span>"
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
