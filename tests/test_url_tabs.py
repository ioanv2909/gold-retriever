from streamlit.testing.v1 import AppTest


def _page():
    import streamlit as st
    from url_tabs import url_tabs

    ro = st.session_state.get("lang", "RO") == "RO"
    tabs = url_tabs([("a", "Prima" if ro else "First"), ("b", "A doua" if ro else "Second"), ("c", "Trei")], "t_key")
    for i, tab in tabs.items():
        if tab.open is not False:
            with tab:
                st.markdown("BODY:" + i)


def _bodies(at):
    return [m.value for m in at.markdown if m.value.startswith("BODY:")]


def _run(tab=None, lang=None):
    at = AppTest.from_function(_page)
    if tab is not None:
        at.query_params["tab"] = tab
    if lang:
        at.session_state["lang"] = lang
    return at.run()


def test_url_opens_the_tab():
    assert _bodies(_run("b")) == ["BODY:b"]
    assert _bodies(_run("c")) == ["BODY:c"]


def test_default_and_invalid_tab_fall_back_to_first():
    assert _bodies(_run()) == ["BODY:a"]
    at = _run("nope")
    assert _bodies(at) == ["BODY:a"] and "tab" not in at.query_params


def test_language_change_keeps_the_tab():
    at = _run("b")
    at.session_state["lang"] = "EN"
    at.run()
    assert _bodies(at) == ["BODY:b"] and at.query_params["tab"] == "b"
