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
    FilterSpec(
        "cash_survival_years",
        "현금 생존력",
        "B경제",
        "적자일 때 가진 현금으로 몇 년이나 버틸 수 있는지예요. 숫자가 클수록 여유 있어요. 우수: 2년 이상",
        "min",
        2.0,
        None,
        True,
        "년",
    ),
    FilterSpec(
        "inventory_months",
        "재고 보유 월수",
        "B경제",
        "창고에 쌓인 물건이 몇 달치 매출 원가인지예요. 너무 많으면 현금이 묶여 있을 수 있어요. 우수: 3개월 이하",
        "max",
        None,
        3.0,
        False,
        "개월",
    ),
    FilterSpec(
        "cash_flow_match",
        "현금흐름일치",
        "B경제",
        "장부상 이익이 실제로 현금으로 잘 들어오는지 봐요. 1배(100%) 이상이면 이익의 질이 좋아요. 적자 종목은 점수에서 빼요. 우수: 1배 이상",
        "min",
        1.0,
        None,
        True,
        "배",
    ),
    FilterSpec(
        "sga_ratio_change",
        "판관비 전년비",
        "B경제",
        "판관비(영업비용) 비중이 작년보다 줄었는지 봐요. 줄면 비용 관리가 좋아진 신호예요. 우수: 0%p 이하(감소) · +10%p 초과는 위험",
        "max_change",
        None,
        0.0,
        False,
        "%p",
    ),
    # 안전성
    FilterSpec(
        "current_ratio",
        "유동비율",
        "안전성 check!",
        "1년 안에 갚을 빚을 당장 쓸 수 있는 자산으로 얼마나 감당하는지예요. 100%면 겨우 맞추는 수준이에요. 우수: 100% 이상",
        "min",
        100.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "quick_ratio",
        "당좌비율",
        "안전성 check!",
        "유동비율에서 재고를 뺀 더 깐깐한 단기 안전성이에요. 우수: 100% 이상",
        "min",
        100.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "debt_ratio",
        "부채비율",
        "안전성 check!",
        "자기자본 대비 빚이 얼마나 있는지예요. 너무 높아도 위험하고, 너무 낮아도 점수는 평범하게 둬요. 우수: 50~200% · 50% 미만은 감점 없음 · 200% 초과는 위험",
        "range",
        50.0,
        200.0,
        True,
        "%",
    ),
    FilterSpec(
        "cash_months",
        "현금규모(개월)",
        "안전성 check!",
        "지금 현금으로 판관비를 몇 달이나 감당할 수 있는지예요. 우수: 12개월 이상",
        "min",
        12.0,
        None,
        True,
        "개월",
    ),
    # 수익/성장
    FilterSpec(
        "revenue_growth",
        "매출성장율",
        "수익/성장성 check!",
        "작년 대비 매출이 얼마나 늘었는지예요. 양호 0%↑ · 우수 40%↑ · 매우우수 80%↑",
        "min",
        40.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "gross_margin",
        "매출총이익율",
        "수익/성장성 check!",
        "물건 팔고 원가를 뺀 뒤 남는 비율이에요. 높을수록 본업 마진이 좋아요. 양호 20%↑ · 우수 30%↑ · 매우우수 50%↑",
        "min",
        30.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "operating_margin",
        "영업이익률",
        "수익/성장성 check!",
        "본업으로 남긴 이익 비율이에요. 양호 5%↑ · 우수 10%↑ · 매우우수 20%↑",
        "min",
        10.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "net_margin",
        "당기순이익율",
        "수익/성장성 check!",
        "이자·세금까지 반영한 최종 이익 비율이에요. 양호 3%↑ · 우수 8%↑ · 매우우수 15%↑",
        "min",
        8.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "revenue_minus_debt_growth",
        "매출−부채증가",
        "수익/성장성 check!",
        "매출 증가가 빚 증가보다 빠른지 봐요. 0 이상이면 성장이 빚보다 앞서요. 우수: 0%p 이상",
        "min",
        0.0,
        None,
        True,
        "%p",
    ),
    # 효율
    FilterSpec(
        "roa",
        "ROA",
        "효율성 check!",
        "회사가 가진 자산으로 얼마나 효율적으로 벌었는지예요. 우수: 5% 이상",
        "min",
        5.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "roe",
        "ROE",
        "효율성 check!",
        "주주 돈(자기자본)으로 얼마나 잘 벌었는지예요. 우수: 15% 이상",
        "min",
        15.0,
        None,
        True,
        "%",
    ),
    FilterSpec(
        "inventory_turnover",
        "재고회전율",
        "효율성 check!",
        "재고가 얼마나 빨리 팔려 나가는지예요. 높을수록 재고가 잘 돌아요. 우수: 4회 이상",
        "min",
        4.0,
        None,
        True,
        "회",
    ),
    FilterSpec(
        "receivable_turnover",
        "매출채권회전",
        "효율성 check!",
        "외상매출금을 얼마나 빨리 회수하는지예요. 높을수록 회수가 빨라요. 우수: 10회 이상",
        "min",
        10.0,
        None,
        True,
        "회",
    ),
    # 주가
    FilterSpec(
        "pct_from_avg_52w",
        "52주평균대비",
        "주가 현위치",
        "최근 1년 평균 주가보다 얼마나 낮은지예요. 바닥 구간을 찾을 때 써요. 우수: -20% 이하 · 매우우수: -50% 이하 · 구간으로 입력",
        "range",
        -80.0,
        -20.0,
        False,
        "%",
    ),
    FilterSpec(
        "range_position",
        "52주위치(%)",
        "주가 현위치",
        "1년 최저~최고가 사이에서 지금 주가가 어디쯤인지예요. 0%면 저가, 100%면 고가예요. 우수: 20% 이하 · 매우우수: 10% 이하 · 구간으로 입력",
        "range",
        0.0,
        20.0,
        False,
        "%",
    ),
    FilterSpec(
        "bottom_dwell_ratio",
        "52주 변동폭",
        "주가 현위치",
        "52주 저가 대비 고가가 얼마나 벌어졌는지예요. 낮을수록 박스처럼 힘이 압축된 구간이에요. 50%≈저가 대비 1.5배 · 100%≈두 배. 우수: 50% 이하",
        "max",
        None,
        50.0,
        False,
        "%",
    ),
]

