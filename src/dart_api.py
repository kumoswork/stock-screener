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
DART_TIMEOUT = (10, 30)
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
            modify_date TEXT,
            market TEXT
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
    # migrate older DBs missing market column
    cols = {row[1] for row in conn.execute("PRAGMA table_info(corp_codes)").fetchall()}
    if "market" not in cols:
        conn.execute("ALTER TABLE corp_codes ADD COLUMN market TEXT")
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
        conn = get_db()
        init_db(conn)
        row = conn.execute(
            "SELECT corp_code FROM corp_codes WHERE stock_code = ? AND corp_code != '' AND corp_code NOT LIKE 'S%'",
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
            "INSERT INTO corp_codes (corp_code, corp_name, stock_code, modify_date, market) VALUES (?, ?, ?, ?, ?)",
            (corp_code, corp_name or stock_code, stock_code, "", None),
        )
        conn.commit()
        conn.close()
        return corp_code

    def _load_bundled_corp_codes(self) -> pd.DataFrame | None:
        if not BUNDLED_CORP_CSV.exists():
            return None
        df = pd.read_csv(BUNDLED_CORP_CSV, dtype=str)
        if "market" not in df.columns:
            df["market"] = ""
        return df

    def _save_corp_codes_df(self, df: pd.DataFrame) -> int:
        listed = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
        if "market" not in listed.columns:
            listed["market"] = ""
        if "modify_date" not in listed.columns:
            listed["modify_date"] = ""
        conn = get_db()
        init_db(conn)
        conn.execute("DELETE FROM corp_codes")
        conn.executemany(
            """
            INSERT INTO corp_codes (corp_code, corp_name, stock_code, modify_date, market)
            VALUES (?, ?, ?, ?, ?)
            """,
            listed[["corp_code", "corp_name", "stock_code", "modify_date", "market"]]
            .fillna("")
            .values.tolist(),
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
                    "market": "",
                }
            )
        return pd.DataFrame(rows)

    def sync_corp_codes(self, force_dart: bool = False) -> tuple[int, str]:
        """
        회사목록 동기화.
        Streamlit Cloud(해외)에서는 DART/KRX가 막히므로
        저장소에 포함된 CSV를 기본으로 사용한다.
        """
        bundled = self._load_bundled_corp_codes()
        existing = count_listed_corps()

        # market 정보가 없거나 비어 있으면 번들로 교체 (상장폐지 섞인 구캐시 방지)
        needs_refresh = False
        if existing > 0:
            conn = get_db()
            init_db(conn)
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM corp_codes WHERE market IS NOT NULL AND market != ''"
            ).fetchone()
            conn.close()
            if not row or int(row["cnt"]) < 100:
                needs_refresh = True

        if existing >= 500 and not force_dart and not needs_refresh:
            return existing, "cached"

        if bundled is not None and not bundled.empty and not force_dart:
            count = self._save_corp_codes_df(bundled)
            return count, "bundled"

        if force_dart:
            try:
                df = self.download_corp_codes()
                listed = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
                count = self._save_corp_codes_df(listed)
                return count, "dart"
            except (ConnectTimeout, RequestException) as exc:
                if bundled is not None and not bundled.empty:
                    count = self._save_corp_codes_df(bundled)
                    return count, f"bundled (DART 실패: {exc.__class__.__name__})"
                raise RuntimeError(
                    "DART 연결 실패. Streamlit Cloud에서는 'DART 전체 갱신'을 끄고 "
                    "번들 목록을 사용하세요."
                ) from exc

        if bundled is not None and not bundled.empty:
            count = self._save_corp_codes_df(bundled)
            return count, "bundled"

        raise RuntimeError(
            "회사목록 파일이 없습니다. 저장소에 data/corp_codes_listed.csv 가 필요합니다."
        )

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
        for i, (_, row) in enumerate(corps.iterrows()):
            if progress_callback:
                progress_callback(i + 1, total, row["corp_name"])

            corp_code = row["corp_code"]
            if not corp_code or str(corp_code).startswith("S"):
                corp_code = self.lookup_corp_code(row["stock_code"])
            if not corp_code:
                continue

            try:
                items = self.fetch_financials(corp_code, bsns_year)
            except (RuntimeError, ConnectTimeout, RequestException) as exc:
                # 데이터 없음은 조용히 스킵
                msg = str(exc)
                if "없습니다" not in msg and "no data" not in msg.lower():
                    pass
                time.sleep(0.05)
                continue

            if not items:
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
            time.sleep(0.05)

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
    """DB에서 상장사 목록 로드. 네트워크 호출 없음 (클라우드 안정)."""
    conn = get_db()
    init_db(conn)
    df = pd.read_sql(
        """
        SELECT corp_code, corp_name, stock_code, market
        FROM corp_codes
        WHERE stock_code IS NOT NULL AND stock_code != ''
        """,
        conn,
    )
    conn.close()
    if df.empty:
        return df

    if market in ("KOSPI", "KOSDAQ") and "market" in df.columns:
        df = df[df["market"] == market].copy()
    elif market == "ALL" and "market" in df.columns:
        df = df[df["market"].isin(["KOSPI", "KOSDAQ"])].copy()

    # 대형주부터 채우도록 종목코드 정렬 (안정적인 샘플링)
    return df.sort_values(["market", "stock_code"]).reset_index(drop=True)
