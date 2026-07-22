"""Financial ratio and absolute metric calculations from DART account data."""

from __future__ import annotations

import pandas as pd

from dart_api import DB_PATH, get_db, init_db

# DART 계정명 후보 (회사마다 표기가 조금씩 다를 수 있음)
ACCOUNT_ALIASES = {
    "current_assets": ["유동자산"],
    "current_liabilities": ["유동부채"],
    "inventory": ["재고자산"],
    "total_liabilities": ["부채총계"],
    "total_equity": ["자본총계", "자본총계(지배기업 소유주지분)"],
    "total_assets": ["자산총계"],
    "revenue": ["매출액", "수익(매출액)"],
    "cogs": ["매출원가", "매출원가 및 용역원가"],
    "gross_profit": ["매출총이익"],
    "operating_profit": ["영업이익", "영업이익(손실)"],
    "net_income": ["당기순이익", "당기순이익(손실)", "분기순이익"],
    "cash": ["현금및현금성자산", "현금 및 현금성 자산"],
    "receivables": ["매출채권", "매출채권 및 기타유동채권"],
    "prev_revenue": [],
}


def _pick_amount(df: pd.DataFrame, aliases: list[str]) -> float | None:
    if df.empty or not aliases:
        return None
    for name in aliases:
        matched = df[df["account_nm"] == name]
        if not matched.empty:
            return float(matched.iloc[0]["amount"])
    return None


def load_financial_metrics(bsns_year: str, prev_year: str | None = None) -> pd.DataFrame:
    conn = get_db()
    init_db(conn)
    cur = pd.read_sql(
        """
        SELECT f.stock_code, c.corp_name, f.account_nm, f.amount
        FROM financials f
        JOIN corp_codes c ON c.stock_code = f.stock_code
        WHERE f.bsns_year = ?
        """,
        conn,
        params=(bsns_year,),
    )
    prev = pd.DataFrame()
    if prev_year:
        prev = pd.read_sql(
            """
            SELECT stock_code, account_nm, amount
            FROM financials
            WHERE bsns_year = ?
            """,
            conn,
            params=(prev_year,),
        )
    conn.close()

    if cur.empty:
        return pd.DataFrame()

    rows = []
    for stock_code, group in cur.groupby("stock_code"):
        corp_name = group.iloc[0]["corp_name"]
        prev_group = prev[prev["stock_code"] == stock_code] if not prev.empty else pd.DataFrame()

        current_assets = _pick_amount(group, ACCOUNT_ALIASES["current_assets"])
        current_liabilities = _pick_amount(group, ACCOUNT_ALIASES["current_liabilities"])
        inventory = _pick_amount(group, ACCOUNT_ALIASES["inventory"])
        total_liabilities = _pick_amount(group, ACCOUNT_ALIASES["total_liabilities"])
        total_equity = _pick_amount(group, ACCOUNT_ALIASES["total_equity"])
        total_assets = _pick_amount(group, ACCOUNT_ALIASES["total_assets"])
        revenue = _pick_amount(group, ACCOUNT_ALIASES["revenue"])
        cogs = _pick_amount(group, ACCOUNT_ALIASES["cogs"])
        gross_profit = _pick_amount(group, ACCOUNT_ALIASES["gross_profit"])
        operating_profit = _pick_amount(group, ACCOUNT_ALIASES["operating_profit"])
        net_income = _pick_amount(group, ACCOUNT_ALIASES["net_income"])
        cash = _pick_amount(group, ACCOUNT_ALIASES["cash"])
        receivables = _pick_amount(group, ACCOUNT_ALIASES["receivables"])
        prev_revenue = _pick_amount(prev_group, ACCOUNT_ALIASES["revenue"]) if not prev_group.empty else None

        if gross_profit is None and revenue is not None and cogs is not None:
            gross_profit = revenue - cogs

        metrics = {
            "stock_code": stock_code,
            "corp_name": corp_name,
            "revenue": revenue,
            "operating_profit": operating_profit,
            "net_income": net_income,
            "current_ratio": _pct_ratio(current_assets, current_liabilities),
            "quick_ratio": _pct_ratio(
                (current_assets - inventory) if current_assets is not None and inventory is not None else None,
                current_liabilities,
            ),
            "debt_ratio": _pct_ratio(total_liabilities, total_equity),
            "gross_margin": _pct_ratio(gross_profit, revenue),
            "operating_margin": _pct_ratio(operating_profit, revenue),
            "net_margin": _pct_ratio(net_income, revenue),
            "roa": _pct_ratio(net_income, total_assets),
            "roe": _pct_ratio(net_income, total_equity),
            "inventory_turnover": _turnover(cogs, inventory),
            "receivable_turnover": _turnover(revenue, receivables),
            "revenue_growth": _growth(revenue, prev_revenue),
            "cash_months": _cash_months(cash, operating_profit),
        }
        rows.append(metrics)

    return pd.DataFrame(rows)


def _pct_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _turnover(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def _cash_months(cash: float | None, operating_profit: float | None) -> float | None:
    """현금 / 월간 영업비용(영업이익이 음수면 절대값 기준 근사)."""
    if cash is None:
        return None
    monthly_burn = None
    if operating_profit is not None and operating_profit < 0:
        monthly_burn = abs(operating_profit) / 12
    if monthly_burn in (None, 0):
        return None
    return cash / monthly_burn