SPEC_BY_KEY = {s.key: s for s in FILTER_SPECS}

ABS_SPECS = [
    ("market_cap", "시가총액"),
    ("revenue", "매출액"),
    ("operating_profit", "영업이익"),
    ("net_income", "당기순이익"),
]

# 시가총액은 주가 캐시 쪽 — 재무 필터와 분리 적용
PRICE_ABS_KEYS = {"market_cap"}

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

PRICE_FILTER_KEYS = {"pct_from_avg_52w", "bottom_dwell_ratio", "range_position", "market_cap"}


def categories_order() -> list[str]:
    seen = []
    for s in FILTER_SPECS:
        if s.category not in seen:
            seen.append(s.category)
    return seen


def specs_in_category(category: str) -> list[FilterSpec]:
    return [s for s in FILTER_SPECS if s.category == category]


# 매출성장율만 공통 구간 사용
REVENUE_GROWTH_KEY = "revenue_growth"

# 이익률 뱃지: (양호, 우수, 매우우수) — 필터 기본값은 우수
MARGIN_BADGE_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "gross_margin": (20.0, 30.0, 50.0),  # 20↑양호, 30↑우수, 50↑매우우수
    "operating_margin": (5.0, 10.0, 20.0),  # 5↑양호, 10↑우수, 20↑매우우수
    "net_margin": (3.0, 8.0, 15.0),  # 3↑양호, 8↑우수, 15↑매우우수
}

# 재고/채권 이상치 → 점수에서 제외
_OUTLIER_KEYS = {
    "inventory_months": (-0.01, 120.0),
    "inventory_turnover": (0.0, 200.0),
    "receivable_turnover": (0.0, 200.0),
}


def _row_get(row: pd.Series | dict[str, Any] | None, key: str) -> Any:
    if row is None:
        return None
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return None


