"""
로컬에서 전 종목 주가 지표 캐시를 만듭니다. (한국 네트워크 권장)

사용:
  python scripts/build_price_cache.py
  python scripts/build_price_cache.py --limit 50 --workers 16

완성된 data/price_cache.csv 를 GitHub에 push하면
Streamlit Cloud 스크리닝이 캐시만으로 즉시 동작합니다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from price import fetch_price_metrics, save_price_metrics  # noqa: E402
from snapshot import FINANCIALS_PATH, load_financials  # noqa: E402

CORP_CSV = ROOT / "data" / "corp_codes_listed.csv"


def _load_universe(market: str) -> pd.DataFrame:
    if FINANCIALS_PATH.exists():
        df = load_financials()
    elif CORP_CSV.exists():
        df = pd.read_csv(CORP_CSV, dtype={"stock_code": str})
        df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    else:
        raise SystemExit("financials_snapshot.csv 또는 corp_codes_listed.csv 가 필요합니다.")

    if market != "ALL" and "market" in df.columns:
        df = df[df["market"] == market].copy()
    cols = [c for c in ("stock_code", "corp_name", "market") if c in df.columns]
    return df[cols].drop_duplicates("stock_code").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build price metrics cache CSV")
    ap.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    ap.add_argument("--limit", type=int, default=0, help="0=전체")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    universe = _load_universe(args.market)
    if args.limit and args.limit > 0:
        universe = universe.head(args.limit).copy()

    codes = universe["stock_code"].astype(str).str.zfill(6).tolist()
    name_map = dict(zip(codes, universe.get("corp_name", pd.Series(codes)).astype(str)))
    market_map = None
    if "market" in universe.columns:
        market_map = dict(
            zip(codes, universe["market"].astype(str).fillna("").tolist())
        )

    print(f"[1/1] 주가 지표 수집 {len(codes)}종목 workers={args.workers}")
    t0 = time.time()

    def progress(cur: int, total: int, name: str) -> None:
        if cur == 1 or cur % 25 == 0 or cur == total:
            print(f"  {cur}/{total} {name}", flush=True)

    prices = fetch_price_metrics(
        codes,
        name_map,
        progress_callback=progress,
        max_workers=args.workers,
        markets=market_map,
        per_stock_timeout=args.timeout,
    )
    path = save_price_metrics(prices)
    print(
        f"done rows={len(prices)}/{len(codes)}  "
        f"elapsed={time.time() - t0:.0f}s  path={path}"
    )


if __name__ == "__main__":
    main()
