"""KRX price data and bottom-position metrics."""

from __future__ import annotations

from datetime import datetime, timedelta

import FinanceDataReader as fdr
import pandas as pd

from dart_api import get_db, init_db


def fetch_price_metrics(
    stock_codes: list[str],
    corp_names: dict[str, str] | None = None,
    lookback_days: int = 365,
    dwell_days: int = 120,
    bottom_band_pct: float = 25.0,
    progress_callback=None,
) -> pd.DataFrame:
    """Compute bottom-focused price metrics for each ticker."""
    end = datetime.today()
    start = end - timedelta(days=lookback_days + 30)
    end_s = end.strftime("%Y-%m-%d")
    start_s = start.strftime("%Y-%m-%d")

    rows = []
    total = len(stock_codes)
    for i, code in enumerate(stock_codes):
        if progress_callback:
            progress_callback(i + 1, total, corp_names.get(code, code) if corp_names else code)
        try:
            ohlcv = fdr.DataReader(code, start_s, end_s)
        except Exception:
            continue
        if ohlcv is None or ohlcv.empty:
            continue

        recent = ohlcv.tail(lookback_days)
        if recent.empty:
            continue

        low_col = "Low" if "Low" in recent.columns else "저가"
        high_col = "High" if "High" in recent.columns else "고가"
        close_col = "Close" if "Close" in recent.columns else "종가"

        low_52w = float(recent[low_col].min())
        high_52w = float(recent[high_col].max())
        current = float(recent[close_col].iloc[-1])

        if low_52w <= 0:
            continue

        pct_from_low = (current - low_52w) / low_52w * 100
        range_position = (
            (current - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 0.0
        )

        band_top = low_52w + (high_52w - low_52w) * (bottom_band_pct / 100)
        dwell_window = recent.tail(dwell_days)
        if len(dwell_window) > 0:
            near_bottom_days = (dwell_window[close_col] <= band_top).sum()
            bottom_dwell_ratio = near_bottom_days / len(dwell_window) * 100
        else:
            bottom_dwell_ratio = None

        rows.append(
            {
                "stock_code": code,
                "corp_name": (corp_names or {}).get(code, ""),
                "current_price": current,
                "low_52w": low_52w,
                "high_52w": high_52w,
                "pct_from_low": round(pct_from_low, 2),
                "range_position": round(range_position, 2),
                "bottom_dwell_ratio": round(bottom_dwell_ratio, 2) if bottom_dwell_ratio is not None else None,
            }
        )

    return pd.DataFrame(rows)


def save_price_metrics(df: pd.DataFrame) -> None:
    if df.empty:
        return
    conn = get_db()
    init_db(conn)
    now = datetime.now().isoformat(timespec="seconds")
    for _, row in df.iterrows():
        conn.execute(
            """
            INSERT OR REPLACE INTO price_metrics
            (stock_code, corp_name, current_price, low_52w, high_52w,
             pct_from_low, range_position, bottom_dwell_ratio, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["stock_code"],
                row.get("corp_name", ""),
                row.get("current_price"),
                row.get("low_52w"),
                row.get("high_52w"),
                row.get("pct_from_low"),
                row.get("range_position"),
                row.get("bottom_dwell_ratio"),
                now,
            ),
        )
    conn.commit()
    conn.close()


def load_price_metrics() -> pd.DataFrame:
    conn = get_db()
    init_db(conn)
    df = pd.read_sql("SELECT * FROM price_metrics", conn)
    conn.close()
    return df