def _as_float(val: Any) -> float | None:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def badge_for_value(
    spec: FilterSpec,
    value: float | None,
    row: pd.Series | dict[str, Any] | None = None,
) -> str:
    """우수 / 매우우수 / 보통(양호) / 주의 / 위험 / 해당없음"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "해당없음"

    # 현금흐름일치: 적자·순이익 없음은 점수 제외
    if spec.key == "cash_flow_match":
        ni = _as_float(_row_get(row, "net_income"))
        if ni is None or ni <= 0:
            return "해당없음"

    # 재고·매출채권 이상치 제외
    bounds = _OUTLIER_KEYS.get(spec.key)
    if bounds is not None:
        lo, hi = bounds
        if value <= lo or value > hi:
            return "해당없음"

    # 매출성장율: 0%↑ 양호, 40%↑ 우수, 80%↑ 매우우수
    if spec.key == REVENUE_GROWTH_KEY:
        if value >= 80:
            return "매우우수"
        if value >= 40:
            return "우수"
        if value >= 0:
            return "보통"  # UI에서 '양호'로 표시
        if value >= -20:
            return "주의"
        return "위험"

    # 이익률 3종: 지표별 양호/우수 기준
    if spec.key in MARGIN_BADGE_THRESHOLDS:
        good, excellent, very = MARGIN_BADGE_THRESHOLDS[spec.key]
        if value >= very:
            return "매우우수"
        if value >= excellent:
            return "우수"
        if value >= good:
            return "보통"  # UI에서 '양호'로 표시
        if value >= 0:
            return "주의"
        return "위험"

    # 52주평균대비: 바닥 포착 — 낮을수록(더 싼 구간) 가점
    if spec.key == "pct_from_avg_52w":
        if value <= -50:
            return "매우우수"
        if value <= -20:
            return "우수"
        if value <= 0:
            return "보통"
        if value <= 20:
            return "주의"
        return "위험"

    # 52주위치: 저~고 구간에서 낮은 쪽이 가점
    if spec.key == "range_position":
        if value <= 10:
            return "매우우수"
        if value <= 20:
            return "우수"
        if value <= 40:
            return "보통"
        if value <= 60:
            return "주의"
        return "위험"

    # range (debt): 50~200 우수, 200↑ 위험, 50↓ 중립
    if spec.direction == "range" and spec.key == "debt_ratio":
        lo, hi = spec.excellent_min, spec.excellent_max
        if lo is not None and hi is not None:
            if lo <= value <= hi:
                return "우수"
            if value > hi:
                return "위험"
            return "보통"  # below 50% — 감점하지 않음

    if spec.direction == "range":
        lo, hi = spec.excellent_min, spec.excellent_max
        if lo is not None and hi is not None and lo <= value <= hi:
            return "우수"
        return "보통"

    # max_change (sga decrease = good if value <= 0)
    if spec.direction == "max_change":
        if value <= -10:
            return "매우우수"
        if value <= 0:
            return "우수"
        if value <= 5:
            return "보통"
        if value <= 10:
            return "주의"
        return "위험"

    if spec.higher_better:
        exc = spec.excellent_min
        if exc is None:
            return "보통"
        very = exc * 2
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

# 카테고리 가중치 (합=1.0). 주가 비중↓ · 펀더멘털 비중↑
CATEGORY_WEIGHTS: dict[str, float] = {
    "수익/성장성 check!": 0.33,
    "안전성 check!": 0.23,
    "효율성 check!": 0.18,
    "B경제": 0.18,
    "주가 현위치": 0.08,
}

CATEGORY_LABELS: dict[str, str] = {
    "B경제": "B경제",
    "안전성 check!": "안전성",
    "수익/성장성 check!": "수익/성장성",
    "효율성 check!": "효율성",
    "주가 현위치": "주가 현위치",
}


def _category_score_from_avg(avg_badge: float) -> int:
    """뱃지 평균(-2~+2) → 0~100. avg=+2→100, 0→50, -2→0."""
    return int(max(0, min(100, round(50 + avg_badge * 25))))


def score_row(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    badges: dict[str, str] = {}
    cat_badge_sums: dict[str, float] = {c: 0.0 for c in categories_order()}
    cat_badge_counts: dict[str, int] = {c: 0 for c in categories_order()}

    for spec in FILTER_SPECS:
        val = row.get(spec.key) if hasattr(row, "get") else row[spec.key] if spec.key in row else None
        try:
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                val = float(val)
            else:
                val = None
        except (TypeError, ValueError):
            val = None
        badge = badge_for_value(spec, val, row)
        badges[spec.key] = badge
        if badge != "해당없음":
            cat_badge_sums[spec.category] += BADGE_SCORE[badge]
            cat_badge_counts[spec.category] += 1

    category_scores: dict[str, int | None] = {}
    weighted = 0.0
    weight_sum = 0.0
    for cat in categories_order():
        n = cat_badge_counts[cat]
        if n <= 0:
            category_scores[cat] = None
            continue
        avg = cat_badge_sums[cat] / n
        cat_score = _category_score_from_avg(avg)
        category_scores[cat] = cat_score
        w = CATEGORY_WEIGHTS.get(cat, 0.0)
        weighted += cat_score * w
        weight_sum += w

    attractiveness = int(round(weighted / weight_sum)) if weight_sum > 0 else 50
    attractiveness = max(0, min(100, attractiveness))
    grade = grade_for_score(attractiveness)

    # 디버그/정렬용: 가중 반영된 카테고리 평균 뱃지 점수
    raw = 0.0
    raw_w = 0.0
    for cat in categories_order():
        n = cat_badge_counts[cat]
        if n <= 0:
            continue
        w = CATEGORY_WEIGHTS.get(cat, 0.0)
        raw += (cat_badge_sums[cat] / n) * w
        raw_w += w
    score_raw = raw / raw_w if raw_w > 0 else 0.0

    counts = {k: 0 for k in BADGE_SCORE}
    for b in badges.values():
        counts[b] = counts.get(b, 0) + 1

    return {
        "badges": badges,
        "badge_counts": counts,
        "score_raw": score_raw,
        "category_scores": category_scores,
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
