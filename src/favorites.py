"""Browser localStorage-backed favorites (no accounts)."""

from __future__ import annotations

import json
from typing import Iterable


STORAGE_KEY = "kumo_favorites"


def normalize_code(code: str) -> str:
    return str(code).zfill(6)


def get_favorites(st) -> set[str]:
    favs = st.session_state.get("favorites")
    if favs is None:
        favs = set()
        st.session_state["favorites"] = favs
    return favs


def bootstrap_favorites_from_query(st) -> None:
    """URL ?favs=005930,000660 으로 복원 (localStorage → 리다이렉트 후)."""
    if st.session_state.get("_fav_bootstrapped"):
        return
    raw = ""
    try:
        raw = st.query_params.get("favs", "") or ""
    except Exception:
        raw = ""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    codes = {normalize_code(c) for c in str(raw).split(",") if c.strip()}
    st.session_state["favorites"] = codes
    st.session_state["_fav_bootstrapped"] = True


def toggle_favorite(st, code: str) -> bool:
    """Toggle and return new state (True=favorited)."""
    code = normalize_code(code)
    favs = get_favorites(st)
    if code in favs:
        favs.discard(code)
        on = False
    else:
        favs.add(code)
        on = True
    st.session_state["_fav_dirty"] = True
    return on


def is_favorite(st, code: str) -> bool:
    return normalize_code(code) in get_favorites(st)


def favorites_sorted(st) -> list[str]:
    return sorted(get_favorites(st))


def localstorage_bootstrap_js() -> str:
    """첫 로드 시 localStorage → query param 동기화 (1회)."""
    return f"""
<script>
(function () {{
  const KEY = {json.dumps(STORAGE_KEY)};
  const FLAG = 'kumo_fav_boot_v1';
  try {{
    if (window.parent.sessionStorage.getItem(FLAG)) return;
    const favs = JSON.parse(window.parent.localStorage.getItem(KEY) || '[]');
    if (!Array.isArray(favs) || !favs.length) {{
      window.parent.sessionStorage.setItem(FLAG, '1');
      return;
    }}
    const url = new URL(window.parent.location.href);
    if (url.searchParams.get('favs')) {{
      window.parent.sessionStorage.setItem(FLAG, '1');
      return;
    }}
    window.parent.sessionStorage.setItem(FLAG, '1');
    url.searchParams.set('favs', favs.join(','));
    window.parent.location.replace(url.toString());
  }} catch (e) {{}}
}})();
</script>
"""


def localstorage_persist_js(codes: Iterable[str]) -> str:
    codes_list = [normalize_code(c) for c in codes]
    return f"""
<script>
(function () {{
  try {{
    window.parent.localStorage.setItem(
      {json.dumps(STORAGE_KEY)},
      {json.dumps(codes_list, ensure_ascii=False)}
    );
  }} catch (e) {{}}
}})();
</script>
"""
