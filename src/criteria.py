"""Filter defaults, 이상/이하 UI, excellence badges and attractiveness score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

Direction = Literal["min", "max", "range", "max_change"]


@dataclass(frozen=True)
class FilterSpec:
    key: str
    label: str
    category: str
    help_text: str
    direction: Direction
    # excellent defaults (shown when checkbox turns on)
    excellent_min: float | None = None
    excellent_max: float | None = None
    # for badge scoring on "higher is better" / "lower is better"
    higher_better: bool = True
    unit_hint: str = ""  # "%", "년", "개월", "배", ""


# --- Spec table (user-confirmed) ---
FILTER_SPECS: list[FilterSpec] = [
    # B경제
    FilterSpec("cash_survival_years", "현금 생존력", "B경제", "(현금+단기금융)/순손실 = 버틸 연수", "min", 2.0, None, True, "년"),
    FilterSpec("inventory_months", "재고 보유 월수", "B경제", "재고/매출원가(월) = 현금흐름 압박", "max", None, 3.0, False, "개월"),
    FilterSpec("cash_flow_match", "현금 흐름 일치도", "B경제", "영업CF/당기순이익 = 이익의 질", "min", 1.0, None, True, "배"),
    FilterSpec("sga_ratio_change", "비용 효율성(판관비율 변화)", "B경제", "판관비/매출 전년 대비 감소", "max_change", None, 0.0, False, "%p"),
    # 안전성
    FilterSpec("current_ratio", "유동비율", "안전성 check!", "유동자산/유동부채", "min", 100.0, None, True, "%"),
    FilterSpec("quick_ratio", "당좌비율", "안전성 check!", "(유동자산-재고)/유동부채", "min", 100.0, None, True, "%"),
    FilterSpec("debt_ratio", "부채비율", "안전성 check!", "부채총액/자본총액 (50~200% 우수)", "range", 50.0, 200.0, True, "%"),
    FilterSpec("cash_months", "현금규모(개월)", "안전성 check!", "현금성자산/월 판관비", "min", 12.0, None, True, "개월"),
    # 수익/성장 — 뱃지: 0%↑양호, 40%↑우수, 80%↑매우우수 (필터 기본=우수 40)
    FilterSpec("revenue_growth", "매출성장율", "수익/성장성 check!", "(당기-전기)매출/전기", "min", 40.0, None, True, "%"),
    FilterSpec("gross_margin", "매출총이익율", "수익/성장성 check!", "매출총이익/매출", "min", 40.0, None, True, "%"),
    FilterSpec("operating_margin", "영업이익률", "수익/성장성 check!", "영업이익/매출", "min", 40.0, None, True, "%"),
    FilterSpec("net_margin", "당기순이익율", "수익/성장성 check!", "당기순이익/매출", "min", 40.0, None, True, "%"),
    # 효율
    FilterSpec("roa", "총자산이익율(ROA)", "효율성 check!", "당기순이익/총자산", "min", 5.0, None, True, "%"),
    FilterSpec("roe", "자기자본이익율(ROE)", "효율성 check!", "당기순이익/자기자본", "min", 15.0, None, True, "%"),
    FilterSpec("inventory_turnover", "재고자산회전율", "효율성 check!", "매출/재고 (높을수록)", "min", 4.0, None, True, "회"),
    FilterSpec("receivable_turnover", "매출채권 회전율", "효율성 check!", "매출/매출채권", "min", 10.0, None, True, "회"),
    # check!!
    FilterSpec("revenue_minus_debt_growth", "매출증가율−부채증가율", "check!!", "매출성장이 부채성장 이상", "min", 0.0, None, True, "%p"),
    # 주가
    FilterSpec("pct_from_low", "저점대비상승", "주가 현위치", "저점 대비 상승폭 (낮을수록)", "max", None, 50.0, False, "%"),
    FilterSpec("bottom_dwell_ratio", "바닥체류", "주가 현위치", "바닥권 체류 비율 (높을수록)", "min", 50.0, None, True, "%"),
]

SPEC_BY_KEY = {s.key: s for s in FILTER_SPECS}

ABS_SPECS = [
    ("revenue", "매출액"),
    ("operating_profit", "영업이익"),
    ("net_income", "당기순이익"),
]

LIST_COLUMNS = [
    "corp_name",
    "stock_code",
    "market",
    "current_price",
    "operating_margin",
    "revenue_growth",
    "revenue",
    "attractiveness",
    "grade",
]

PRICE_FILTER_KEYS = {"pct_from_low", "bottom_dwell_ratio", "range_position"}


def categories_order() -> list[str]:
    seen = []
    for s in FILTER_SPECS:
        if s.category not in seen:
            seen.append(s.category)
    return seen


def specs_in_category(category: str) -> list[FilterSpec]:
    return [s for s in FILTER_SPECS if s.category == category]


GROWTH_PROFIT_KEYS = {
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_margin",
}


def badge_for_value(spec: FilterSpec, value: float | None) -> str:
    """우수 / 매우우수 / 보통(양호) / 주의 / 위험 / 해당없음"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "해당없음"

    # 수익/성장성: 0%↑ 양호(보통), 40%↑ 우수, 80%↑ 매우우수
    if spec.key in GROWTH_PROFIT_KEYS:
        if value >= 80:
            return "매우우수"
        if value >= 40:
            return "우수"
        if value >= 0:
            return "보통"  # UI에서 '양호'로 표시
        if value >= -20:
            return "주의"
        return "위험"

    # range (debt)
    if spec.direction == "range":
        lo, hi = spec.excellent_min, spec.excellent_max
        if lo is not None and hi is not None:
            if lo <= value <= hi:
                return "우수"
            if value > hi:
                return "위험"
            return "주의"  # below 50%

    # max_change (sga decrease = good if value <= 0)
    if spec.direction == "max_change":
        if value <= -10:
            return "매우우수"
        if value <= 0:
            return "우수"
        if value <= 5:
            return "보통"
        return "주의"

    if spec.higher_better:
        exc = spec.excellent_min
        if exc is None:
            return "보통"
        very = exc * 2
        # bottom_dwell capped: very = 75
        if spec.key == "bottom_dwell_ratio":
            very = 75.0
        if value >= very:
            return "매우우수"
        if value >= exc:
            return "우수"
        if value >= exc * 0.7:
            return "보통"
        if value >= exc * 0.4:
            return "주의"
        return "위험"

    # lower better
    exc = spec.excellent_max
    if exc is None:
        return "보통"
    very = exc / 2
    if value <= very:
        return "매우우수"
    if value <= exc:
        return "우수"
    if value <= exc * 1.5:
        return "보통"
    if value <= exc * 2.5:
        return "주의"
    return "위험"


