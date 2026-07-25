"""기존 price_cache.csv 에 시가총액(market_cap)만 붙여 갱신합니다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from price import attach_market_caps, load_price_metrics, save_price_metrics  # noqa: E402


def main() -> None:
    df = load_price_metrics()
    if df.empty:
        raise SystemExit("data/price_cache.csv 가 비어 있습니다.")
    out = attach_market_caps(df)
    filled = int(out["market_cap"].notna().sum()) if "market_cap" in out.columns else 0
    path = save_price_metrics(out)
    print(f"market_cap filled={filled}/{len(out)} path={path}")


if __name__ == "__main__":
    main()
