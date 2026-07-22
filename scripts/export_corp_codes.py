"""Export DART listed corp codes to data/corp_codes_listed.csv (run locally in Korea)."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

import os  # noqa: E402

from dart_api import DartClient  # noqa: E402


def main() -> None:
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit("DART_API_KEY missing in .env")

    client = DartClient(api_key)
    df = client.download_corp_codes()
    listed = df[df["stock_code"].notna() & (df["stock_code"] != "")]
    listed = listed[listed["stock_code"].str.strip() != ""]
    out = ROOT / "data" / "corp_codes_listed.csv"
    out.parent.mkdir(exist_ok=True)
    listed[["corp_code", "corp_name", "stock_code", "modify_date"]].to_csv(out, index=False)
    print(f"Saved {len(listed)} rows to {out}")


if __name__ == "__main__":
    main()
