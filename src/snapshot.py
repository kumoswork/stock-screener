"""Load/save prebuilt screener snapshot for instant filtering."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_PATH = DATA_DIR / "screener_snapshot.csv"
META_PATH = DATA_DIR / "screener_snapshot_meta.txt"


def snapshot_exists() -> bool:
    return SNAPSHOT_PATH.exists()


def load_snapshot() -> pd.DataFrame:
    if not SNAPSHOT_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(SNAPSHOT_PATH, dtype={"stock_code": str})


def save_snapshot(df: pd.DataFrame, note: str = "") -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SNAPSHOT_PATH, index=False)
    META_PATH.write_text(
        f"updated_at={datetime.now().isoformat(timespec='seconds')}\n"
        f"rows={len(df)}\n"
        f"note={note}\n",
        encoding="utf-8",
    )
    return SNAPSHOT_PATH


def snapshot_meta() -> str:
    if META_PATH.exists():
        return META_PATH.read_text(encoding="utf-8")
    if SNAPSHOT_PATH.exists():
        return f"rows={len(pd.read_csv(SNAPSHOT_PATH))}\n"
    return "스냅샷 없음"
