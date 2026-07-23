"""List / detail UI helpers (cards, table, badges). Does not restyle the sidebar."""

from __future__ import annotations

from html import escape

import pandas as pd

GRADE_UI = {
    "A": ("적극 관심", "hot"),
    "B": ("관심", "watch"),
    "C": ("보통", "neutral"),
    "D": ("주의", "warn"),
}

BADGE_STATUS = {
    "매우우수": ("매우우수", "good"),
    "우수": ("양호", "good"),
    "보통": ("보통", "muted"),
    "주의": ("주의", "bad"),
    "위험": ("약세", "bad"),
    "해당없음": ("—", "muted"),
}


LIST_DETAIL_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

.ks-wrap, .ks-wrap * {
  font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
}

.ks-status {
  color: #6b7385;
  font-size: 0.9rem;
  margin: 0.2rem 0 0.55rem 0;
}
.ks-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  vertical-align: middle;
}
.ks-badge.hot { background: rgba(61,214,140,0.16); color: #3dd68c; }
.ks-badge.watch { background: rgba(61,214,140,0.14); color: #3dd68c; }
.ks-badge.neutral { background: rgba(155,165,184,0.14); color: #b0b8c8; }
.ks-badge.warn { background: rgba(240,113,120,0.14); color: #f07178; }
.ks-badge.good { color: #3dd68c; background: transparent; font-weight: 600; padding: 0; }
.ks-badge.bad {
  background: rgba(240,113,120,0.16);
  color: #f07178;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}
.ks-badge.muted { color: #6b7385; background: transparent; padding: 0; }
</style>
"""

# components.html 안에서만 쓰는 카드/그리드 스타일 (dialog 레이아웃은 건드리지 않음)
DETAIL_CARD_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
html, body {
  margin: 0;
  padding: 0;
  background: transparent;
  font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
  color: #e8ecf4;
}
.ks-wrap { width: 100%; box-sizing: border-box; }
.ks-card {
  background: #151b2b;
  border: 1px solid #2a3348;
  border-radius: 14px;
  padding: 1.1rem 1.2rem;
  margin: 0 0 0.75rem 0;
  color: #e8ecf4;
  box-sizing: border-box;
}
.ks-score-row {
  display: flex;
  justify-content: space-between;
  gap: 1.2rem;
  flex-wrap: wrap;
  align-items: flex-start;
}
.ks-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: #f2f5fa;
  margin-bottom: 0.5rem;
}
.ks-title .code {
  color: #8b95a8;
  font-weight: 500;
  font-size: 0.95rem;
  margin-left: 0.35rem;
}
.ks-score-label {
  color: #8b95a8;
  font-size: 0.8rem;
  margin-bottom: 0.12rem;
}
.ks-score-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.ks-score {
  font-size: 2.4rem;
  font-weight: 800;
  color: #fff;
  line-height: 1.05;
}
.ks-sub {
  color: #8b95a8;
  font-size: 0.8rem;
  margin-top: 0.4rem;
}
.ks-side { min-width: 140px; text-align: right; }
.ks-side-item { margin-bottom: 0.5rem; }
.ks-side-label { color: #8b95a8; font-size: 0.78rem; margin-bottom: 0.08rem; }
.ks-side-val { color: #7eb6ff; font-size: 1.25rem; font-weight: 700; }

.ks-badge {
  display: inline-block;
  padding: 0.18rem 0.55rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 700;
  vertical-align: middle;
}
.ks-badge.hot { background: rgba(61,214,140,0.16); color: #3dd68c; }
.ks-badge.watch { background: rgba(61,214,140,0.14); color: #3dd68c; }
.ks-badge.neutral { background: rgba(155,165,184,0.14); color: #b0b8c8; }
.ks-badge.warn { background: rgba(240,113,120,0.14); color: #f07178; }
.ks-badge.good { color: #3dd68c; background: transparent; font-weight: 600; padding: 0; }
.ks-badge.bad {
  background: rgba(240,113,120,0.16);
  color: #f07178;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
}
.ks-badge.muted { color: #6b7385; background: transparent; padding: 0; }

.ks-section-title {
  color: #e8ecf4;
  font-weight: 700;
  font-size: 0.95rem;
  margin: 0 0 0.7rem 0;
}
.ks-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.55rem;
}
@media (max-width: 900px) {
  .ks-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .ks-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.ks-metric {
  background: #121826;
  border: 1px solid #2a3348;
  border-radius: 12px;
  padding: 0.7rem 0.75rem;
  min-height: 90px;
  box-sizing: border-box;
}
.ks-metric .lab { color: #8b95a8; font-size: 0.74rem; margin-bottom: 0.3rem; }
.ks-metric .val {
  color: #f2f5fa;
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
  word-break: break-word;
}
.ks-metric .stat { font-size: 0.78rem; min-height: 1rem; }
.ks-foot {
  color: #6b7385;
  font-size: 0.75rem;
  margin-top: 0.65rem;
}
</style>
"""


def inject_list_detail_css() -> None:
    import streamlit as st

    st.markdown(LIST_DETAIL_CSS, unsafe_allow_html=True)


def grade_badge_html(grade: str) -> str:
    label, cls = GRADE_UI.get(str(grade), (str(grade), "neutral"))
    return f'<span class="ks-badge {cls}">{escape(label)}</span>'


def status_html(badge: str) -> str:
    label, cls = BADGE_STATUS.get(badge, (badge or "", "muted"))
    if not label:
        return ""
    return f'<span class="ks-badge {cls}">{escape(label)}</span>'


def render_score_card(
    name: str,
    code: str,
    score: int,
    grade: str,
    fin_score: str,
    price_score: str,
    caption: str,
) -> str:
    badge = grade_badge_html(grade)
    return f"""
    <div class="ks-wrap"><div class="ks-card">
      <div class="ks-score-row">
        <div>
          <div class="ks-title">{escape(name)}<span class="code">{escape(code)}</span></div>
          <div class="ks-score-label">통합 점수</div>
          <div class="ks-score-line">
            <span class="ks-score">{int(score)}점</span>
            {badge}
          </div>
          <div class="ks-sub">{escape(caption)}</div>
        </div>
        <div class="ks-side">
          <div class="ks-side-item">
            <div class="ks-side-label">재무</div>
            <div class="ks-side-val">{escape(fin_score)}</div>
          </div>
          <div class="ks-side-item">
            <div class="ks-side-label">주가 현위치</div>
            <div class="ks-side-val">{escape(price_score)}</div>
          </div>
        </div>
      </div>
    </div></div>
    """


def render_metric_grid(title: str, items: list[tuple[str, str, str]], footer: str = "") -> str:
    cards = []
    for lab, val, badge in items:
        cards.append(
            f"""
            <div class="ks-metric">
              <div class="lab">{escape(lab)}</div>
              <div class="val">{escape(val)}</div>
              <div class="stat">{status_html(badge)}</div>
            </div>
            """
        )
    foot = f'<div class="ks-foot">{escape(footer)}</div>' if footer else ""
    return f"""
    <div class="ks-wrap"><div class="ks-card">
      <div class="ks-section-title">{escape(title)}</div>
      <div class="ks-grid">{''.join(cards)}</div>
      {foot}
    </div></div>
    """


def render_result_table(df: pd.DataFrame, columns: list[str], labels: dict[str, str], format_cell) -> str:
    heads = "".join(f"<th>{escape(labels.get(c, c))}</th>" for c in columns)
    rows_html = []
    for _, r in df.iterrows():
        tds = []
        for c in columns:
            if c == "grade":
                tds.append(f"<td>{grade_badge_html(str(r.get(c, '')))}</td>")
            elif c == "corp_name":
                tds.append(f'<td class="name">{escape(str(r.get(c, "")))}</td>')
            elif c == "stock_code":
                tds.append(f"<td>{escape(str(r.get(c, '')).zfill(6))}</td>")
            elif c == "market":
                m = str(r.get(c, ""))
                label = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(m, m)
                tds.append(f"<td>{escape(label)}</td>")
            else:
                cls = "num" if c not in ("corp_name", "stock_code", "market", "grade") else ""
                tds.append(f'<td class="{cls}">{escape(format_cell(r, c))}</td>')
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return f"""
    <div class="ks-wrap"><div class="ks-table-wrap">
      <table class="ks-table">
        <thead><tr>{heads}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div></div>
    """
