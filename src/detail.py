"""Detail modal — soft gray cards, fixed section order, 6 columns."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from criteria import score_row, specs_in_category
from screener import format_cell
from ui_theme import GRADE_UI

DETAIL_READABLE_CSS = """
<style>
div[data-testid="stDialog"] h3 {
  font-size: 1.5rem !important;
  font-weight: 800 !important;
  color: #1f2937 !important;
  margin-bottom: 0.3rem !important;
}
div[data-testid="stDialog"] h4 {
  font-size: 1.08rem !important;
  font-weight: 700 !important;
  color: #374151 !important;
  margin: 1rem 0 0.45rem 0 !important;
  border-left: 3px solid #94a3b8;
  padding-left: 0.55rem;
}
</style>
"""

DETAIL_SECTION_ORDER: list[tuple[str, str | None]] = [
    ("주가 현위치", "주가 현위치"),
    ("손익 요약", None),
    ("B경제", "B경제"),
    ("안전성", "안전성 check!"),
    ("수익/성장성", "수익/성장성 check!"),
    ("효율성", "효율성 check!"),
    ("매출증가율−부채증가율", "check!!"),
]

# 라이트 그레이 테마용 뱃지 스타일
_GRADE_STYLE = {
    "A": ("적극 관심", "#dcfce7", "#15803d"),
    "B": ("관심", "#dbeafe", "#1d4ed8"),
    "C": ("보통", "#e5e7eb", "#4b5563"),
    "D": ("주의", "#fee2e2", "#b91c1c"),
}
_STATUS_STYLE = {
    "매우우수": ("매우우수", "#dcfce7", "#15803d"),
    "우수": ("양호", "#dcfce7", "#16a34a"),
    "보통": ("보통", "#e5e7eb", "#6b7280"),
    "주의": ("주의", "#ffedd5", "#c2410c"),
    "위험": ("약세", "#fee2e2", "#b91c1c"),
    "해당없음": ("—", "#f3f4f6", "#9ca3af"),
}


def _pill(label: str, bg: str, fg: str) -> str:
    return (
        f"<span style='display:inline-block;padding:0.15rem 0.55rem;border-radius:999px;"
        f"background:{bg};color:{fg};font-size:0.82rem;font-weight:700;'>"
        f"{escape(label)}</span>"
    )


def _grade_pill(grade: str) -> str:
    label = GRADE_UI.get(str(grade), (str(grade), ""))[0]
    _, bg, fg = _GRADE_STYLE.get(str(grade), (label, "#e5e7eb", "#4b5563"))
    return _pill(label, bg, fg)


def _status_pill(badge: str) -> str:
    label, bg, fg = _STATUS_STYLE.get(badge, (badge or "—", "#f3f4f6", "#9ca3af"))
    return _pill(label, bg, fg)


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

    # ---- 상단 요약 카드 ----
    st.markdown(
        f"<div style='background:#e5e7eb;border:1px solid #d1d5db;border-radius:14px;"
        f"padding:1rem 1.15rem;margin-bottom:0.35rem;'>"
        f"<div style='font-size:1.25rem;font-weight:800;color:#111827;margin-bottom:0.45rem;'>"
        f"{escape(name)} <span style='color:#6b7280;font-weight:600;font-size:1.05rem;'>{code}</span></div>"
        f"<div style='color:#6b7280;font-size:0.92rem;margin-bottom:0.1rem;'>통합 점수</div>"
        f"<div style='display:flex;align-items:center;gap:0.7rem;flex-wrap:wrap;'>"
        f"<span style='font-size:2.75rem;font-weight:800;line-height:1;color:#111827;'>{score}점</span>"
        f"{_grade_pill(grade)}"
        f"</div>"
        f"<div style='color:#6b7280;font-size:0.9rem;margin-top:0.35rem;'>등급 {escape(grade_label)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for title, cat_key in DETAIL_SECTION_ORDER:
        st.markdown(f"#### {title}")
        if cat_key is None:
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
            tiles.append(
                (spec.label, _fmt_metric(spec.key, row.get(spec.key)), badges.get(spec.key, "해당없음"))
            )

        if tiles:
            _render_metric_tiles(tiles)
        else:
            st.caption("데이터 없음")


def _render_metric_tiles(items: list[tuple[str, str, str]]) -> None:
    cols_per_row = 6
    for i in range(0, len(items), cols_per_row):
        chunk = items[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (lab, val, badge) in zip(cols, chunk):
            with col:
                st.markdown(
                    f"<div style='background:#e8eaee;border:1px solid #d5d8de;border-radius:12px;"
                    f"padding:0.75rem 0.6rem;min-height:104px;"
                    f"box-shadow:0 1px 2px rgba(15,23,42,0.04);'>"
                    f"<div style='font-size:0.86rem;margin-bottom:0.3rem;color:#6b7280;font-weight:600;'>"
                    f"{escape(lab)}</div>"
                    f"<div style='font-size:1.18rem;font-weight:800;margin-bottom:0.4rem;"
                    f"line-height:1.25;color:#111827;'>{escape(str(val))}</div>"
                    f"<div>{_status_pill(badge)}</div>"
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
