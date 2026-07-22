"""DART Open API client for Korean listed company financial data."""

from __future__ import annotations

import io
import sqlite3
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://opendart.fss.or.kr/api"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "screener.db"

# 연간 사업보고서
ANNUAL_REPORT = "11011"


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS corp_codes (
            corp_code TEXT PRIMARY KEY,
            corp_name TEXT NOT NULL,
            stock_code TEXT,
            modify_date TEXT
        );

        CREATE TABLE IF NOT EXISTS financials (
            stock_code TEXT NOT NULL,
            corp_code TEXT NOT NULL,
            bsns_year TEXT NOT NULL,
            account_nm TEXT NOT NULL,
            amount REAL,
            PRIMARY KEY (stock_code, bsns_year, account_nm)
        );

        CREATE TABLE IF NOT EXISTS price_metrics (
            stock_code TEXT PRIMARY KEY,
            corp_name TEXT,
            current_price REAL,
            low_52w REAL,
            high_52w REAL,
            pct_from_low REAL,
            range_position REAL,
            bottom_dwell_ratio REAL,
            updated_at TEXT
        );
        """
    )
    conn.commit()


class DartClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["crtfc_key"] = self.api_key
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "000":
            raise RuntimeError(f"DART API error: {data.get('message', data)}")
        return data

    def download_corp_codes(self) -> pd.DataFrame:
        resp = self.session.get(
            f"{BASE_URL}/corpCode.xml",
            params={"crtfc_key": self.api_key},
            timeout=60,
        )
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_name = zf.namelist()[0]
            xml_bytes = zf.read(xml_name)

        root = ET.fromstring(xml_bytes)
        rows = []
        for item in root.findall("list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            rows.append(
                {
                    "corp_code": item.findtext("corp_code", "").strip(),
                    "corp_name": item.findtext("corp_name", "").strip(),
                    "stock_code": stock_code if stock_code else None,
                    "modify_date": item.findtext("modify_date", "").strip(),
                }
            )
        return pd.DataFrame(rows)

    def sync_corp_codes(self) -> int:
        df = self.download_corp_codes()
        listed = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
        conn = get_db()
        init_db(conn)
        conn.execute("DELETE FROM corp_codes")
        conn.executemany(
            "INSERT INTO corp_codes VALUES (?, ?, ?, ?)",
            listed[["corp_code", "corp_name", "stock_code", "modify_date"]].values.tolist(),
        )
        conn.commit()
        conn.close()
        return len(listed)

    def fetch_financials(self, corp_code: str, bsns_year: str) -> list[dict]:
        data = self._get(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": ANNUAL_REPORT,
                "fs_div": "CFS",  # 연결재무제표 우선
            },
        )
        items = data.get("list") or []
        if not items:
            data = self._get(
                "fnlttSinglAcntAll.json",
                {
                    "corp_code": corp_code,
                    "bsns_year": bsns_year,
                    "reprt_code": ANNUAL_REPORT,
                    "fs_div": "OFS",  # 연결 없으면 개별
                },
            )
            items = data.get("list") or []
        return items

    def sync_financials(
        self,
        stock_codes: list[str],
        bsns_year: str,
        progress_callback=None,
    ) -> int:
        conn = get_db()
        init_db(conn)
        corps = pd.read_sql(
            "SELECT corp_code, corp_name, stock_code FROM corp_codes WHERE stock_code IS NOT NULL",
            conn,
        )
        corps = corps[corps["stock_code"].isin(stock_codes)]

        saved = 0
        total = len(corps)
        for i, row in corps.iterrows():
            if progress_callback:
                progress_callback(i + 1, total, row["corp_name"])
            try:
                items = self.fetch_financials(row["corp_code"], bsns_year)
            except RuntimeError:
                time.sleep(0.15)
                continue

            conn.execute(
                "DELETE FROM financials WHERE stock_code = ? AND bsns_year = ?",
                (row["stock_code"], bsns_year),
            )
            for item in items:
                amount = _parse_amount(item.get("thstrm_amount"))
                if amount is None:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO financials (stock_code, corp_code, bsns_year, account_nm, amount)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["stock_code"],
                        row["corp_code"],
                        bsns_year,
                        item.get("account_nm", "").strip(),
                        amount,
                    ),
                )
            saved += 1
            conn.commit()
            time.sleep(0.12)  # API rate limit courtesy

        conn.close()
        return saved


def _parse_amount(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_listed_corps(market: str = "ALL") -> pd.DataFrame:
    conn = get_db()
    init_db(conn)
    df = pd.read_sql(
        "SELECT corp_code, corp_name, stock_code FROM corp_codes WHERE stock_code IS NOT NULL",
        conn,
    )
    conn.close()
    if df.empty:
        return df

    import FinanceDataReader as fdr

    codes: set[str] = set()
    try:
        if market in ("ALL", "KOSPI"):
            kospi = fdr.StockListing("KOSPI")
            codes.update(kospi["Code"].astype(str).str.zfill(6).tolist())
        if market in ("ALL", "KOSDAQ"):
            kosdaq = fdr.StockListing("KOSDAQ")
            codes.update(kosdaq["Code"].astype(str).str.zfill(6).tolist())
    except Exception:
        return df.reset_index(drop=True)

    df = df[df["stock_code"].isin(codes)].copy()
    return df.reset_index(drop=True)
