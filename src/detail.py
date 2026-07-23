"""Detail modal — dark-gray dialog bg, original dark cards, 6 columns."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from criteria import CATEGORY_LABELS, CATEGORY_WEIGHTS, score_row, specs_in_category
from screener import format_cell, format_metric_value
from ui_theme import GRADE_UI

DETAIL_READABLE_CSS = """
<style>
/* 상세 모달 배경만 다크그레이 — 카드는 건드리지 않음 */
div[data-testid="stDialog"] > div,
section[data-testid="stDialog"] > div,
div[role="dialog"] {
  background-color: #2f343c !important;
}
div[data-testid="stDialog"] h3,
div[data-testid="stDialog"] h4 {
  color: #e8eaed !important;
}
div[data-testid="stDialog"] h3 {
  font-size: 1.5rem !important;
  font-weight: 800 !important;
  margin-bottom: 0.3rem !important;
}
div[data-testid="stDialog"] h4 {
  font-size: 1.08rem !important;
  font-weight: 700 !important;
  margin: 1rem 0 0.45rem 0 !important;
  border-left: 3px solid #7d8590;
  padding-left: 0.55rem;
}
div[data-testid="stDialog"] .stCaption,
div[data-testid="stDialog"] [data-testid="stMarkdownContainer"] p {
  color: #b0b6c0 !important;
}
.ks-cat-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 0.45rem 0;
}
.ks-cat-title {
  flex: 0 0 auto;
  color: #e8eaed;
  font-size: 1.08rem;
  font-weight: 700;
  border-left: 3px solid #7d8590;
  padding-left: 0.55rem;
  white-space: nowrap;
}
.ks-cat-line {
  flex: 1 1 auto;
  height: 1px;
  background: #5a6578;
  min-width: 1.5rem;
  max-width: calc(90% - 6.5rem);
}
.ks-cat-score {
  position: absolute;
  left: 90%;
  transform: translateX(-50%);
  color: #c5cddc;
  font-size: 0.95rem;
  font-weight: 700;
  white-space: nowrap;
}
.ks-cat-chips {
  display: flex;
  gap: 0.85rem;
  flex-wrap: wrap;
  margin-top: 0.85rem;
  padding-top: 0.75rem;
  border-top: 1px solid #2a3348;
  row-gap: 0.65rem;
}
.ks-cat-chip {
  min-width: 4.6rem;
}
.ks-detail-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.55rem;
  margin-bottom: 0.25rem;
}
.ks-detail-tile {
  background: #121826;
  border: 1px solid #2a3348;
  border-radius: 12px;
  padding: 0.75rem 0.6rem;
  min-height: 104px;
  box-sizing: border-box;
}
.ks-detail-tile .lab {
  font-size: 0.86rem;
  margin-bottom: 0.3rem;
  color: #8b95a8;
  font-weight: 600;
}
.ks-detail-tile .val {
  font-size: 1.18rem;
  font-weight: 800;
  margin-bottom: 0.4rem;
  line-height: 1.25;
  color: #f2f5fa;
  word-break: break-word;
}
@media (max-width: 768px) {
  .ks-detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.45rem;
  }
  .ks-detail-tile {
    padding: 0.65rem 0.5rem;
    min-height: 92px;
  }
  .ks-detail-tile .lab { font-size: 0.78rem; }
  .ks-detail-tile .val { font-size: 1.05rem; }
  .ks-cat-chips {
    gap: 0.55rem 0.7rem;
    row-gap: 0.55rem;
    margin-top: 0.7rem;
    padding-top: 0.65rem;
  }
  .ks-cat-chip {
    min-width: 4.1rem;
    flex: 1 1 calc(33.33% - 0.7rem);
  }
  .ks-cat-head {
    gap: 0.45rem;
  }
  div[data-testid="stDialog"] > div,
  section[data-testid="stDialog"] > div,
  div[role="dialog"] {
    padding-left: 0.55rem !important;
    padding-right: 0.55rem !important;
  }
  div[data-testid="stDialog"] [data-testid="stMarkdownContainer"],
  section[data-testid="stDialog"] [data-testid="stMarkdownContainer"] {
    padding-left: 0 !important;
    padding-right: 0 !important;
  }
}
</style>
"""

DETAIL_SECTION_ORDER: list[tuple[str, str | None]] = [
    ("손익 요약", None),
    ("주가 현위치", "주가 현위치"),
    ("B경제", "B경제"),
    ("안전성", "안전성 check!"),
    ("수익/성장성", "수익/성장성 check!"),
    ("효율성", "효율성 check!"),
    ("매출증가율−부채증가율", "check!!"),
]

_GRADE_STYLE = {
    "A": ("적극 관심", "rgba(61,214,140,0.18)", "#3dd68c"),
    "B": ("관심", "rgba(76,139,245,0.18)", "#7eb6ff"),
    "C": ("보통", "rgba(155,165,184,0.18)", "#b0b8c8"),
    "D": ("주의", "rgba(240,113,120,0.18)", "#f07178"),
}
_STATUS_STYLE = {
    "매우우수": ("매우우수", "transparent", "#3dd68c"),
    "우수": ("우수", "transparent", "#3dd68c"),
    "보통": ("양호", "transparent", "#3dd68c"),
    "주의": ("주의", "rgba(240,113,120,0.16)", "#f07178"),
    "위험": ("약세", "rgba(240,113,120,0.16)", "#f07178"),
    "해당없음": ("—", "transparent", "#6b7385"),
}


def _pill(label: str, bg: str, fg: str) -> str:
    pad = "0.15rem 0.5rem" if bg != "transparent" else "0"
    return (
        f"<span style='display:inline-block;padding:{pad};border-radius:999px;"
        f"background:{bg};color:{fg};font-size:0.82rem;font-weight:700;'>"
        f"{escape(label)}</span>"
    )


def _grade_pill(grade: str) -> str:
    label = GRADE_UI.get(str(grade), (str(grade), ""))[0]
    _, bg, fg = _GRADE_STYLE.get(str(grade), (label, "rgba(155,165,184,0.18)", "#b0b8c8"))
    return _pill(label, bg, fg)


def _status_pill(badge: str) -> str:
    label, bg, fg = _STATUS_STYLE.get(badge, (badge or "—", "transparent", "#6b7385"))
    return _pill(label, bg, fg)


def _category_header(title: str, score: int | None, *, show_score: bool = True) -> str:
    if show_score:
        score_html = f"{int(score)}점" if score is not None else "—"
    else:
        score_html = ""
    # Streamlit이 class CSS를 가끔 무시해서 핵심 레이아웃은 인라인으로 고정
    # 점수는 행 너비의 약 90% 지점 (끝보다 살짝 안쪽)
    score_block = ""
    line_max = "100%"
    if show_score:
        line_max = "calc(90% - 6.5rem)"
        score_block = (
            f"<div class='ks-cat-score' style='position:absolute;left:90%;"
            f"transform:translateX(-50%);color:#c5cddc;font-size:0.95rem;"
            f"font-weight:700;white-space:nowrap;'>{escape(score_html)}</div>"
        )
    return (
        f"<div class='ks-cat-head' style='position:relative;display:flex;align-items:center;"
        f"gap:0.75rem;margin:1rem 0 0.45rem 0;'>"
        f"<div class='ks-cat-title' style='flex:0 0 auto;color:#e8eaed;font-size:1.08rem;"
        f"font-weight:700;border-left:3px solid #7d8590;padding-left:0.55rem;"
        f"white-space:nowrap;'>{escape(title)}</div>"
        f"<div class='ks-cat-line' style='flex:1 1 auto;height:1px;background:#5a6578;"
        f"min-width:1.5rem;max-width:{line_max};'></div>"
        f"{score_block}"
        f"</div>"
    )


@st.dialog("종목 상세", width="large")
def detail_dialog(stock_code: str) -> None:
    st.markdown(DETAIL_READABLE_CSS, unsafe_allow_html=True)

    row = _load_detail_row(stock_code)
    if row is None:
        st.error(f"종목 데이터를 찾을 수 없습니다 ({stock_code})")
        return

    sc = score_row(row)
    name = str(row.get("corp_name", "") or "")
    code = str(row.get("stock_code", "") or "").zfill(6)
    score = int(sc["attractiveness"])
    grade = str(sc["grade"])
    grade_label = GRADE_UI.get(grade, (grade, "neutral"))[0]
    badges = sc["badges"]
    cat_scores: dict = sc.get("category_scores") or {}

    # 상세 섹션과 같은 순서로 카테고리 점수 칩 배치
    cat_chips = []
    for title, cat_key in DETAIL_SECTION_ORDER:
        if not cat_key:
            continue
        label = CATEGORY_LABELS.get(cat_key, title)
        cs = cat_scores.get(cat_key)
        val = f"{int(cs)}" if cs is not None else "—"
        pct = int(round(CATEGORY_WEIGHTS.get(cat_key, 0) * 100))
        cat_chips.append(
            f"<div class='ks-cat-chip' style='min-width:4.6rem;'>"
            f"<div style='color:#8b95a8;font-size:0.72rem;'>{escape(label)} · {pct}%</div>"
            f"<div style='color:#e8eaed;font-size:1.05rem;font-weight:700;'>{val}</div>"
            f"</div>"
        )
    cat_row = (
        "<div class='ks-cat-chips' style='display:flex;gap:0.85rem;flex-wrap:wrap;"
        "margin-top:0.85rem;padding-top:0.75rem;border-top:1px solid #2a3348;'>"
        + "".join(cat_chips)
        + "</div>"
    )

    # 상단: 점수 + 카테고리 소점수
    st.markdown(
        f"<div style='background:#151b2b;border:1px solid #2a3348;border-radius:14px;"
        f"padding:1rem 1.15rem;margin-bottom:0.35rem;'>"
        f"<div style='font-size:1.2rem;font-weight:800;color:#f2f5fa;margin-bottom:0.4rem;'>"
        f"{escape(name)} <span style='color:#8b95a8;font-weight:500;font-size:1rem;'>{code}</span></div>"
        f"<div style='color:#8b95a8;font-size:0.9rem;margin-bottom:0.1rem;'>통합 점수 (카테고리 가중)</div>"
        f"<div style='display:flex;align-items:center;gap:0.7rem;flex-wrap:wrap;'>"
        f"<span style='font-size:2.75rem;font-weight:800;line-height:1;color:#fff;'>{score}점</span>"
        f"{_grade_pill(grade)}"
        f"</div>"
        f"<div style='color:#8b95a8;font-size:0.88rem;margin-top:0.35rem;'>등급 {escape(grade_label)}</div>"
        f"{cat_row}"
        f"</div>",
        unsafe_allow_html=True,
    )

    for title, cat_key in DETAIL_SECTION_ORDER:
        cat_score = cat_scores.get(cat_key) if cat_key else None
        st.markdown(
            _category_header(title, cat_score, show_score=cat_key is not None),
            unsafe_allow_html=True,
        )
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
                    (
                        "52주위치(%)",
                        format_metric_value("range_position", row.get("range_position")),
                        "해당없음",
                    )
                )
            if _has(row.get("low_52w")):
                tiles.append(
                    (
                        "52주 저가/고가",
                        f"{_price(row.get('low_52w'))} / {_price(row.get('high_52w'))}",
                        "해당없음",
                    )
                )

        # B경제: 판관비율(절대)도 함께 표시 — 전년대비와 혼동 방지
        if cat_key == "B경제" and _has(row.get("sga_ratio")):
            tiles.append(
                (
                    "판관비율(판관비÷매출)",
                    format_metric_value("sga_ratio", row.get("sga_ratio")),
                    "해당없음",
                )
            )

        for spec in specs_in_category(cat_key):
            tiles.append(
                (
                    spec.label,
                    format_metric_value(spec.key, row.get(spec.key)),
                    badges.get(spec.key, "해당없음"),
                )
            )

        if tiles:
            _render_metric_tiles(tiles)
        else:
            st.caption("데이터 없음")


def _load_detail_row(stock_code: str) -> pd.Series | None:
    """상세는 항상 최신 재무 스냅샷을 다시 읽고, 주가 필드는 최근 결과에서 보강."""
    from snapshot import load_financials

    code = str(stock_code).zfill(6)
    fin = load_financials()
    if fin.empty or "stock_code" not in fin.columns:
        return None
    fin = fin.copy()
    fin["stock_code"] = fin["stock_code"].astype(str).str.zfill(6)
    hit = fin[fin["stock_code"] == code]
    if hit.empty:
        return None
    row = hit.iloc[0].copy()

    # 주가·점수 등은 방금 조회한 결과에서 덮어씀
    cached = st.session_state.get("last_result")
    if isinstance(cached, pd.DataFrame) and not cached.empty and "stock_code" in cached.columns:
        tmp = cached.copy()
        tmp["stock_code"] = tmp["stock_code"].astype(str).str.zfill(6)
        c_hit = tmp[tmp["stock_code"] == code]
        if not c_hit.empty:
            overlay = c_hit.iloc[0]
            for col in (
                "current_price",
                "low_52w",
                "high_52w",
                "pct_from_low",
                "range_position",
                "bottom_dwell_ratio",
            ):
                if col in overlay.index and _has(overlay.get(col)):
                    row[col] = overlay[col]
    return row


def _render_metric_tiles(items: list[tuple[str, str, str]]) -> None:
    """다크 카드 타일 — 데스크톱 6열, 모바일 2열(CSS)."""
    cards = []
    for lab, val, badge in items:
        cards.append(
            f"<div class='ks-detail-tile'>"
            f"<div class='lab'>{escape(lab)}</div>"
            f"<div class='val'>{escape(str(val))}</div>"
            f"<div>{_status_pill(badge)}</div>"
            f"</div>"
        )
    st.markdown(
        f"<div class='ks-detail-grid'>{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def open_detail_for_row(row: pd.Series) -> None:
    code = str(row.get("stock_code", "")).zfill(6)
    detail_dialog(code)


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
