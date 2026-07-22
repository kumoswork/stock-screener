"""Daily price / bottom-position metrics (refreshed separately from financials)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd


def _compute_one(
    code: str,
    start_s: str,
    end_s: str,
    lookback_days: int,
    dwell_days: int,
    bottom_band_pct: float,
) -> dict | None:
    ohlcv = None
    # 1) Yahoo (클라우드에서 더 잘 됨)
    try:
        import yfinance as yf

        for suffix in (".KS", ".KQ"):
            ticker = yf.Ticker(f"{code}{suffix}")
            hist = ticker.history(start=start_s, end=end_s, auto_adjust=False)
            if hist is not None and not hist.empty:
                ohlcv = hist.rename(
                    columns={"Low": "Low", "High": "High", "Close": "Close"}
                )
                break
    except Exception:
        ohlcv = None

    # 2) FinanceDataReader fallback
    if ohlcv is None or ohlcv.empty:
        try:
            import FinanceDataReader as fdr

            ohlcv = fdr.DataReader(code, start_s, end_s)
        except Exception:
            return None

    if ohlcv is None or ohlcv.empty:
        return None

    recent = ohlcv.tail(lookback_days)
    if recent.empty:
        return None

    low_col = "Low" if "Low" in recent.columns else "저가"
    high_col = "High" if "High" in recent.columns else "고가"
    close_col = "Close" if "Close" in recent.columns else "종가"
    if low_col not in recent.columns or close_col not in recent.columns:
        return None

    low_52w = float(recent[low_col].min())
    high_52w = float(recent[high_col].max())
    current = float(recent[close_col].iloc[-1])
    if low_52w <= 0:
        return None

    pct_from_low = (current - low_52w) / low_52w * 100
    range_position = (
        (current - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 0.0
    )
    band_top = low_52w + (high_52w - low_52w) * (bottom_band_pct / 100)
    dwell_window = recent.tail(dwell_days)
    if len(dwell_window) > 0:
        near_bottom_days = int((dwell_window[close_col] <= band_top).sum())
        bottom_dwell_ratio = near_bottom_days / len(dwell_window) * 100
    else:
        bottom_dwell_ratio = None

    return {
        "stock_code": code,
        "current_price": current,
        "low_52w": low_52w,
        "high_52w": high_52w,
        "pct_from_low": round(pct_from_low, 2),
        "range_position": round(range_position, 2),
        "bottom_dwell_ratio": round(bottom_dwell_ratio, 2) if bottom_dwell_ratio is not None else None,
    }


def fetch_price_metrics(
    stock_codes: list[str],
    corp_names: dict[str, str] | None = None,
    lookback_days: int = 365,
    dwell_days: int = 120,
    bottom_band_pct: float = 25.0,
    progress_callback=None,
    max_workers: int = 8,
) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=lookback_days + 40)
    end_s = end.strftime("%Y-%m-%d")
    start_s = start.strftime("%Y-%m-%d")

    codes = [str(c).zfill(6) for c in stock_codes]
    rows: list[dict] = []
    total = len(codes)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _compute_one,
                code,
                start_s,
                end_s,
                lookback_days,
                dwell_days,
                bottom_band_pct,
            ): code
            for code in codes
        }
        for fut in as_completed(futures):
            done += 1
            code = futures[fut]
            if progress_callback:
                name = (corp_names or {}).get(code, code)
                progress_callback(done, total, name)
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                row["corp_name"] = (corp_names or {}).get(code, "")
                rows.append(row)

    return pd.DataFrame(rows)


def save_price_metrics(df: pd.DataFrame) -> None:
    """Optional local cache — kept for build scripts; app uses session state."""
    if df.empty:
        return
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "price_cache.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out.to_csv(path, index=False)


def load_price_metrics() -> pd.DataFrame:
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "price_cache.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"stock_code": str})
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    return df
