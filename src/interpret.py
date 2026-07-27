"""Detail-tile value readings (what THIS number means)."""

from __future__ import annotations

import math
from typing import Any


def _num(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _badge_note(badge: str | None) -> str:
    if not badge or badge in ("해당없음", "—", "-"):
        return ""
    return f"평가: {badge}."


def interpret_metric(
    key: str,
    raw: Any,
    display: str,
    badge: str | None = None,
) -> str:
    """Return a short Korean reading for the current value."""
    v = _num(raw)
    note = _badge_note(badge)
    parts: list[str] = []

    if key == "inventory_months" and v is not None:
        parts.append(
            f"지금 재고를 현재 판매 속도로 팔면 약 {v:.2f}개월이면 소진된다는 뜻이에요."
        )
        if v <= 1:
            parts.append("재고가 매우 빨리 도는 편이에요.")
        elif v <= 3:
            parts.append("재고 부담이 작은 편이에요.")
        elif v <= 6:
            parts.append("보통 수준이에요.")
        else:
            parts.append("재고가 많아 현금이 묶일 수 있어요.")
    elif key == "cash_survival_years" and v is not None:
        parts.append(
            f"적자가 이어져도 보유 현금으로 약 {v:.2f}년은 버틸 수 있다는 뜻이에요."
        )
        if v >= 2:
            parts.append("현금 여유가 있는 편이에요.")
        elif v >= 1:
            parts.append("당장은 버틸 만해요.")
        else:
            parts.append("현금 여유가 짧은 편이에요.")
    elif key == "cash_months" and v is not None:
        parts.append(
            f"지금 현금만으로 판관비를 약 {v:.1f}개월 감당할 수 있다는 뜻이에요."
        )
        if v >= 12:
            parts.append("단기 현금 여유가 넉넉한 편이에요.")
        elif v >= 6:
            parts.append("보통~양호 수준이에요.")
        else:
            parts.append("현금 버퍼가 짧은 편이에요.")
    elif key == "cash_flow_match" and v is not None:
        # 보통 1.0=100% 배수로 저장, 큰 숫자는 이미 %로 온 경우
        if abs(v) < 20:
            pct, ratio = v * 100, v
        else:
            pct, ratio = v, v / 100.0
        parts.append(
            f"장부상 이익 대비 실제 현금이 약 {pct:.1f}% 들어온다는 뜻이에요."
        )
        if ratio >= 1:
            parts.append("이익이 현금으로 잘 들어오는 편이에요.")
        else:
            parts.append("이익 대비 현금 유입이 약한 편이에요.")
    elif key == "sga_ratio_change" and v is not None:
        if v < 0:
            parts.append(
                f"판관비 비중이 작년보다 {abs(v):.1f}%p 줄었다는 뜻이에요. 비용 관리가 좋아진 신호예요."
            )
        elif v == 0:
            parts.append("판관비 비중이 작년과 비슷하다는 뜻이에요.")
        else:
            parts.append(
                f"판관비 비중이 작년보다 {v:.1f}%p 늘었다는 뜻이에요. 비용 부담이 커졌을 수 있어요."
            )
    elif key == "sga_ratio" and v is not None:
        parts.append(
            f"매출 중 판관비(영업비용)가 약 {v:.1f}%를 차지한다는 뜻이에요."
        )
    elif key == "current_ratio" and v is not None:
        parts.append(
            f"1년 안 갚을 빚을 당장 쓸 자산으로 {v:.0f}% 감당한다는 뜻이에요."
        )
        if v >= 100:
            parts.append("단기 지급 여력이 있는 편이에요.")
        else:
            parts.append("단기 빚 부담이 자산보다 큰 편이에요.")
    elif key == "quick_ratio" and v is not None:
        parts.append(
            f"재고를 빼고 봐도 단기 빚을 {v:.0f}% 감당한다는 뜻이에요."
        )
        if v >= 100:
            parts.append("단기 안전성이 괜찮은 편이에요.")
        else:
            parts.append("재고 없이 보면 단기 여유가 부족한 편이에요.")
    elif key == "debt_ratio" and v is not None:
        parts.append(f"자기자본 대비 빚이 약 {v:.0f}%라는 뜻이에요.")
        if v < 50:
            parts.append("빚이 매우 적은 편이에요.")
        elif v <= 200:
            parts.append("보통~적정 구간에 가까워요.")
        else:
            parts.append("빚 비중이 높은 편이에요.")
    elif key == "revenue_growth" and v is not None:
        if v >= 0:
            parts.append(f"작년보다 매출이 약 {v:.1f}% 늘었다는 뜻이에요.")
        else:
            parts.append(f"작년보다 매출이 약 {abs(v):.1f}% 줄었다는 뜻이에요.")
    elif key == "gross_margin" and v is not None:
        parts.append(f"물건 팔고 원가를 뺀 뒤 약 {v:.1f}%가 남는다는 뜻이에요.")
    elif key == "operating_margin" and v is not None:
        parts.append(f"본업으로 매출의 약 {v:.1f}%를 이익으로 남긴다는 뜻이에요.")
    elif key == "net_margin" and v is not None:
        parts.append(
            f"이자·세금까지 반영해 매출의 약 {v:.1f}%가 최종 이익이라는 뜻이에요."
        )
    elif key == "roa" and v is not None:
        parts.append(f"보유 자산으로 약 {v:.1f}%의 이익을 냈다는 뜻이에요.")
    elif key == "roe" and v is not None:
        parts.append(f"주주 자본으로 약 {v:.1f}%의 이익을 냈다는 뜻이에요.")
    elif key == "inventory_turnover" and v is not None:
        parts.append(f"재고가 1년에 약 {v:.2f}번 팔려 나간다는 뜻이에요.")
        if v >= 4:
            parts.append("재고 회전이 빠른 편이에요.")
        else:
            parts.append("재고가 상대적으로 천천히 도는 편이에요.")
    elif key == "receivable_turnover" and v is not None:
        parts.append(f"외상매출금이 1년에 약 {v:.2f}번 회수된다는 뜻이에요.")
        if v >= 10:
            parts.append("회수가 빠른 편이에요.")
        else:
            parts.append("회수가 다소 느린 편이에요.")
    elif key == "revenue_minus_debt_growth" and v is not None:
        if v >= 0:
            parts.append(
                f"매출 증가가 빚 증가보다 {v:.1f}%p 앞서 있다는 뜻이에요."
            )
        else:
            parts.append(
                f"빚 증가가 매출 증가보다 {abs(v):.1f}%p 빠르다는 뜻이에요."
            )
    elif key == "pct_from_avg_52w" and v is not None:
        if v < 0:
            parts.append(
                f"최근 1년 평균 주가보다 약 {abs(v):.1f}% 낮다는 뜻이에요."
            )
        elif v > 0:
            parts.append(
                f"최근 1년 평균 주가보다 약 {v:.1f}% 높다는 뜻이에요."
            )
        else:
            parts.append("최근 1년 평균 주가와 비슷한 수준이에요.")
    elif key == "bottom_dwell_ratio" and v is not None:
        parts.append(
            f"최근 기간 중 약 {v:.1f}%를 바닥권에서 보냈다는 뜻이에요."
        )
        if v >= 50:
            parts.append("오래 눌려 있었던 편이에요.")
        else:
            parts.append("바닥권에 머문 비중은 크지 않아요.")
    elif key == "range_position" and v is not None:
        parts.append(
            f"1년 최저~최고가 사이에서 아래에서부터 약 {v:.1f}% 지점이라는 뜻이에요."
        )
        if v <= 20:
            parts.append("저가권에 가까운 편이에요.")
        elif v >= 80:
            parts.append("고가권에 가까운 편이에요.")
        else:
            parts.append("중간 구간에 있어요.")
    elif key == "market_cap":
        parts.append(f"회사 전체 시가총액이 {display}예요.")
    elif key == "current_price":
        parts.append(f"최근 종가가 {display}예요.")
    elif key == "avg_52w":
        parts.append(f"최근 약 1년 종가 평균이 {display}예요.")
    elif key == "revenue":
        parts.append(f"한 해 매출 규모가 {display}예요.")
    elif key == "operating_profit":
        parts.append(f"본업 이익(영업이익) 규모가 {display}예요.")
    elif key == "net_income":
        parts.append(f"최종 이익(당기순이익) 규모가 {display}예요.")
    elif key == "low_high_52w":
        parts.append(f"최근 약 1년 최저가/최고가가 {display}예요.")
    elif display and display != "-":
        parts.append(f"현재 값은 {display}예요.")

    if note:
        parts.append(note)
    return " ".join(parts).strip()
