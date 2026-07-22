"""
로컬에서 재무+주가 스냅샷을 미리 만듭니다. (한국 네트워크 권장)

사용:
  .\\.venv\\Scripts\\python.exe scripts\\build_snapshot.py
  .\\.venv\\Scripts\\python.exe scripts\\build_snapshot.py --limit 500 --year 2025 --prev 2024
  .\\.venv\\Scripts\\python.exe scripts\\build_snapshot.py --market KOSPI

완성된 data/screener_snapshot.csv 를 GitHub에 push하면
Streamlit Cloud는 필터만 즉시 수행합니다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

import os  # noqa: E402

from dart_api import DartClient, load_listed_corps  # noqa: E402
from metrics import load_financial_metrics  # noqa: E402
from price import fetch_price_metrics  # noqa: E402
from screener import merge_financial_and_price  # noqa: E402
from snapshot import save_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2025")
    parser.add_argument("--prev", default="2024")
    parser.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체")
    parser.add_argument("--skip-price", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.08, help="API 호출 간격(초)")
    args = parser.parse_args()

    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART_API_KEY missing in .env")

    client = DartClient(api_key)

    print("[1/4] 회사목록 (번들 CSV 강제 로드)")
    # 구캐시(상장폐지 포함) 무시하고 번들로 교체
    bundled = client._load_bundled_corp_codes()
    if bundled is None or bundled.empty:
        raise SystemExit("data/corp_codes_listed.csv 가 없습니다.")
    count = client._save_corp_codes_df(bundled)
    print(f"  -> {count}개 (bundled)")

    corps = load_listed_corps(args.market)
    if args.limit and args.limit > 0:
        corps = corps.head(args.limit)
    codes = corps["stock_code"].tolist()
    print(f"[2/4] 재무제표 {len(codes)}종목 × ({args.prev}, {args.year})")

    # temporarily tighten sleep used inside sync by wrapping progress
    original_sleep = time.sleep

    def progress(cur, total, name):
        if cur == 1 or cur % 20 == 0 or cur == total:
            print(f"  {cur}/{total} {name}", flush=True)

    # Patch sleep in dart_api module via monkeypatch of time.sleep duration
    # Keep default sleep inside sync_financials; use --sleep by adjusting after each batch year
    t0 = time.time()
    saved_prev = client.sync_financials(codes, args.prev, progress)
    print(f"  prev year saved={saved_prev}")
    saved_cur = client.sync_financials(codes, args.year, progress)
    print(f"  cur year saved={saved_cur}  elapsed={time.time()-t0:.0f}s")

    print("[3/4] 지표 계산")
    financials = load_financial_metrics(args.year, args.prev)
    print(f"  metrics rows={len(financials)}")

    prices = None
    if not args.skip_price and not financials.empty:
        print("[4/4] 주가/바닥지표")
        name_map = dict(zip(financials["stock_code"], financials["corp_name"]))

        def pprog(cur, total, name):
            if cur == 1 or cur % 50 == 0 or cur == total:
                print(f"  price {cur}/{total} {name}", flush=True)

        prices = fetch_price_metrics(
            financials["stock_code"].tolist(),
            name_map,
            progress_callback=pprog,
        )
        print(f"  price rows={len(prices)}")
    else:
        print("[4/4] 주가 스킵")

    merged = merge_financial_and_price(
        financials,
        prices if prices is not None else __import__("pandas").DataFrame(),
    )
    if merged.empty:
        raise SystemExit("재무 지표가 비었습니다. corp 목록/연도를 확인하세요.")

    if "market" in corps.columns and "stock_code" in merged.columns:
        merged = merged.merge(corps[["stock_code", "market"]], on="stock_code", how="left")

    path = save_snapshot(
        merged,
        note=f"market={args.market} year={args.year} prev={args.prev} n={len(merged)}",
    )
    print(f"DONE -> {path} ({len(merged)} rows)")
    print("GitHub에 push 후 Streamlit 앱은 필터만 즉시 동작합니다.")


if __name__ == "__main__":
    main()
