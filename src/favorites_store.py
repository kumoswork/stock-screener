"""Persist favorites across devices (shared app list)."""

from __future__ import annotations

import base64
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

SAVED_PATH = Path(__file__).resolve().parent.parent / "data" / "favorites.json"


def _code(raw: Any) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit()).zfill(6)


def _normalize_item(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        code = _code(raw)
        if not code or code == "000000":
            return None
        return {"code": code, "added_at": None, "price_at_add": None}
    if not isinstance(raw, dict):
        return None
    code = _code(raw.get("code") or raw.get("stock_code"))
    if not code or code == "000000":
        return None
    added = raw.get("added_at")
    if added is not None:
        added = str(added)[:10] or None
    price = raw.get("price_at_add")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    if price is not None and price <= 0:
        price = None
    return {"code": code, "added_at": added, "price_at_add": price}


def _normalize_items(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items or []:
        item = _normalize_item(raw)
        if not item or item["code"] in seen:
            continue
        seen.add(item["code"])
        out.append(item)
    return out


def _parse_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return _normalize_items(data)
    if isinstance(data, dict):
        if "items" in data:
            return _normalize_items(data.get("items"))
        if "codes" in data:
            return _normalize_items(data.get("codes"))
    return []


def _load_local_items() -> list[dict[str, Any]]:
    if not SAVED_PATH.exists():
        return []
    try:
        return _parse_payload(json.loads(SAVED_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return []


def _load_from_github_raw() -> list[dict[str, Any]] | None:
    try:
        import requests

        repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
        url = f"https://raw.githubusercontent.com/{repo}/main/data/favorites.json"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        items = _parse_payload(resp.json())
        return items
    except Exception:
        return None


def load_favorite_items() -> list[dict[str, Any]]:
    """서버 로컬 파일 우선. GitHub는 로컬이 비었을 때만(백업)."""
    local = _load_local_items()
    if local:
        return local

    remote = _load_from_github_raw()
    if remote:
        try:
            save_favorites_local(remote)
        except OSError:
            pass
        return remote
    return []


def load_favorites() -> list[str]:
    return [x["code"] for x in load_favorite_items()]


def load_favorites_map() -> dict[str, dict[str, Any]]:
    return {x["code"]: x for x in load_favorite_items()}


def save_favorites_local(items: list[dict[str, Any]]) -> None:
    cleaned = _normalize_items(items)
    SAVED_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": cleaned}
    SAVED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_favorites_github(items: list[dict[str, Any]]) -> str | None:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
    if not token:
        return None

    import requests

    path = "data/favorites.json"
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha = None
    get_resp = requests.get(api, headers=headers, timeout=20)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    cleaned = _normalize_items(items)
    payload_body = {"items": cleaned}
    content = base64.b64encode(
        json.dumps(payload_body, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    payload = {"message": "Update screener favorites", "content": content, "branch": "main"}
    if sha:
        payload["sha"] = sha
    put_resp = requests.put(api, headers=headers, json=payload, timeout=30)
    if put_resp.status_code in (200, 201):
        return "github"
    return f"github_error:{put_resp.status_code}"


def merge_favorite_items(
  local: list[dict[str, Any]], remote: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for raw in remote + local:
        item = _normalize_item(raw)
        if not item:
            continue
        code = item["code"]
        prev = by_code.get(code)
        if not prev:
            by_code[code] = item
            continue
        # 더 이른 등록일·등록가 보존
        merged = dict(prev)
        if item.get("added_at") and (not merged.get("added_at") or item["added_at"] < merged["added_at"]):
            merged["added_at"] = item["added_at"]
        if item.get("price_at_add") is not None and merged.get("price_at_add") is None:
            merged["price_at_add"] = item["price_at_add"]
        by_code[code] = merged
    return list(by_code.values())


def persist_favorites(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    cleaned = _normalize_items(items)
    save_favorites_local(cleaned)
    remote = save_favorites_github(cleaned)
    if remote == "github":
        return cleaned, "local+github"
    if remote and str(remote).startswith("github_error"):
        return cleaned, f"local ({remote})"
    return cleaned, "local"


def item_for_add(code: str, price_at_add: float | None = None) -> dict[str, Any]:
    return {
        "code": _code(code),
        "added_at": date.today().isoformat(),
        "price_at_add": float(price_at_add) if price_at_add is not None and price_at_add > 0 else None,
    }
