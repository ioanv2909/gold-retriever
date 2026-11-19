"""Cautare rapida de pozitii: un camp deasupra taburilor (Ctrl+K il selecteaza) care deschide pagina pozitiei."""
import json

import streamlit as st

from appearance import _run_js
from i18n import t

KEY = "quick_search"


def options(df_display):
    """(ticker, eticheta) pentru pozitiile din tabel, ordonate dupa nume; eticheta = nume (ticker)."""
    seen, out = set(), []
    for tk, name in zip(df_display["ticker"], df_display["name"]):
        if tk in seen:
            continue
        seen.add(tk)
        out.append((tk, f"{name} ({tk})" if name and name != tk else str(tk)))
    return sorted(out, key=lambda x: x[1].casefold())


def render(df_display):
    opts = options(df_display)
    if not opts:
        return
    labels = dict(opts)
    label = t("qs.label")
    choice = st.selectbox(label, [tk for tk, _ in opts], index=None, format_func=lambda tk: labels.get(tk, tk),
                          placeholder=t("qs.placeholder"), label_visibility="collapsed", key=KEY)
    if choice:
        st.session_state.pop(KEY, None)
        st.query_params["detail"] = str(choice)
        st.rerun()
    # Ctrl+K / Cmd+K: focus pe camp (o singura data per pagina)
    _run_js("""
if (!window.parent.__grQuickSearch) {
  window.parent.__grQuickSearch = true;
  window.parent.document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      const box = window.parent.document.querySelector('input[aria-label=%s]');
      if (box) { e.preventDefault(); box.focus(); box.click(); }
    }
  });
}
""" % json.dumps(label))
