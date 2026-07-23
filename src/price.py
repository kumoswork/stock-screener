"""Daily price / bottom-position metrics (Naver-first, hard timeouts)."""

from __future__ import annotations

import ast
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests

_NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}


def _run_with_timeout(fn, timeout_s: float):
    """Run fn in a daemon thread; return None on timeout (do not block forever)."""
    box: dict = {}

    def _target() -> None:
        try:
            box["v"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["e"] = exc

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None
    if "e" in box:
        return None
    return box.get("v")


def _naver_ohlcv(code: str, start_s: str, end_s: str) -> pd.DataFrame | None:
    start = start_s.replace("-", "")
    end = end_s.replace("-", "")
    url = (
        "https://api.finance.naver.com/siseJson.naver"
        f"?symbol={code}&requestType=1&startTime={start}&endTime={end}&timeframe=day"
    )
    resp = requests.get(url, headers=_NAVER_HEADERS, timeout=(3, 8))
    resp.raise_for_status()
    text = (resp.text or "").strip()
    if not text or text[0] != "[":
        return None
    data = ast.literal_eval(text)
    if not isinstance(data, list) or len(data) < 2:
        return None
    rows = []
    for item in data[1:]:
        if not item or len(item) < 5:
            continue
        try:
            rows.append(
                {
                    "Date": pd.to_datetime(str(item[0]), format="%Y%m%d"),
                    "Open": float(item[1]),
                    "High": float(item[2]),
                    "Low": float(item[3]),
                    "Close": float(item[4]),
                }
            )
        except (TypeError, ValueError):
            continue
    if not rows:
        return None
    return pd.DataFrame(rows).set_index("Date").sort_index()


def _yahoo_ohlcv(code: str, start_s: str, end_s: str, market: str | None) -> pd.DataFrame | None:
    import yfinance as yf

    suffixes: list[str]
    m = (market or "").upper()
    if m == "KOSPI":
        suffixes = [".KS", ".KQ"]
    elif m == "KOSDAQ":
        suffixes = [".KQ", ".KS"]
    else:
        suffixes = [".KS", ".KQ"]

    for suffix in suffixes:
        hist = yf.Ticker(f"{code}{suffix}").history(start=start_s, end=end_s, auto_adjust=False)
        if hist is not None and not hist.empty:
            return hist
    return None


def _fdr_ohlcv(code: str, start_s: str, end_s: str) -> pd.DataFrame | None:
    import FinanceDataReader as fdr

    ohlcv = fdr.DataReader(code, start_s, end_s)
    if ohlcv is None or ohlcv.empty:
        return None
    return ohlcv


def _metrics_from_ohlcv(
    code: str,
    ohlcv: pd.DataFrame,
    lookback_days: int,
    dwell_days: int,
    bottom_band_pct: float,
) -> dict | None:
    recent = ohlcv.tail(lookback_days)
    if recent.empty:
        return None

    low_col = "Low" if "Low" in recent.columns else "저가"
    high_col = "High" if "High" in recent.columns else "고가"
    close_col = "Close" if "Close" in recent.columns else "종가"
    if low_col not in recent.columns or close_col not in recent.columns:
        return None

    low_52w = float(recent[low_col].min())
    high_52w = float(recent[high_col].max()) if high_col in recent.columns else low_52w
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


def _compute_one(
    code: str,
    start_s: str,
    end_s: str,
    lookback_days: int,
    dwell_days: int,
    bottom_band_pct: float,
    market: str | None = None,
    per_stock_timeout: float = 12.0,
) -> dict | None:
    def _fetch() -> dict | None:
        ohlcv = None
        # 1) Naver (국내·리츠 포함, 빠름)
        try:
            ohlcv = _naver_ohlcv(code, start_s, end_s)
        except Exception:
            ohlcv = None

        # 2) Yahoo (시장 접미사 우선)
        if ohlcv is None or ohlcv.empty:
            try:
                ohlcv = _yahoo_ohlcv(code, start_s, end_s, market)
            except Exception:
                ohlcv = None

        # 3) FDR
        if ohlcv is None or ohlcv.empty:
            try:
                ohlcv = _fdr_ohlcv(code, start_s, end_s)
            except Exception:
                return None

        if ohlcv is None or ohlcv.empty:
            return None
        return _metrics_from_ohlcv(code, ohlcv, lookback_days, dwell_days, bottom_band_pct)

    return _run_with_timeout(_fetch, per_stock_timeout)


def fetch_price_metrics(
    stock_codes: list[str],
    corp_names: dict[str, str] | None = None,
    lookback_days: int = 365,
    dwell_days: int = 120,
    bottom_band_pct: float = 25.0,
    progress_callback=None,
    max_workers: int = 12,
    markets: dict[str, str] | None = None,
    per_stock_timeout: float = 12.0,
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
                (markets or {}).get(code),
                per_stock_timeout,
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
                row = fut.result(timeout=1)
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
