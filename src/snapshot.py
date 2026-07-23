"""Financial snapshot (yearly) + optional price merge helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FINANCIALS_PATH = DATA_DIR / "financials_snapshot.csv"
FINANCIALS_META = DATA_DIR / "financials_snapshot_meta.txt"
# legacy combined snapshot (migration fallback)
LEGACY_SNAPSHOT = DATA_DIR / "screener_snapshot.csv"

PRICE_COLS = [
    "current_price",
    "low_52w",
    "high_52w",
    "avg_52w",
    "pct_from_avg_52w",
    "range_position",
    "bottom_dwell_ratio",
]


def financials_exists() -> bool:
    return FINANCIALS_PATH.exists() or LEGACY_SNAPSHOT.exists()


def load_financials() -> pd.DataFrame:
    if FINANCIALS_PATH.exists():
        df = pd.read_csv(FINANCIALS_PATH, dtype={"stock_code": str})
    elif LEGACY_SNAPSHOT.exists():
        df = pd.read_csv(LEGACY_SNAPSHOT, dtype={"stock_code": str})
        drop = [c for c in PRICE_COLS if c in df.columns]
        df = df.drop(columns=drop, errors="ignore")
    else:
        return pd.DataFrame()

    if "stock_code" in df.columns:
        df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    return df


def save_financials(df: pd.DataFrame, note: str = "") -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = df.drop(columns=[c for c in PRICE_COLS if c in df.columns], errors="ignore")
    out.to_csv(FINANCIALS_PATH, index=False)
    FINANCIALS_META.write_text(
        f"updated_at={datetime.now().isoformat(timespec='seconds')}\n"
        f"rows={len(out)}\n"
        f"note={note}\n",
        encoding="utf-8",
    )
    return FINANCIALS_PATH


def financials_meta() -> str:
    if FINANCIALS_META.exists():
        return FINANCIALS_META.read_text(encoding="utf-8")
    if FINANCIALS_PATH.exists():
        return f"rows={len(pd.read_csv(FINANCIALS_PATH))}\n"
    if LEGACY_SNAPSHOT.exists():
        return f"(legacy) rows={len(pd.read_csv(LEGACY_SNAPSHOT))}\n"
    return "재무 스냅샷 없음"


def financials_basis_caption() -> str:
    """UI용 짧은 기준 문구. 예: 기준: 2025년 재무제표 (네이버)"""
    import re

    meta = financials_meta()
    m = re.search(r"year=(\d{4})", meta)
    year = m.group(1) if m else "2025"
    src = "네이버" if "source=naver" in meta or "naver" in meta.lower() else (
        "DART" if "source=dart" in meta else "네이버"
    )
    return f"기준: {year}년 재무제표 ({src})"


# backward-compatible aliases used by older scripts
def snapshot_exists() -> bool:
    return financials_exists()


def load_snapshot() -> pd.DataFrame:
    return load_financials()


def save_snapshot(df: pd.DataFrame, note: str = "") -> Path:
    return save_financials(df, note=note)


def snapshot_meta() -> str:
    return financials_meta()
