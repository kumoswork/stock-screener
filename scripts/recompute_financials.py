"""로컬 screener.db 기준으로 재무 스냅샷만 재계산 (DART 재호출 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metrics import load_financial_metrics  # noqa: E402
from snapshot import load_financials, save_financials  # noqa: E402


def main() -> None:
    year, prev = "2025", "2024"
    print(f"recompute metrics {year}/{prev} from local DB...")
    financials = load_financial_metrics(year, prev)
    if financials.empty:
        raise SystemExit("metrics empty — screener.db 재무 데이터 확인")

    old = load_financials()
    if not old.empty and "market" in old.columns:
        m = old[["stock_code", "market"]].drop_duplicates()
        financials["stock_code"] = financials["stock_code"].astype(str).str.zfill(6)
        m["stock_code"] = m["stock_code"].astype(str).str.zfill(6)
        financials = financials.drop(columns=[c for c in ["market"] if c in financials.columns], errors="ignore")
        financials = financials.merge(m, on="stock_code", how="left")

    # sanity: 강원랜드
    hit = financials[financials["stock_code"].astype(str).str.zfill(6) == "035250"]
    if not hit.empty:
        ni = hit.iloc[0].get("net_income")
        print(f"강원랜드 net_income = {ni}")

    path = save_financials(
        financials,
        note=f"market=ALL year={year} prev={prev} n={len(financials)} recompute_net_income_fix",
    )
    print(f"DONE -> {path} rows={len(financials)}")


if __name__ == "__main__":
    main()
