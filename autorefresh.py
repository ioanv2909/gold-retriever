"""Reincarcare automata: cand firul din fundal scrie date noi (T212, preturi XTB, dividende),
pagina deschisa (principala sau detaliul unei pozitii) se reincarca singura. Un fragment verifica
la POLL_SECONDS secunde; fisierele se citesc doar cand li s-a schimbat mtime-ul.
Setarea e per utilizator, pornita implicit."""
import os

import streamlit as st

from core import DIVIDENDS_CACHE_FILE, PORTFOLIO_CACHE_FILE, XTB_PRICES_FILE, load_json_file, save_json_file
from userctx import UPath

SETTINGS_FILE = UPath("autorefresh.json")
POLL_SECONDS = 30
WATCHED = (PORTFOLIO_CACHE_FILE, XTB_PRICES_FILE, DIVIDENDS_CACHE_FILE)
_SIG = "_autorefresh_sig"
_MTIMES = "_autorefresh_mtimes"
KEEP_SCROLL = "_autorefresh_keep_scroll"


def enabled():
    return bool(load_json_file(SETTINGS_FILE, {}).get("enabled", True))


def save_enabled(on):
    save_json_file(SETTINGS_FILE, {"enabled": bool(on)})


def signature(cache=None, files=WATCHED):
    """fetched_at pentru fiecare fisier urmarit; `cache` (mtime, fetched_at) evita parsarea fisierelor neschimbate."""
    cache = {} if cache is None else cache
    sig = []
    for f in files:
        path = os.fspath(f)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        hit = cache.get(path)
        if not hit or hit[0] != mtime:
            data = load_json_file(path, None) if mtime is not None else None
            hit = (mtime, (data or {}).get("fetched_at") if isinstance(data, dict) else None)
            cache[path] = hit
        sig.append(hit[1])
    return tuple(sig)


def _drop_detail_row():
    # randul se reconstruieste din ?detail= de vederea principala, fara salt in capul paginii
    for k in ("selected_ticker", "selected_row", "_url_ticker"):
        st.session_state.pop(k, None)
    # altfel selectia ramasa in tabel ar alege iar randul vechi din cache
    st.session_state["table_nonce"] = st.session_state.get("table_nonce", 0) + 1
    st.session_state[KEEP_SCROLL] = True


@st.fragment(run_every=POLL_SECONDS)
def _poll(detail):
    if signature(st.session_state.setdefault(_MTIMES, {})) == st.session_state.get(_SIG):
        return
    if detail:
        _drop_detail_row()
    from auth import auto_rerun
    auto_rerun()


def watch(detail=False):
    """Se apeleaza la fiecare randare completa, dupa ce pagina si-a citit datele."""
    st.session_state.pop(KEEP_SCROLL, None)  # neconsumat daca randul n-a mai putut fi refacut
    if not enabled():
        return
    st.session_state[_SIG] = signature(st.session_state.setdefault(_MTIMES, {}))
    _poll(detail)


def render_settings_toggle():
    from i18n import t
    on = st.toggle(t("ar.toggle"), value=enabled(), key="autorefresh_enabled", help=t("ar.help"))
    if on != enabled():
        save_enabled(on)
        st.toast(t("priv.saved"))
