"""Per-user portfolio favorites (name + 4-digit PIN).

Portfolios are stored locally and mirrored to GitHub (GITHUB_TOKEN)
so Railway redeploys do not wipe them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE_PATH = DATA_DIR / "portfolios_store.json"
SESSIONS_PATH = DATA_DIR / "portfolio_sessions.json"
GITHUB_PATH = "data/portfolios_store.json"

SESSION_TTL_SEC = 60 * 60 * 24 * 30  # 30 days
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{2,20}$")
_PIN_RE = re.compile(r"^\d{4}$")


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


def normalize_portfolio_name(name: str) -> str:
    return (name or "").strip()


def _slug(name: str) -> str:
    return normalize_portfolio_name(name).casefold()


def validate_credentials(name: str, pin: str) -> str | None:
    n = normalize_portfolio_name(name)
    if not _NAME_RE.match(n):
        return "이름은 영문 2~20자 (영문/숫자/_/-)로 입력해 주세요."
    if not _PIN_RE.match(str(pin or "")):
        return "비밀번호는 숫자 4자리여야 합니다."
    return None


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _empty_store() -> dict[str, Any]:
    return {"portfolios": {}}


def _parse_store(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _empty_store()
    portfolios = data.get("portfolios")
    if not isinstance(portfolios, dict):
        # migrate old single-file layout if ever needed
        return _empty_store()
    cleaned: dict[str, Any] = {}
    for key, raw in portfolios.items():
        if not isinstance(raw, dict):
            continue
        name = normalize_portfolio_name(raw.get("name") or key)
        slug = _slug(name)
        cleaned[slug] = {
            "name": name,
            "salt": str(raw.get("salt") or ""),
            "pin_hash": str(raw.get("pin_hash") or ""),
            "items": _normalize_items(raw.get("items")),
            "updated_at": str(raw.get("updated_at") or "")[:10] or None,
        }
    return {"portfolios": cleaned}


def _load_store_local() -> dict[str, Any]:
    if not STORE_PATH.exists():
        return _empty_store()
    try:
        return _parse_store(_read_json(STORE_PATH))
    except (json.JSONDecodeError, OSError):
        return _empty_store()


def _load_store_github() -> dict[str, Any] | None:
    try:
        import requests

        repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
        url = f"https://raw.githubusercontent.com/{repo}/main/{GITHUB_PATH}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        return _parse_store(resp.json())
    except Exception:
        return None


def _save_store_github(store: dict[str, Any]) -> str | None:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
    if not token:
        return None

    import requests

    api = f"https://api.github.com/repos/{repo}/contents/{GITHUB_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha = None
    get_resp = requests.get(api, headers=headers, timeout=20)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    content = base64.b64encode(
        json.dumps(store, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    payload: dict[str, Any] = {
        "message": "Update screener portfolios",
        "content": content,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    put_resp = requests.put(api, headers=headers, json=payload, timeout=30)
    if put_resp.status_code in (200, 201):
        return "github"
    return f"github_error:{put_resp.status_code}"


def _load_store(*, allow_remote: bool = True) -> dict[str, Any]:
    local = _load_store_local()
    if local.get("portfolios"):
        return local
    if not allow_remote:
        return local
    remote = _load_store_github()
    if remote and remote.get("portfolios"):
        try:
            _write_json(STORE_PATH, remote)
        except OSError:
            pass
        return remote
    return local


def _persist_store(store: dict[str, Any]) -> str:
    cleaned = _parse_store(store)
    _write_json(STORE_PATH, cleaned)
    remote = _save_store_github(cleaned)
    if remote == "github":
        return "local+github"
    if remote and str(remote).startswith("github_error"):
        return f"local ({remote})"
    return "local"


def _load_sessions() -> dict[str, Any]:
    if not SESSIONS_PATH.exists():
        return {}
    try:
        data = _read_json(SESSIONS_PATH)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sessions(sessions: dict[str, Any]) -> None:
    _write_json(SESSIONS_PATH, sessions)


def _cleanup_sessions(sessions: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    return {
        k: v
        for k, v in sessions.items()
        if isinstance(v, dict) and float(v.get("exp") or 0) > now
    }


def _issue_token(name: str) -> str:
    token = secrets.token_urlsafe(24)
    sessions = _cleanup_sessions(_load_sessions())
    sessions[token] = {
        "name": normalize_portfolio_name(name),
        "exp": time.time() + SESSION_TTL_SEC,
    }
    _save_sessions(sessions)
    return token


def resolve_token(token: str | None) -> str | None:
    if not token:
        return None
    sessions = _cleanup_sessions(_load_sessions())
    entry = sessions.get(token)
    if not entry:
        _save_sessions(sessions)
        return None
    entry["exp"] = time.time() + SESSION_TTL_SEC
    sessions[token] = entry
    _save_sessions(sessions)
    return str(entry.get("name") or "") or None


def revoke_token(token: str | None) -> None:
    if not token:
        return
    sessions = _cleanup_sessions(_load_sessions())
    if token in sessions:
        sessions.pop(token, None)
        _save_sessions(sessions)


def _get_portfolio(store: dict[str, Any], name: str) -> dict[str, Any] | None:
    return store.get("portfolios", {}).get(_slug(name))


def create_portfolio(name: str, pin: str) -> tuple[dict[str, Any] | None, str | None]:
    err = validate_credentials(name, pin)
    if err:
        return None, err
    n = normalize_portfolio_name(name)
    store = _load_store()
    if _get_portfolio(store, n) is not None:
        return None, "이미 있는 이름입니다. 들어가기를 이용해 주세요."
    salt = secrets.token_hex(8)
    entry = {
        "name": n,
        "salt": salt,
        "pin_hash": _hash_pin(pin, salt),
        "items": [],
        "updated_at": date.today().isoformat(),
    }
    store.setdefault("portfolios", {})[_slug(n)] = entry
    _persist_store(store)
    token = _issue_token(n)
    return {
        "token": token,
        "name": n,
        "items": [],
        "codes": [],
        "count": 0,
    }, None


def login_portfolio(name: str, pin: str) -> tuple[dict[str, Any] | None, str | None]:
    err = validate_credentials(name, pin)
    if err:
        return None, err
    n = normalize_portfolio_name(name)
    store = _load_store()
    data = _get_portfolio(store, n)
    if data is None:
        return None, "없는 포트폴리오입니다. 새로 만들기를 이용해 주세요."
    salt = str(data.get("salt") or "")
    expect = str(data.get("pin_hash") or "")
    got = _hash_pin(pin, salt)
    if not salt or not hmac.compare_digest(expect, got):
        return None, "비밀번호가 올바르지 않습니다."
    items = _normalize_items(data.get("items"))
    token = _issue_token(str(data.get("name") or n))
    return {
        "token": token,
        "name": str(data.get("name") or n),
        "items": items,
        "codes": [x["code"] for x in items],
        "count": len(items),
    }, None


def load_favorite_items(name: str | None = None) -> list[dict[str, Any]]:
    if not name:
        return []
    data = _get_portfolio(_load_store(), name)
    if not data:
        return []
    return _normalize_items(data.get("items"))


def load_favorites(name: str | None = None) -> list[str]:
    return [x["code"] for x in load_favorite_items(name)]


def load_favorites_map(name: str | None = None) -> dict[str, dict[str, Any]]:
    return {x["code"]: x for x in load_favorite_items(name)}


def persist_favorites(
    items: list[dict[str, Any]], name: str | None = None
) -> tuple[list[dict[str, Any]], str]:
    if not name:
        return [], "unauthorized"
    store = _load_store()
    data = _get_portfolio(store, name)
    if data is None:
        return [], "missing"
    cleaned = _normalize_items(items)
    data["items"] = cleaned
    data["updated_at"] = date.today().isoformat()
    store.setdefault("portfolios", {})[_slug(name)] = data
    where = _persist_store(store)
    return cleaned, where


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
        merged = dict(prev)
        if item.get("added_at") and (not merged.get("added_at") or item["added_at"] < merged["added_at"]):
            merged["added_at"] = item["added_at"]
        if item.get("price_at_add") is not None and merged.get("price_at_add") is None:
            merged["price_at_add"] = item["price_at_add"]
        by_code[code] = merged
    return list(by_code.values())


def item_for_add(code: str, price_at_add: float | None = None) -> dict[str, Any]:
    return {
        "code": _code(code),
        "added_at": date.today().isoformat(),
        "price_at_add": float(price_at_add) if price_at_add is not None and price_at_add > 0 else None,
    }
