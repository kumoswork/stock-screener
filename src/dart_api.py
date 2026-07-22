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
from requests.exceptions import ConnectTimeout, RequestException

BASE_URL = "https://opendart.fss.or.kr/api"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "screener.db"
BUNDLED_CORP_CSV = DATA_DIR / "corp_codes_listed.csv"

ANNUAL_REPORT = "11011"
DART_TIMEOUT = (10, 30)  # connect, read seconds
DART_RETRIES = 3


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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

        CREATE INDEX IF NOT EXISTS idx_corp_codes_stock ON corp_codes(stock_code);
        """
    )
    conn.commit()


def count_listed_corps() -> int:
    conn = get_db()
    init_db(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM corp_codes WHERE stock_code IS NOT NULL AND stock_code != ''"
    ).fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


class DartClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def _get_json(self, endpoint: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["crtfc_key"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(DART_RETRIES):
            try:
                resp = self.session.get(
                    f"{BASE_URL}/{endpoint}",
                    params=params,
                    timeout=DART_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "000":
                    raise RuntimeError(f"DART API error: {data.get('message', data)}")
                return data
            except (ConnectTimeout, RequestException) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise ConnectTimeout(f"DART 연결 실패 ({endpoint}): {last_error}")

    def lookup_corp_code(self, stock_code: str) -> str | None:
        """종목코드로 DART 고유번호 조회 (소량 요청, 해외 서버에서도 비교적 안정)."""
        conn = get_db()
        init_db(conn)
        row = conn.execute(
            "SELECT corp_code FROM corp_codes WHERE stock_code = ? AND corp_code != ''",
            (stock_code,),
        ).fetchone()
        if row and row["corp_code"]:
            conn.close()
            return row["corp_code"]

        try:
            data = self._get_json("company.json", {"stock_code": stock_code})
        except (ConnectTimeout, RequestException, RuntimeError):
            conn.close()
            return None

        corp_code = (data.get("corp_code") or "").strip()
        corp_name = (data.get("corp_name") or "").strip()
        if not corp_code:
            conn.close()
            return None

        conn.execute("DELETE FROM corp_codes WHERE stock_code = ?", (stock_code,))
        conn.execute(
            "INSERT INTO corp_codes (corp_code, corp_name, stock_code, modify_date) VALUES (?, ?, ?, ?)",
            (corp_code, corp_name or stock_code, stock_code, ""),
        )
        conn.commit()
        conn.close()
        return corp_code

    def sync_corp_codes_fast(self, market: str = "ALL") -> int:
        """KRX 상장목록 빠른 로드 (DART 대용량 XML 불필요)."""
        import FinanceDataReader as fdr

        markets = []
        if market in ("ALL", "KOSPI"):
            markets.append("KOSPI")
        if market in ("ALL", "KOSDAQ"):
            markets.append("KOSDAQ")

        rows: list[tuple[str, str, str, str]] = []
        seen: set[str] = set()
        for mk in markets:
            listing = fdr.StockListing(mk)
            for _, item in listing.iterrows():
                stock_code = str(item["Code"]).zfill(6)
                if stock_code in seen:
                    continue
                seen.add(stock_code)
                corp_name = str(item["Name"]).strip()
                placeholder_code = f"S{stock_code}"
                rows.append((placeholder_code, corp_name, stock_code, ""))

        conn = get_db()
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO corp_codes (corp_code, corp_name, stock_code, modify_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(corp_code) DO UPDATE SET
                corp_name = excluded.corp_name,
                stock_code = excluded.stock_code
            """,
            rows,
        )
        conn.commit()
        conn.close()
        return len(rows)

    def _load_bundled_corp_codes(self) -> pd.DataFrame | None:
        if not BUNDLED_CORP_CSV.exists():
            return None
        return pd.read_csv(BUNDLED_CORP_CSV, dtype=str)

    def _save_corp_codes_df(self, df: pd.DataFrame) -> int:
        listed = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
        conn = get_db()
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO corp_codes (corp_code, corp_name, stock_code, modify_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(corp_code) DO UPDATE SET
                corp_name = excluded.corp_name,
                stock_code = excluded.stock_code,
                modify_date = excluded.modify_date
            """,
            listed[["corp_code", "corp_name", "stock_code", "modify_date"]].fillna("").values.tolist(),
        )
        conn.commit()
        conn.close()
        return len(listed)

    def download_corp_codes(self) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(DART_RETRIES):
            try:
                resp = self.session.get(
                    f"{BASE_URL}/corpCode.xml",
                    params={"crtfc_key": self.api_key},
                    timeout=(10, 120),
                )
                resp.raise_for_status()
                break
            except (ConnectTimeout, RequestException) as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        else:
            raise ConnectTimeout(f"DART corpCode.xml 다운로드 실패: {last_error}")

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

    def sync_corp_codes(self, force_dart: bool = False) -> tuple[int, str]:
        """
        회사목록 동기화.
        - 기본: DB에 있으면 스킵, 없으면 빠른 KRX 로드
        - force_dart: DART XML 시도 → 실패 시 번들 CSV → 최후 KRX
        """
        existing = count_listed_corps()
        if existing >= 500 and not force_dart:
            return existing, "cached"

        if force_dart:
            try:
                df = self.download_corp_codes()
                listed = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
                count = self._save_corp_codes_df(listed)
                listed.to_csv(BUNDLED_CORP_CSV, index=False)
                return count, "dart"
            except (ConnectTimeout, RequestException) as exc:
                bundled = self._load_bundled_corp_codes()
                if bundled is not None and not bundled.empty:
                    count = self._save_corp_codes_df(bundled)
                    return count, f"bundled (DART 실패: {exc.__class__.__name__})"
                raise

        bundled = self._load_bundled_corp_codes()
        if bundled is not None and not bundled.empty:
            count = self._save_corp_codes_df(bundled)
            return count, "bundled"

        count = self.sync_corp_codes_fast("ALL")
        return count, "krx"

    def fetch_financials(self, corp_code: str, bsns_year: str) -> list[dict]:
        data = self._get_json(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": ANNUAL_REPORT,
                "fs_div": "CFS",
            },
        )
        items = data.get("list") or []
        if not items:
            data = self._get_json(
                "fnlttSinglAcntAll.json",
                {
                    "corp_code": corp_code,
                    "bsns_year": bsns_year,
                    "reprt_code": ANNUAL_REPORT,
                    "fs_div": "OFS",
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
        conn.close()
        corps = corps[corps["stock_code"].isin(stock_codes)]

        saved = 0
        total = len(corps)
        for i, row in corps.iterrows():
            if progress_callback:
                progress_callback(i + 1, total, row["corp_name"])

            corp_code = row["corp_code"]
            if not corp_code or str(corp_code).startswith("S"):
                corp_code = self.lookup_corp_code(row["stock_code"])
            if not corp_code:
                continue

            try:
                items = self.fetch_financials(corp_code, bsns_year)
            except (RuntimeError, ConnectTimeout, RequestException):
                time.sleep(0.15)
                continue

            conn = get_db()
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
                        corp_code,
                        bsns_year,
                        item.get("account_nm", "").strip(),
                        amount,
                    ),
                )
            conn.commit()
            conn.close()
            saved += 1
            time.sleep(0.12)

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
        "SELECT corp_code, corp_name, stock_code FROM corp_codes WHERE stock_code IS NOT NULL AND stock_code != ''",
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