BADGE_SCORE = {
    "매우우수": 2,
    "우수": 1,
    "보통": 0,
    "주의": -1,
    "위험": -2,
    "해당없음": 0,
}

BADGE_COLOR = {
    "매우우수": "🟢",
    "우수": "🔵",
    "보통": "⚪",
    "주의": "🟡",
    "위험": "🔴",
    "해당없음": "⬛",
}


def score_row(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    badges: dict[str, str] = {}
    total = 0
    counted = 0
    for spec in FILTER_SPECS:
        val = row.get(spec.key) if hasattr(row, "get") else row[spec.key] if spec.key in row else None
        try:
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                val = float(val)
            else:
                val = None
        except (TypeError, ValueError):
            val = None
        # cash_flow_match stored as ratio (1.0 = 100%); excellent is 100% in UI = 1.0 in data
        if spec.key == "cash_flow_match" and val is not None:
            # compare using ratio: excellent min 1.0
            pass
        badge = badge_for_value(spec, val)
        # Fix cash_flow_match: FilterSpec excellent_min=1.0 means 100% as ratio
        badges[spec.key] = badge
        if badge != "해당없음":
            total += BADGE_SCORE[badge]
            counted += 1

    raw = total
    attractiveness = int(max(0, min(100, 50 + raw * 3)))
    grade = grade_for_score(attractiveness)

    counts = {k: 0 for k in BADGE_SCORE}
    for b in badges.values():
        counts[b] = counts.get(b, 0) + 1

    return {
        "badges": badges,
        "badge_counts": counts,
        "score_raw": raw,
        "attractiveness": attractiveness,
        "grade": grade,
    }


def grade_for_score(attractiveness: int) -> str:
    if attractiveness >= 80:
        return "A"
    if attractiveness >= 65:
        return "B"
    if attractiveness >= 50:
        return "C"
    return "D"
