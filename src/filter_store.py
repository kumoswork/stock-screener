"""Persist filter settings across refresh / browsers (shared app defaults)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

SAVED_PATH = Path(__file__).resolve().parent.parent / "data" / "saved_filters.json"


def load_saved_filters() -> dict[str, Any]:
    """Load shared filters. Prefer GitHub(main) so all browsers see the latest save."""
    remote = _load_from_github_raw()
    if remote:
        # keep local copy in sync
        try:
            save_filters_local(remote)
        except OSError:
            pass
        return remote

    if SAVED_PATH.exists():
        try:
            data = json.loads(SAVED_PATH.read_text(encoding="utf-8"))
            if data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_from_github_raw() -> dict[str, Any]:
    try:
        import requests

        repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")
        try:
            import streamlit as st

            repo = st.secrets.get("GITHUB_REPO", repo)
        except Exception:
            pass
        url = f"https://raw.githubusercontent.com/{repo}/main/data/saved_filters.json"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) and data else {}
    except Exception:
        return {}


def save_filters_local(state: dict[str, Any]) -> None:
    SAVED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVED_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_filters_github(state: dict[str, Any]) -> str | None:
    """
    Optional durable save via GitHub Contents API.
    Secrets: GITHUB_TOKEN, optional GITHUB_REPO (default kumoswork/stock-screener)
    """
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    try:
        import streamlit as st

        if not token:
            token = st.secrets.get("GITHUB_TOKEN") or st.secrets.get("GH_TOKEN")
        repo = st.secrets.get("GITHUB_REPO", os.getenv("GITHUB_REPO", "kumoswork/stock-screener"))
    except Exception:
        repo = os.getenv("GITHUB_REPO", "kumoswork/stock-screener")

    if not token:
        return None

    import requests

    path = "data/saved_filters.json"
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

    content = base64.b64encode(
        json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": "Update saved screener filters",
        "content": content,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    put_resp = requests.put(api, headers=headers, json=payload, timeout=30)
    if put_resp.status_code in (200, 201):
        return "github"
    return f"github_error:{put_resp.status_code}"


def persist_filters(state: dict[str, Any]) -> str:
    save_filters_local(state)
    remote = save_filters_github(state)
    if remote == "github":
        return "local+github"
    if remote and remote.startswith("github_error"):
        return f"local ({remote})"
    return "local"


def collect_filter_state(
    market_label: str,
    filter_keys: list[str],
    abs_keys: list[str],
) -> dict[str, Any]:
    import streamlit as st

    enabled = []
    ranges: dict[str, list] = {}
    for key in filter_keys:
        if st.session_state.get(f"f_{key}", False):
            enabled.append(key)
            lo = st.session_state.get(f"f_{key}_lo", 0.0)
            hi = st.session_state.get(f"f_{key}_hi", 0.0)
            ranges[key] = [
                None if float(lo) == 0.0 else float(lo),
                None if float(hi) == 0.0 else float(hi),
            ]

    abs_state = {}
    for key in abs_keys:
        abs_state[key] = {
            "on": bool(st.session_state.get(f"abs_{key}", False)),
            "unit": st.session_state.get(f"abs_{key}_unit", "억원"),
            "lo": float(st.session_state.get(f"abs_{key}_lo", 0.0) or 0.0),
            "hi": float(st.session_state.get(f"abs_{key}_hi", 0.0) or 0.0),
        }

    sort = []
    for i in range(2):
        sort.append(
            {
                "col": st.session_state.get(f"sort_{i}", "") or "",
                "asc": st.session_state.get(f"sort_dir_{i}", "내림차순") == "오름차순",
                "dir_label": st.session_state.get(f"sort_dir_{i}", "내림차순"),
            }
        )

    return {
        "market": market_label,
        "enabled": enabled,
        "ranges": ranges,
        "abs": abs_state,
        "sort": sort,
    }


def seed_session_from_saved(saved: dict[str, Any]) -> None:
    """Call once before widgets are created."""
    import streamlit as st

    if st.session_state.get("_filters_seeded"):
        return

    if not saved:
        st.session_state["_filters_seeded"] = True
        return

    if "market" in saved and "market_radio" not in st.session_state:
        st.session_state["market_radio"] = saved["market"]

    for key in saved.get("enabled", []):
        st.session_state[f"f_{key}"] = True
        lo, hi = saved.get("ranges", {}).get(key, [None, None])
        st.session_state[f"f_{key}_lo"] = float(lo or 0.0)
        st.session_state[f"f_{key}_hi"] = float(hi or 0.0)

    # also restore ranges for enabled keys only is enough; disabled stay default

    for key, conf in saved.get("abs", {}).items():
        st.session_state[f"abs_{key}"] = bool(conf.get("on"))
        st.session_state[f"abs_{key}_unit"] = conf.get("unit", "억원")
        st.session_state[f"abs_{key}_lo"] = float(conf.get("lo") or 0.0)
        st.session_state[f"abs_{key}_hi"] = float(conf.get("hi") or 0.0)

    for i, item in enumerate(saved.get("sort", [])[:2]):
        st.session_state[f"sort_{i}"] = item.get("col", "") or ""
        st.session_state[f"sort_dir_{i}"] = item.get("dir_label") or (
            "오름차순" if item.get("asc") else "내림차순"
        )

    st.session_state["_filters_seeded"] = True
