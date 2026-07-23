"""Financial ratio and absolute metric calculations from DART account data."""

from __future__ import annotations

import pandas as pd

from dart_api import get_db, init_db

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
    "short_term_financial": ["단기금융상품", "단기금융자산", "단기투자자산"],
    "receivables": ["매출채권", "매출채권 및 기타유동채권"],
    "operating_cash_flow": ["영업활동현금흐름", "영업활동으로인한현금흐름"],
    "advances": ["선수금", "선수수익", "계약부채"],
    "sga": ["판매비와관리비", "판매비와관리비(일반)", "판매비와관리비 및 기타판매비와관리비"],
}


def _pick_amount(df: pd.DataFrame, aliases: list[str]) -> float | None:
    if df.empty or not aliases:
        return None
    for name in aliases:
        matched = df[df["account_nm"] == name]
        if not matched.empty:
            return float(matched.iloc[0]["amount"])
    return None


def _extract_accounts(group: pd.DataFrame) -> dict[str, float | None]:
    return {key: _pick_amount(group, aliases) for key, aliases in ACCOUNT_ALIASES.items()}


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

        a = _extract_accounts(group)
        p = _extract_accounts(prev_group) if not prev_group.empty else {}

        gross_profit = a["gross_profit"]
        if gross_profit is None and a["revenue"] is not None and a["cogs"] is not None:
            gross_profit = a["revenue"] - a["cogs"]

        cash_total = _sum_non_null(a["cash"], a["short_term_financial"])
        revenue = a["revenue"]
        net_income = a["net_income"]
        sga = a["sga"]
        sga_ratio = _pct_ratio(sga, revenue)
        prev_sga_ratio = _pct_ratio(p.get("sga"), p.get("revenue"))
        revenue_growth = _growth(revenue, p.get("revenue"))
        debt_growth = _growth(a["total_liabilities"], p.get("total_liabilities"))

        metrics = {
            "stock_code": stock_code,
            "corp_name": corp_name,
            "revenue": revenue,
            "operating_profit": a["operating_profit"],
            "net_income": net_income,
            # B경제
            "cash_survival_years": _cash_survival_years(cash_total, net_income),
            "inventory_months": _inventory_months(a["inventory"], a["cogs"]),
            "cash_flow_match": _ratio(a["operating_cash_flow"], net_income),
            "cash_to_revenue": _pct_ratio(cash_total, revenue),
            "cash_to_op_profit_x3": _pct_ratio(
                cash_total,
                a["operating_profit"] * 3 if a["operating_profit"] is not None else None,
            ),
            "happy_debt_growth": _growth(a["advances"], p.get("advances")),
            "sga_ratio": sga_ratio,
            "sga_ratio_change": (sga_ratio - prev_sga_ratio) if sga_ratio is not None and prev_sga_ratio is not None else None,
            # 안전성
            "current_ratio": _pct_ratio(a["current_assets"], a["current_liabilities"]),
            "quick_ratio": _pct_ratio(
                (a["current_assets"] - a["inventory"]) if a["current_assets"] is not None and a["inventory"] is not None else None,
                a["current_liabilities"],
            ),
            "debt_ratio": _pct_ratio(a["total_liabilities"], a["total_equity"]),
            "cash_months": _cash_months_sga(cash_total, sga),
            # 수익/성장성
            "revenue_growth": revenue_growth,
            "gross_margin": _pct_ratio(gross_profit, revenue),
            "operating_margin": _pct_ratio(a["operating_profit"], revenue),
            "net_margin": _pct_ratio(net_income, revenue),
            # 효율성
            "roa": _pct_ratio(net_income, a["total_assets"]),
            "roe": _pct_ratio(net_income, a["total_equity"]),
            "inventory_turnover": _turnover(revenue, a["inventory"]),
            "receivable_turnover": _turnover(revenue, a["receivables"]),
            # check!!
            "debt_growth": debt_growth,
            "revenue_minus_debt_growth": (
                revenue_growth - debt_growth
                if revenue_growth is not None and debt_growth is not None
                else None
            ),
            # raw accounts for detail modal
            "current_assets": a["current_assets"],
            "cash": a["cash"],
            "short_term_financial": a["short_term_financial"],
            "receivables": a["receivables"],
            "inventory": a["inventory"],
            "total_assets": a["total_assets"],
            "current_liabilities": a["current_liabilities"],
            "total_liabilities": a["total_liabilities"],
            "total_equity": a["total_equity"],
            "advances": a["advances"],
            "cogs": a["cogs"],
            "gross_profit": gross_profit,
            "sga": sga,
            "operating_cash_flow": a["operating_cash_flow"],
        }
        rows.append(metrics)

    return pd.DataFrame(rows)


def _sum_non_null(*values: float | None) -> float | None:
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _pct_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _turnover(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def _cash_survival_years(cash_total: float | None, net_income: float | None) -> float | None:
    """(현금+단기금융) / 당기순손실 → 버틸 수 있는 연수."""
    if cash_total is None or net_income is None or net_income >= 0:
        return None
    return cash_total / abs(net_income)


def _inventory_months(inventory: float | None, cogs: float | None) -> float | None:
    """재고자산 / 월매출원가 → 재고 보유 월수."""
    if inventory is None or cogs in (None, 0):
        return None
    return inventory / (cogs / 12)


def _cash_months_sga(cash_total: float | None, sga: float | None) -> float | None:
    """현금성자산 / 월 판관비."""
    if cash_total is None or sga in (None, 0):
        return None
    return cash_total / (sga / 12)
