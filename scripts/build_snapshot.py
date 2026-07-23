"""
로컬에서 네이버(Wisereport) 연간 재무 스냅샷을 만듭니다. (한국 네트워크 권장)

사용:
  python scripts/build_snapshot.py
  python scripts/build_snapshot.py --limit 30 --year 2025 --prev 2024
  python scripts/build_snapshot.py --market KOSPI --sleep 0.1

완성된 data/financials_snapshot.csv 를 GitHub에 push하면
Streamlit Cloud는 필터만 즉시 수행합니다.

참고: --source dart 는 예전 DART OpenAPI 경로(키 필요).
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

import pandas as pd  # noqa: E402

from naver_finance import build_metrics_dataframe  # noqa: E402
from snapshot import save_financials  # noqa: E402

CORP_CSV = ROOT / "data" / "corp_codes_listed.csv"


def _load_corps(market: str) -> pd.DataFrame:
    if not CORP_CSV.exists():
        raise SystemExit(f"회사목록 없음: {CORP_CSV}")
    df = pd.read_csv(CORP_CSV, dtype={"stock_code": str})
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    if market != "ALL" and "market" in df.columns:
        df = df[df["market"] == market].copy()
    return df.reset_index(drop=True)


def _build_naver(args: argparse.Namespace) -> pd.DataFrame:
    corps = _load_corps(args.market)
    print(f"[1/2] 회사목록 {len(corps)}개 (bundled CSV, market={args.market})")
    print(f"[2/2] 네이버 연간 재무 수집 year={args.year} prev={args.prev}")

    t0 = time.time()

    def progress(cur: int, total: int, name: str) -> None:
        if cur == 1 or cur % 20 == 0 or cur == total:
            print(f"  {cur}/{total} {name}", flush=True)

    financials = build_metrics_dataframe(
        corps,
        args.year,
        args.prev,
        sleep=args.sleep,
        progress=progress,
        limit=args.limit,
        workers=args.workers,
    )
    print(f"  metrics rows={len(financials)}  elapsed={time.time() - t0:.0f}s")
    return financials


def _build_dart(args: argparse.Namespace) -> pd.DataFrame:
    from dart_api import DartClient, load_listed_corps  # noqa: WPS433
    from metrics import load_financial_metrics  # noqa: WPS433

    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART_API_KEY missing in .env")

    client = DartClient(api_key)
    print("[1/3] 회사목록 (번들 CSV)")
    bundled = client._load_bundled_corp_codes()
    if bundled is None or bundled.empty:
        raise SystemExit("data/corp_codes_listed.csv 가 없습니다.")
    count = client._save_corp_codes_df(bundled)
    print(f"  -> {count}개 (bundled)")

    corps = load_listed_corps(args.market)
    if args.limit and args.limit > 0:
        corps = corps.head(args.limit)
    codes = corps["stock_code"].tolist()
    print(f"[2/3] DART 재무제표 {len(codes)}종목 × ({args.prev}, {args.year})")

    def progress(cur, total, name):
        if cur == 1 or cur % 20 == 0 or cur == total:
            print(f"  {cur}/{total} {name}", flush=True)

    t0 = time.time()
    saved_prev = client.sync_financials(codes, args.prev, progress)
    print(f"  prev year saved={saved_prev}")
    saved_cur = client.sync_financials(codes, args.year, progress)
    print(f"  cur year saved={saved_cur}  elapsed={time.time() - t0:.0f}s")

    print("[3/3] 지표 계산")
    financials = load_financial_metrics(args.year, args.prev)
    if "market" in corps.columns and not financials.empty:
        financials = financials.merge(corps[["stock_code", "market"]], on="stock_code", how="left")
    print(f"  metrics rows={len(financials)}")
    return financials


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", default="2025")
    parser.add_argument("--prev", default="2024")
    parser.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체")
    parser.add_argument("--sleep", type=float, default=0.05, help="네이버 요청 간격(초)")
    parser.add_argument("--workers", type=int, default=6, help="네이버 병렬 수집 워커")
    parser.add_argument(
        "--source",
        default="naver",
        choices=["naver", "dart"],
        help="재무 소스 (기본: naver)",
    )
    args = parser.parse_args()

    if args.source == "naver":
        financials = _build_naver(args)
        note = (
            f"source=naver market={args.market} year={args.year} "
            f"prev={args.prev} n={len(financials)}"
        )
    else:
        financials = _build_dart(args)
        note = (
            f"source=dart market={args.market} year={args.year} "
            f"prev={args.prev} n={len(financials)}"
        )

    if financials.empty:
        raise SystemExit("재무 지표가 비었습니다. 네트워크/연도를 확인하세요.")

    path = save_financials(financials, note=note)
    print(f"DONE -> {path} ({len(financials)} rows)")
    print("주가는 앱에서 결과 종목만 조회합니다.")


if __name__ == "__main__":
    main()
