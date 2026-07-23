"""Naver(Wisereport) annual financial statements → normalized account amounts (원)."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import pandas as pd
import requests

from metrics import (
    ACCOUNT_ALIASES,
    _extract_accounts_from_rows,
    compute_metrics_row,
)

BASE = "https://navercomp.wisereport.co.kr"
# rpt: 0=손익, 1=재무상태, 2=현금흐름
RPT_IS, RPT_BS, RPT_CF = 0, 1, 2
EOK = 100_000_000  # 네이버 표기 단위: 억원 → 원

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/v2/company/c1010001.aspx",
    "Accept": "application/json,text/javascript,*/*;q=0.01",
}

_ENCPARAM_RE = re.compile(r"encparam\s*[:=]\s*['\"]([^'\"]+)", re.I)
_YEAR_RE = re.compile(r"(\d{4})\s*/\s*\d{1,2}")


class NaverFinanceClient:
    def __init__(self, sleep: float = 0.05, timeout: float = 25.0) -> None:
        self.sleep = sleep
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self._enc_cache: dict[str, str] = {}

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        last: Exception | None = None
        for attempt in range(3):
            try:
                if self.sleep and attempt == 0:
                    time.sleep(self.sleep)
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                if resp.status_code in (429, 503):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"Naver request failed: {url} ({last})")

    def encparam(self, stock_code: str) -> str:
        code = str(stock_code).zfill(6)
        if code in self._enc_cache:
            return self._enc_cache[code]
        url = f"{BASE}/v2/company/c1010001.aspx?cmp_cd={code}"
        html = self._get(url).text
        m = _ENCPARAM_RE.search(html)
        if not m:
            raise RuntimeError(f"encparam missing for {code}")
        self._enc_cache[code] = m.group(1)
        return self._enc_cache[code]

    def fetch_statement(self, stock_code: str, rpt: int, enc: str | None = None) -> dict[str, Any]:
        code = str(stock_code).zfill(6)
        enc = enc or self.encparam(code)
        url = (
            f"{BASE}/v2/company/cF3002.aspx?"
            f"cmp_cd={code}&frq=0&rpt={rpt}&finGubun=MAIN&frqTyp=0&cn=&encparam={enc}"
        )
        data = self._get(url).json()
        if not isinstance(data, dict) or "DATA" not in data:
            raise RuntimeError(f"bad statement payload {code} rpt={rpt}")
        return data

    def fetch_all_statements(self, stock_code: str) -> dict[int, dict[str, Any]]:
        enc = self.encparam(stock_code)
        return {
            RPT_IS: self.fetch_statement(stock_code, RPT_IS, enc),
            RPT_BS: self.fetch_statement(stock_code, RPT_BS, enc),
            RPT_CF: self.fetch_statement(stock_code, RPT_CF, enc),
        }


def _year_column(yymm: list[str], year: str) -> str | None:
    """YYMM label list → DATA1..DATAn for the calendar year (skip consensus)."""
    for i, label in enumerate(yymm or []):
        text = str(label)
        if "(E)" in text or "전년대비" in text:
            continue
        m = _YEAR_RE.search(text)
        if m and m.group(1) == str(year):
            return f"DATA{i + 1}"
    return None


def _rows_for_year(payload: dict[str, Any], year: str) -> list[dict[str, Any]]:
    col = _year_column(payload.get("YYMM") or [], year)
    if not col:
        return []
    out: list[dict[str, Any]] = []
    for item in payload.get("DATA") or []:
        nm = str(item.get("ACC_NM") or "").strip()
        if not nm:
            continue
        raw = item.get(col)
        if raw is None or raw == "":
            continue
        try:
            amount = float(raw) * EOK
        except (TypeError, ValueError):
            continue
        out.append({"account_nm": nm, "amount": amount})
    return out


def accounts_for_year(statements: dict[int, dict[str, Any]], year: str) -> dict[str, float | None]:
    rows: list[dict[str, Any]] = []
    for rpt in (RPT_IS, RPT_BS, RPT_CF):
        rows.extend(_rows_for_year(statements[rpt], year))
    if not rows:
        return {k: None for k in ACCOUNT_ALIASES}
    return _extract_accounts_from_rows(pd.DataFrame(rows))


def _one_stock(
    stock_code: str,
    corp_name: str,
    market: str,
    year: str,
    prev_year: str,
    sleep: float,
) -> dict[str, Any] | None:
    client = NaverFinanceClient(sleep=sleep)
    stmts = client.fetch_all_statements(stock_code)
    cur = accounts_for_year(stmts, year)
    prev = accounts_for_year(stmts, prev_year)
    if all(v is None for v in cur.values()):
        return None
    metrics = compute_metrics_row(stock_code, corp_name, cur, prev)
    if market:
        metrics["market"] = market
    metrics["data_source"] = "naver"
    metrics["fiscal_year"] = year
    return metrics


def build_metrics_dataframe(
    corps: pd.DataFrame,
    year: str,
    prev_year: str,
    *,
    sleep: float = 0.05,
    progress: Callable[[int, int, str], None] | None = None,
    limit: int = 0,
    workers: int = 6,
) -> pd.DataFrame:
    """Fetch Naver annuals for listed corps and compute screener metrics."""
    work = corps.copy()
    if limit and limit > 0:
        work = work.head(limit)

    total = len(work)
    rows: list[dict[str, Any]] = []
    done = 0

    def submit_row(r: Any) -> tuple[str, str, dict[str, Any] | None, str | None]:
        code = str(getattr(r, "stock_code")).zfill(6)
        name = str(getattr(r, "corp_name", "") or "")
        market = str(getattr(r, "market", "") or "")
        try:
            m = _one_stock(code, name, market, year, prev_year, sleep)
            return code, name, m, None
        except Exception as exc:  # noqa: BLE001
            return code, name, None, exc.__class__.__name__

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = [pool.submit(submit_row, r) for r in work.itertuples(index=False)]
        for fut in as_completed(futs):
            code, name, metrics, err = fut.result()
            done += 1
            if metrics is not None:
                rows.append(metrics)
            label = name or code
            if err:
                label = f"{label} ERR:{err}"
            if progress and (done == 1 or done % 20 == 0 or done == total):
                progress(done, total, label)

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values("stock_code").reset_index(drop=True)
