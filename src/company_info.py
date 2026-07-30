"""Company overview text (Naver Finance 기업개요)."""

from __future__ import annotations

import re
import time
from html import unescape
from typing import Any

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}
_SUMMARY_BLOCK_RE = re.compile(r'id="summary_info"[^>]*>(.*?)</div>', re.S | re.I)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

_cache: dict[str, tuple[float, str | None]] = {}
_CACHE_TTL_SEC = 60 * 60 * 24
_CACHE_MAX = 800


def _clean_html_text(raw: str) -> str:
    text = _TAG_RE.sub("", raw)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_company_summary(stock_code: str) -> str | None:
    code = "".join(ch for ch in str(stock_code or "") if ch.isdigit()).zfill(6)
    if not code or code == "000000":
        return None

    now = time.time()
    cached = _cache.get(code)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return cached[1]

    summary: str | None = None
    try:
        resp = requests.get(
            f"https://finance.naver.com/item/main.naver?code={code}",
            headers=_HEADERS,
            timeout=(2, 8),
        )
        resp.raise_for_status()
        # 네이버 금융은 UTF-8(charset=UTF-8). euc-kr로 읽으면 한글이 깨짐.
        html = resp.content.decode("utf-8")
        block = _SUMMARY_BLOCK_RE.search(html)
        if block:
            parts: list[str] = []
            for raw in _P_RE.findall(block.group(1)):
                text = _clean_html_text(raw)
                if not text or "출처" in text:
                    continue
                parts.append(text)
            if parts:
                summary = "\n".join(parts[:3])
                if len(summary) > 520:
                    summary = summary[:517].rstrip() + "…"
    except Exception:
        summary = None

    if len(_cache) >= _CACHE_MAX:
        oldest = min(_cache.items(), key=lambda x: x[1][0])[0]
        _cache.pop(oldest, None)
    _cache[code] = (now, summary)
    return summary
