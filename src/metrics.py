"""Financial ratio and absolute metric calculations (DART / Naver account rows)."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from dart_api import get_db, init_db

ACCOUNT_ALIASES = {
    # 엑셀 계정 매핑 + DART/네이버(Wisereport) 표기
    "current_assets": ["유동자산"],
    "cash": ["현금및현금성자산", "현금 및 현금성 자산", "현금", "예치금"],
    "short_term_financial": [
        "단기금융자산",
        "단기금융상품",
        "단기투자자산",
        "유동금융자산",
        "당기손익-공정가치측정금융자산",  # JYP 등
        "당기손익-공정가치금융자산",
    ],
    "receivables": ["매출채권", "매출채권및기타채권", "매출채권 및 기타유동채권"],
    "inventory": ["재고자산"],
    "total_assets": ["자산총계", "자산합계"],
    "current_liabilities": ["유동부채"],
    "total_liabilities": ["부채총계", "부채합계"],
    "total_equity": [
        "지배주주지분",  # 네이버 우선
        "자본총계",
        "자본합계",
        "지배기업의 소유주에게 귀속되는 자본",
        "지배기업의소유주에게귀속되는자본",
        "자본총계(지배기업 소유주지분)",
        "지배기업소유주지분",
    ],
    "advances": ["선수금", "선수수익", "예수금", "계약부채"],  # 행복한 부채
    "revenue": ["매출액(수익)", "매출액", "영업수익", "수익(매출액)", "수익"],
    "cogs": ["매출원가", "영업원가", "매출원가 및 용역원가"],
    "gross_profit": ["매출총이익"],
    "sga": [
        "판매비와관리비",
        "영업비용",
        "판매비와관리비(일반)",
        "판매비와관리비 및 기타판매비와관리비",
    ],
    "operating_profit": ["영업이익", "영업손실", "영업이익(손실)", "영업이익(발표기준)"],
    # 지배지분 순이익 우선 (네이버/DART 공통)
    "net_income": [
        "(지배주주지분)당기순이익",
        "*(지배주주지분)연결당기순이익",
        "지배기업의소유주에게귀속되는당기순이익(손실)",
        "지배기업의 소유주에게 귀속되는 당기순이익(손실)",
        "당기순이익(손실)",
        "연결당기순이익",
        "당기순이익",
        "당기순손실",
        "분기순이익",
    ],
    "pretax_income": [
        "법인세비용차감전계속사업이익",
        "법인세비용차감전순이익(손실)",
        "법인세비용차감전순이익",
        "법인세차감전순이익",
        "법인세비용차감전계속영업순이익",
    ],
    "income_tax": ["법인세비용(수익)", "법인세비용", "법인세등"],
    "operating_cash_flow": [
        "영업활동으로인한현금흐름",
        "영업활동현금흐름",
        "영업활동에서의현금흐름",
        "영업활동으로부터창출된현금흐름",
    ],
    "capex": ["*CAPEX", "CAPEX", "유형자산의취득", "유형자산의증가"],
    "dividends_paid": ["배당금의지급", "배당금지급"],
}

# 부분일치에 쓰기엔 너무 넓은 계정명 (exact만 사용)
_BROAD_ALIASES = {"현금", "예치금", "수익", "영업비용"}

_NUM_PREFIX_RE = re.compile(
    r"^[\dIVXivxⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+\s*[.．、)\]]\s*"
)


def _norm_account(name: str) -> str:
    """'Ⅵ. 당기순이익' / '....재고자산' → 정규화."""
    s = str(name).strip()
    s = _NUM_PREFIX_RE.sub("", s)
    s = re.sub(r"^[\.\*]+", "", s)
    return re.sub(r"\s+", "", s)


def _pick_amount(df: pd.DataFrame, aliases: list[str]) -> float | None:
    """계정명 매칭. 0원 더미는 건너뛰고 비영 값을 우선."""
    if df.empty or not aliases:
        return None

    zero_hit: float | None = None
    norms = df["account_nm"].astype(str).map(_norm_account)

    for name in aliases:
        target = _norm_account(name)
        matched = df[norms == target]
        if matched.empty:
            matched = df[df["account_nm"] == name]
        if matched.empty:
            continue
        for amt in matched["amount"].astype(float).tolist():
            if amt != 0:
                return float(amt)
            zero_hit = 0.0

    # exact가 전부 0/없음이면 부분일치 (넓은 별칭·조정라인 제외)
    for name in aliases:
        if name in _BROAD_ALIASES or len(name) < 4:
            continue
        target = _norm_account(name)
        mask = norms.str.contains(target, regex=False, na=False)
        if not mask.any():
            continue
        sub = df.loc[mask].copy()
        sub_names = sub["account_nm"].astype(str)
        sub = sub[
            ~sub_names.str.contains(
                "조정|가감|재분류|법인세비용차감전|법인세차감전",
                regex=True,
                na=False,
            )
        ]
        if sub.empty:
            continue
        sub["_abs"] = sub["amount"].astype(float).abs()
        sub = sub.sort_values("_abs", ascending=False)
        for amt in sub["amount"].astype(float).tolist():
            if amt != 0:
                return float(amt)
            zero_hit = 0.0

    return zero_hit


def _resolve_net_income(accounts: dict[str, float | None]) -> float | None:
    """DART에 당기순이익=0 더미만 있을 때 세전이익−법인세비용으로 보정."""
    ni = accounts.get("net_income")
    pretax = accounts.get("pretax_income")
    tax = accounts.get("income_tax")
    if ni not in (None, 0):
        return ni
    if pretax is not None and tax is not None and pretax != 0:
        return float(pretax) - float(tax)
    return ni


def _resolve_total_equity(accounts: dict[str, float | None]) -> float | None:
    """자본총계가 잘못 들어온 경우(SK오션플랜트 등) 자산−부채로 보정."""
    equity = accounts.get("total_equity")
    assets = accounts.get("total_assets")
    liab = accounts.get("total_liabilities")
    if assets is not None and liab is not None:
        implied = float(assets) - float(liab)
        if implied != 0:
            if equity is None or equity == 0:
                return implied
            # 계정 '자본총계'가 BS 항등식과 5% 이상 어긋나면 자산−부채 사용
            if abs(float(equity) - implied) / abs(implied) > 0.05:
                return implied
    return equity


def _extract_accounts(group: pd.DataFrame) -> dict[str, float | None]:
    return _extract_accounts_from_rows(group)


def _extract_accounts_from_rows(group: pd.DataFrame) -> dict[str, float | None]:
    return {key: _pick_amount(group, aliases) for key, aliases in ACCOUNT_ALIASES.items()}


def compute_metrics_row(
    stock_code: str,
    corp_name: str,
    a: dict[str, float | None],
    p: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """계정 dict(당기/전기) → 스크리너 지표 1행."""
    p = p or {}
    a = dict(a)
    p = dict(p)
    a["total_equity"] = _resolve_total_equity(a)
    if p:
        p["total_equity"] = _resolve_total_equity(p)

    gross_profit = a.get("gross_profit")
    if gross_profit is None and a.get("revenue") is not None and a.get("cogs") is not None:
        gross_profit = a["revenue"] - a["cogs"]  # type: ignore[operator]

    cash_total = _sum_non_null(a.get("cash"), a.get("short_term_financial"))
    revenue = a.get("revenue")
    net_income = _resolve_net_income(a)
    sga = a.get("sga")
    sga_ratio = _pct_ratio(sga, revenue)
    prev_sga_ratio = _pct_ratio(p.get("sga"), p.get("revenue"))
    revenue_growth = _growth(revenue, p.get("revenue"))
    debt_growth = _growth(a.get("total_liabilities"), p.get("total_liabilities"))

    return {
        "stock_code": str(stock_code).zfill(6),
        "corp_name": corp_name,
        "revenue": revenue,
        "operating_profit": a.get("operating_profit"),
        "net_income": net_income,
        # B경제
        "cash_survival_years": _cash_survival_years(cash_total, net_income),
        "inventory_months": _inventory_months(a.get("inventory"), a.get("cogs")),
        "cash_flow_match": _ratio(a.get("operating_cash_flow"), net_income),
        "cash_to_revenue": _pct_ratio(cash_total, revenue),
        "cash_to_op_profit_x3": _pct_ratio(
            cash_total,
            a["operating_profit"] * 3 if a.get("operating_profit") is not None else None,
        ),
        "happy_debt_growth": _growth(a.get("advances"), p.get("advances")),
        "sga_ratio": sga_ratio,
        "sga_ratio_change": (
            sga_ratio - prev_sga_ratio
            if sga_ratio is not None and prev_sga_ratio is not None
            else None
        ),
        # 안전성
        "current_ratio": _pct_ratio(a.get("current_assets"), a.get("current_liabilities")),
        "quick_ratio": _pct_ratio(
            (
                a["current_assets"] - a["inventory"]
                if a.get("current_assets") is not None and a.get("inventory") is not None
                else None
            ),
            a.get("current_liabilities"),
        ),
        "debt_ratio": _pct_ratio(a.get("total_liabilities"), a.get("total_equity")),
        "cash_months": _cash_months_sga(cash_total, sga),
        # 수익/성장성
        "revenue_growth": revenue_growth,
        "gross_margin": _pct_ratio(gross_profit, revenue),
        "operating_margin": _pct_ratio(a.get("operating_profit"), revenue),
        "net_margin": _pct_ratio(net_income, revenue),
        # 효율성
        "roa": _pct_ratio(net_income, a.get("total_assets")),
        "roe": _pct_ratio(net_income, a.get("total_equity")),
        "inventory_turnover": _turnover(revenue, a.get("inventory")),
        "receivable_turnover": _turnover(revenue, a.get("receivables")),
        # check!!
        "debt_growth": debt_growth,
        "revenue_minus_debt_growth": (
            revenue_growth - debt_growth
            if revenue_growth is not None and debt_growth is not None
            else None
        ),
        # raw accounts for detail modal
        "current_assets": a.get("current_assets"),
        "cash": a.get("cash"),
        "short_term_financial": a.get("short_term_financial"),
        "receivables": a.get("receivables"),
        "inventory": a.get("inventory"),
        "total_assets": a.get("total_assets"),
        "current_liabilities": a.get("current_liabilities"),
        "total_liabilities": a.get("total_liabilities"),
        "total_equity": a.get("total_equity"),
        "advances": a.get("advances"),
        "cogs": a.get("cogs"),
        "gross_profit": gross_profit,
        "sga": sga,
        "operating_cash_flow": a.get("operating_cash_flow"),
        "capex": a.get("capex"),
        "dividends_paid": a.get("dividends_paid"),
    }


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
        rows.append(compute_metrics_row(str(stock_code), corp_name, a, p))

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
