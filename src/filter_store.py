"""Persist filter settings across refresh / browsers (shared app defaults)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

SAVED_PATH = Path(__file__).resolve().parent.parent / "data" / "saved_filters.json"


def load_saved_filters() -> dict[str, Any]:
    remote = _load_from_github_raw()
    if remote:
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
    SAVED_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_filters_github(state: dict[str, Any]) -> str | None:
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

    content = base64.b64encode(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    payload = {"message": "Update saved screener filters", "content": content, "branch": "main"}
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
    if remote and str(remote).startswith("github_error"):
        return f"local ({remote})"
    return "local"


def collect_filter_state(market_label: str, filter_keys: list[str], abs_keys: list[str]) -> dict[str, Any]:
    import streamlit as st

    enabled = []
    ranges: dict[str, list] = {}
    for key in filter_keys:
        if st.session_state.get(f"f_{key}", False):
            enabled.append(key)
            lo = st.session_state.get(f"f_{key}_min")
            hi = st.session_state.get(f"f_{key}_max")
            ranges[key] = [
                float(lo) if lo is not None else None,
                float(hi) if hi is not None else None,
            ]

    abs_state = {}
    for key in abs_keys:
        abs_state[key] = {
            "on": bool(st.session_state.get(f"abs_{key}", False)),
            "unit": st.session_state.get(f"abs_{key}_unit", "억원"),
            "lo": float(st.session_state.get(f"abs_{key}_lo", 0.0) or 0.0),
            "hi": float(st.session_state.get(f"abs_{key}_hi", 0.0) or 0.0),
        }

    return {
        "market": market_label,
        "search": st.session_state.get("stock_search_select", "") or "",
        "enabled": enabled,
        "ranges": ranges,
        "abs": abs_state,
    }


def backup_filters_from_session(filter_keys: list[str], abs_keys: list[str]) -> dict[str, Any]:
    """위젯이 사라지기 전에 필터를 비위젯 키로 백업 (모드 전환 대비)."""
    import streamlit as st

    market = st.session_state.get("market_radio", "전체")
    # 필터 위젯 키가 하나도 없으면 기존 백업 유지
    has_filter_widgets = any(f"f_{k}" in st.session_state for k in filter_keys) or any(
        f"abs_{k}" in st.session_state for k in abs_keys
    )
    if not has_filter_widgets:
        return st.session_state.get("_filter_backup") or {}

    state = collect_filter_state(str(market), filter_keys, abs_keys)
    st.session_state["_filter_backup"] = state
    return state


def restore_filters_to_session(filter_keys: list[str], abs_keys: list[str]) -> None:
    """필터 위젯 렌더 직전에 백업(또는 저장본)을 세션에 되돌림."""
    import streamlit as st

    saved = st.session_state.get("_filter_backup")
    if not saved:
        return

    if "market" in saved:
        st.session_state["market_radio"] = saved["market"]

    enabled = set(saved.get("enabled") or [])
    ranges = saved.get("ranges") or {}
    for key in filter_keys:
        on = key in enabled
        st.session_state[f"f_{key}"] = on
        if on:
            st.session_state[f"_defaulted_{key}"] = True
            lo, hi = ranges.get(key, [None, None])
            if lo is not None:
                st.session_state[f"f_{key}_min"] = float(lo)
            if hi is not None:
                st.session_state[f"f_{key}_max"] = float(hi)
        else:
            st.session_state.pop(f"_defaulted_{key}", None)

    for key, conf in (saved.get("abs") or {}).items():
        if key not in abs_keys:
            continue
        st.session_state[f"abs_{key}"] = bool(conf.get("on"))
        st.session_state[f"abs_{key}_unit"] = conf.get("unit", "억원")
        st.session_state[f"abs_{key}_lo"] = float(conf.get("lo") or 0.0)
        st.session_state[f"abs_{key}_hi"] = float(conf.get("hi") or 0.0)


def seed_session_from_saved(saved: dict[str, Any]) -> None:
    import streamlit as st

    if st.session_state.get("_filters_seeded"):
        return

    if not saved:
        st.session_state["_filters_seeded"] = True
        return

    # 모드 전환용 백업에도 넣어 둠
    st.session_state["_filter_backup"] = saved

    if "market" in saved and "market_radio" not in st.session_state:
        st.session_state["market_radio"] = saved["market"]
    if "search" in saved and "stock_search_select" not in st.session_state:
        search = saved.get("search") or "종목을 선택하세요"
        if search in ("— 검색 안 함 —", ""):
            search = "종목을 선택하세요"
        st.session_state["stock_search_select"] = search

    for key in saved.get("enabled", []):
        st.session_state[f"f_{key}"] = True
        st.session_state[f"_defaulted_{key}"] = True
        lo, hi = saved.get("ranges", {}).get(key, [None, None])
        if lo is not None:
            st.session_state[f"f_{key}_min"] = float(lo)
        if hi is not None:
            st.session_state[f"f_{key}_max"] = float(hi)

    for key, conf in saved.get("abs", {}).items():
        st.session_state[f"abs_{key}"] = bool(conf.get("on"))
        st.session_state[f"abs_{key}_unit"] = conf.get("unit", "억원")
        st.session_state[f"abs_{key}_lo"] = float(conf.get("lo") or 0.0)
        st.session_state[f"abs_{key}_hi"] = float(conf.get("hi") or 0.0)

    st.session_state["_filters_seeded"] = True
