"""Detail modal — Streamlit-native layout (dialog-safe)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from criteria import BADGE_SCORE, PRICE_FILTER_KEYS, categories_order, score_row, specs_in_category
from screener import format_account_krw, format_cell
from ui_theme import GRADE_UI, grade_badge_html, status_html


@st.dialog("종목 상세", width="large")
def detail_dialog(row_dict: dict) -> None:
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
    st.markdown(f"### {name}  ·  `{code}`")
    left, right = st.columns([2.2, 1.0])
    with left:
        st.caption("통합 점수")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:0.6rem;'>"
            f"<span style='font-size:2.4rem;font-weight:800;line-height:1;'>{score}점</span>"
            f"{grade_badge_html(grade)}"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.caption("가중치: 재무 60 : 주가 현위치 40")
    with right:
        st.caption("재무")
        st.markdown(f"**{fin_s}**")
        st.caption("주가 현위치")
        st.markdown(f"**{price_s}**")

    st.divider()
    st.markdown(f"**핵심 지표 · {score}점 ({grade_label})**")

    items: list[tuple[str, str, str]] = [
        ("현재가", _price(row.get("current_price")), "해당없음"),
        ("저점대비(%)", _pct(row.get("pct_from_low")), badges.get("pct_from_low", "해당없음")),
        ("52주위치(%)", _pct(row.get("range_position")), badges.get("range_position", "해당없음")),
        ("바닥체류(%)", _pct(row.get("bottom_dwell_ratio")), badges.get("bottom_dwell_ratio", "해당없음")),
        (
            "52주 저/고",
            f"{_price(row.get('low_52w'))} / {_price(row.get('high_52w'))}"
            if _has(row.get("low_52w"))
            else "-",
            "해당없음",
        ),
    ]
    for key, label in [
        ("operating_margin", "영업이익률(%)"),
        ("revenue_growth", "매출성장률(%)"),
        ("revenue", "매출액"),
        ("roe", "ROE(%)"),
        ("current_ratio", "유동비율(%)"),
        ("debt_ratio", "부채비율(%)"),
        ("roa", "ROA(%)"),
        ("quick_ratio", "당좌비율(%)"),
        ("operating_profit", "영업이익"),
        ("net_income", "당기순이익"),
    ]:
        if key not in row.index or not _has(row.get(key)):
            continue
        items.append((label, format_cell(row, key), badges.get(key, "해당없음")))

    _render_metric_tiles(items[:15])
    st.caption("뱃지: 매우우수/양호=녹색 · 주의/약세=빨강")

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
            if k in row.index and _has(row.get(k)):
                st.write(f"- **{lab}**: {format_account_krw(row.get(k))}")
                shown += 1
        if shown < 3:
            st.caption("원장 계정이 스냅샷에 없으면 지표·금액만 표시됩니다.")


def _render_metric_tiles(items: list[tuple[str, str, str]]) -> None:
    """5열 타일. 복잡한 HTML 카드 대신 columns + 짧은 마크다운."""
    cols_per_row = 5
    for i in range(0, len(items), cols_per_row):
        chunk = items[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (lab, val, badge) in zip(cols, chunk):
            with col:
                st.markdown(
                    f"<div style='border:1px solid #2a3348;border-radius:10px;"
                    f"padding:0.65rem 0.7rem;background:#151b2b;min-height:92px;'>"
                    f"<div style='color:#8b95a8;font-size:0.75rem;margin-bottom:0.25rem;'>{lab}</div>"
                    f"<div style='color:#f2f5fa;font-size:1.05rem;font-weight:700;margin-bottom:0.25rem;'>{val}</div>"
                    f"<div style='font-size:0.78rem;'>{status_html(badge)}</div>"
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


def _pct(v) -> str:
    if not _has(v):
        return "-"
    return f"{float(v):.1f}"


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
