from streamlit.testing.v1 import AppTest

from mobile import is_mobile_ua


def _page():
    import streamlit as st
    import mobile

    st.markdown("MODE:" + ("compact" if mobile.compact() else "full"))
    with mobile.desktop_only("x"):
        st.markdown("DESKTOP")


def _mode(at):
    return [m.value for m in at.markdown if m.value.startswith("MODE:")][0]


def test_user_agent_detection():
    assert is_mobile_ua("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148")
    assert is_mobile_ua("Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/126.0 Mobile Safari/537.36")
    assert not is_mobile_ua("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36")
    assert not is_mobile_ua(None)


def test_query_param_forces_mode_and_sticks_for_the_session():
    at = AppTest.from_function(_page)
    at.query_params["view"] = "compact"
    at.run()
    assert _mode(at) == "MODE:compact"
    # containerul desktop-only exista (codul ruleaza), dar e marcat pentru ascundere prin CSS
    assert any("DESKTOP" == m.value for m in at.markdown)
    at.query_params.pop("view")
    at.run()
    assert _mode(at) == "MODE:compact"
    at.query_params["view"] = "full"
    at.run()
    assert _mode(at) == "MODE:full"


def test_desktop_by_default():
    assert _mode(AppTest.from_function(_page).run()) == "MODE:full"
