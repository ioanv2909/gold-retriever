"""Limba aleasa, pastrata in ui_prefs.json (per utilizator dupa login, altfel fisierul comun)."""
import json as _json
import os as _os

import streamlit as st

from i18n import LANGS

_PREF_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "ui_prefs.json")


def _pref_file():
    try:
        from userctx import current_user, user_dir
        if current_user():
            return _os.path.join(user_dir(), "ui_prefs.json")
    except Exception:
        pass
    return _PREF_PATH


def _read_prefs():
    for _pth in (_pref_file(), _PREF_PATH):
        try:
            with open(_pth, encoding="utf-8") as _f:
                _d = _json.load(_f)
            if _d.get("lang") or _pth == _PREF_PATH:
                return _d
        except Exception:
            pass
    return {}


def restore_lang():
    """Păstrează limba aleasă când selectorul nu e randat (ex. pe pagina de detaliu):
    Streamlit șterge starea unui widget nerandat, deci o reatribuim la fiecare rulare."""
    if not st.session_state.get("lang") and not st.session_state.get("_lang"):
        _saved_lang = _read_prefs().get("lang")
        if _saved_lang in LANGS:
            st.session_state["lang"] = _saved_lang

    if st.session_state.get("lang"):
        st.session_state["_lang"] = st.session_state["lang"]
    elif st.session_state.get("_lang"):
        st.session_state["lang"] = st.session_state["_lang"]
    if not st.session_state.get("lang"):
        st.session_state["lang"] = "RO"

    _cur_lang = st.session_state.get("lang")
    if _cur_lang in LANGS:
        _p = _read_prefs()
        if _p.get("lang") != _cur_lang:
            _p["lang"] = _cur_lang
            try:
                _pf = _pref_file()
                _os.makedirs(_os.path.dirname(_pf), exist_ok=True)
                with open(_pf, "w", encoding="utf-8") as _f:
                    _json.dump(_p, _f)
            except Exception:
                pass


def apply_user_lang(me):
    """La schimbarea utilizatorului se incarca limba lui salvata."""
    if st.session_state.get("_lang_user") != me:
        st.session_state["_lang_user"] = me
        _pl = _read_prefs().get("lang")
        if _pl in LANGS:
            st.session_state["lang"] = _pl
            st.session_state["_lang"] = _pl
