"""Taburi legate de URL (?tab=<id>): refresh-ul si linkurile redeschid acelasi tab, in orice limba."""
import streamlit as st

PARAM = "tab"


def url_tabs(entries, key):
    """entries: [(id, eticheta)]. Intoarce {id: container}; container.open e False pentru taburile inchise.
    Id-ul apare in URL; eticheta se poate schimba (limba) fara sa strice linkul."""
    label_by_id = dict(entries)
    id_by_label = {label: i for i, label in entries}
    first = entries[0][0]
    wanted = st.query_params.get(PARAM)
    if wanted not in label_by_id:
        wanted = first
        st.query_params.pop(PARAM, None)
    # URL-ul castiga (link, refresh, alta limba); dupa un click, callback-ul le aliniaza inainte de rulare
    if st.session_state.get(key) != label_by_id[wanted]:
        st.session_state.pop(key, None)

    def _sync():
        chosen = id_by_label.get(st.session_state.get(key), first)
        if chosen == first:
            st.query_params.pop(PARAM, None)  # primul tab nu are nevoie de parametru
        else:
            st.query_params[PARAM] = chosen

    tabs = st.tabs([label for _, label in entries], default=label_by_id[wanted], key=key, on_change=_sync)
    return {i: tab for (i, _), tab in zip(entries, tabs)}


def reset(key):
    """La intrarea pe o alta pagina: primul tab si fara parametru in URL."""
    st.query_params.pop(PARAM, None)
    st.session_state.pop(key, None)
