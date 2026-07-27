"""Persist favorites across devices (shared app list)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

SAVED_PATH = Path(__file__).resolve().parent.parent / "data" / "favorites.json"


def _normalize(codes: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = "".join(ch for ch in str(raw or "") if ch.isdigit()).zfill(6)
        if not code or code == "000000" or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _load_local() -> list[str]:
    if not SAVED_PATH.exists():
        return []
    try:
        data = json.loads(SAVED_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _normalize(data.get("codes"))
        if isinstance(data, list):
            return _normalize(data)
    except (json.JSONDecodeError, OSError):
        pass
    return []


def load_favorites() -> list[str]:
    """서버 로컬 파일 우선. GitHub는 로컬이 비었을 때만(백업)."""
    local = _load_local()
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


def _load_from_github_raw() -> list[str] | None:
    try:
        import requests

        repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
        url = f"https://raw.githubusercontent.com/{repo}/main/data/favorites.json"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, dict):
            return _normalize(data.get("codes"))
        if isinstance(data, list):
            return _normalize(data)
        return None
    except Exception:
        return None


def save_favorites_local(codes: list[str]) -> None:
    SAVED_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"codes": _normalize(codes)}
    SAVED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_favorites_github(codes: list[str]) -> str | None:
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

    payload_body = {"codes": _normalize(codes)}
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


def persist_favorites(codes: list[str]) -> tuple[list[str], str]:
    cleaned = _normalize(codes)
    save_favorites_local(cleaned)
    remote = save_favorites_github(cleaned)
    if remote == "github":
        return cleaned, "local+github"
    if remote and str(remote).startswith("github_error"):
        return cleaned, f"local ({remote})"
    return cleaned, "local"
