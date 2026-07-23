"""Dark dashboard theme + HTML UI helpers (tabs, cards, table)."""

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
    "보통": ("보통", "neutral"),
    "주의": ("주의", "warn"),
    "위험": ("약세", "bad"),
    "해당없음": ("—", "muted"),
}


THEME_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

html, body, [class*="css"] {
  font-family: 'Pretendard', 'Noto Sans KR', sans-serif !important;
}

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stHeader"] { display: none; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

.stApp {
  background: #0b111e !important;
  color: #e8ecf4;
}

div[data-testid="stAppViewContainer"] .main .block-container {
  max-width: 1180px !important;
  padding: 1.1rem 1.4rem 3rem 1.4rem;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] > div > div,
div[data-baseweb="select"] > div {
  background: #121826 !important;
  color: #e8ecf4 !important;
  border: 1px solid #2a3348 !important;
  border-radius: 10px !important;
}
div[data-testid="stSelectbox"] label,
div[data-testid="stNumberInput"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stRadio"] label,
.stMarkdown p, .stCaption, label {
  color: #9aa3b5 !important;
}

div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stButton"] > button[data-testid="baseButton-primary"] {
  background: #4c8bf5 !important;
  color: #fff !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 600 !important;
  padding: 0.45rem 1.2rem !important;
}
div[data-testid="stButton"] > button {
  border-radius: 10px !important;
  border: 1px solid #2a3348 !important;
  background: #151b2b !important;
  color: #e8ecf4 !important;
}

div[data-testid="stRadio"] > div {
  gap: 0.55rem !important;
  flex-wrap: nowrap !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] {
  background: #151b2b !important;
  border: 1px solid #2a3348 !important;
  border-radius: 12px !important;
  padding: 0.55rem 1.05rem !important;
  min-width: 9.5rem;
  justify-content: center;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
  display: none !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] [data-testid="stMarkdownContainer"] p {
  color: #c5cddc !important;
  font-weight: 600 !important;
  margin: 0 !important;
  font-size: 0.95rem !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
  background: #4c8bf5 !important;
  border-color: #4c8bf5 !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) [data-testid="stMarkdownContainer"] p {
  color: #fff !important;
}

div[data-testid="stCheckbox"] label p { color: #d5dbe8 !important; }
div[data-testid="stExpander"] {
  background: #121826 !important;
  border: 1px solid #2a3348 !important;
  border-radius: 12px !important;
}

hr { border-color: #243049 !important; }

/* 필터 한 줄 유지 */
div[data-testid="stExpander"] div[data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  gap: 0.35rem !important;
  align-items: center !important;
}
div[data-testid="stExpander"] div[data-testid="column"] {
  min-width: 0 !important;
}

.ks-hint {
  color: #8b95a8;
  font-size: 0.88rem;
  margin: 0.15rem 0 0.85rem 0;
}
.ks-status {
  color: #9aa3b5;
  font-size: 0.9rem;
  padding-top: 0.55rem;
}
.ks-card {
  background: #151b2b;
  border: 1px solid #2a3348;
  border-radius: 14px;
  padding: 1.1rem 1.25rem;
  margin: 0.6rem 0 0.9rem 0;
}
.ks-score-row {
  display: flex;
  justify-content: space-between;
  gap: 1.5rem;
  flex-wrap: wrap;
  align-items: flex-start;
}
.ks-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: #f2f5fa;
  margin-bottom: 0.35rem;
}
.ks-score {
  font-size: 2.6rem;
  font-weight: 800;
  color: #fff;
  line-height: 1.1;
  display: inline-block;
  margin-right: 0.55rem;
}
.ks-sub {
  color: #8b95a8;
  font-size: 0.85rem;
  margin-top: 0.25rem;
}
.ks-side {
  min-width: 180px;
  text-align: right;
}
.ks-side-item {
  margin-bottom: 0.45rem;
}
.ks-side-label { color: #8b95a8; font-size: 0.8rem; }
.ks-side-val { color: #7eb6ff; font-size: 1.25rem; font-weight: 700; }

.ks-badge {
  display: inline-block;
  padding: 0.18rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  vertical-align: middle;
}
.ks-badge.hot { background: rgba(61,214,140,0.16); color: #3dd68c; }
.ks-badge.watch { background: rgba(76,139,245,0.16); color: #7eb6ff; }
.ks-badge.neutral { background: rgba(155,165,184,0.14); color: #b0b8c8; }
.ks-badge.warn { background: rgba(240,113,120,0.14); color: #f07178; }
.ks-badge.good { color: #3dd68c; background: transparent; font-weight: 600; padding: 0; }
.ks-badge.bad { color: #f07178; background: transparent; font-weight: 600; padding: 0; }
.ks-badge.muted { color: #6b7385; background: transparent; padding: 0; }

.ks-section-title {
  color: #c5cddc;
  font-weight: 700;
  font-size: 0.95rem;
  margin: 0.4rem 0 0.7rem 0;
}
.ks-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.65rem;
}
@media (max-width: 900px) {
  .ks-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.ks-metric {
  background: #121826;
  border: 1px solid #2a3348;
  border-radius: 12px;
  padding: 0.75rem 0.8rem;
  min-height: 92px;
}
.ks-metric .lab {
  color: #8b95a8;
  font-size: 0.75rem;
  margin-bottom: 0.35rem;
}
.ks-metric .val {
  color: #f2f5fa;
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
}
.ks-metric .st {
  font-size: 0.78rem;
}

.ks-table-wrap {
  background: #151b2b;
  border: 1px solid #2a3348;
  border-radius: 14px;
  overflow: hidden;
  margin-top: 0.6rem;
}
.ks-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.ks-table th {
  text-align: left;
  color: #8b95a8;
  font-weight: 600;
  padding: 0.75rem 0.85rem;
  border-bottom: 1px solid #2a3348;
  white-space: nowrap;
}
.ks-table td {
  color: #e8ecf4;
  padding: 0.7rem 0.85rem;
  border-bottom: 1px solid #1e2638;
  white-space: nowrap;
}
.ks-table tr:last-child td { border-bottom: none; }
.ks-table tr:hover td { background: rgba(76,139,245,0.06); }
.ks-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.ks-table .name { font-weight: 600; }
.ks-foot {
  color: #6b7385;
  font-size: 0.78rem;
  margin-top: 0.55rem;
}
</style>
"""


def inject_theme() -> None:
    import streamlit as st

    st.markdown(THEME_CSS, unsafe_allow_html=True)


def grade_badge_html(grade: str) -> str:
    label, cls = GRADE_UI.get(str(grade), (str(grade), "neutral"))
    return f'<span class="ks-badge {cls}">{escape(label)}</span>'


def status_html(badge: str) -> str:
    label, cls = BADGE_STATUS.get(badge, (badge or "—", "muted"))
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
    <div class="ks-card">
      <div class="ks-score-row">
        <div>
          <div class="ks-title">{escape(name)} {escape(code)}</div>
          <div>
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
    </div>
    """


def render_metric_grid(items: list[tuple[str, str, str]]) -> str:
    cards = []
    for lab, val, badge in items:
        cards.append(
            f"""
            <div class="ks-metric">
              <div class="lab">{escape(lab)}</div>
              <div class="val">{escape(val)}</div>
              <div class="st">{status_html(badge)}</div>
            </div>
            """
        )
    return f"""
    <div class="ks-card">
      <div class="ks-section-title">핵심 지표</div>
      <div class="ks-grid">{''.join(cards)}</div>
    </div>
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
    <div class="ks-table-wrap">
      <table class="ks-table">
        <thead><tr>{heads}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    """
