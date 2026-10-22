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


def _chart_page():
    import plotly.graph_objects as go
    import streamlit as st
    import mobile

    fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
    mobile.plotly_chart(fig, key="c")
    st.session_state["_fig_layout"] = fig.layout


def test_chart_ignores_drag_on_phone_only():
    at = AppTest.from_function(_chart_page)
    at.query_params["view"] = "compact"
    lay = at.run().session_state["_fig_layout"]
    assert lay.dragmode is False and lay.xaxis.fixedrange and lay.yaxis.fixedrange
    lay = AppTest.from_function(_chart_page).run().session_state["_fig_layout"]
    assert lay.dragmode is None and not lay.xaxis.fixedrange


def _picker_page():
    import streamlit as st
    import mobile

    st.markdown("PICK:" + mobile.period_picker("P", ["1L", "3L", "1A"], key="p"))


def test_period_picker_uses_buttons_on_phone():
    at = AppTest.from_function(_picker_page)
    at.query_params["view"] = "compact"
    at.session_state["p"] = "3L"
    at.run()
    assert not at.radio and at.button_group[0].value == "3L"
    at.button_group[0].set_value("1A").run()
    assert "PICK:1A" in [m.value for m in at.markdown]
    at = AppTest.from_function(_picker_page).run()
    assert at.radio[0].value == "1L"


def _lang_page():
    import streamlit as st
    from i18n import lang_button

    lang_button("lb")
    st.markdown("LANG:" + st.session_state.get("lang", "RO"))


def test_language_button_shows_the_other_language_and_switches():
    at = AppTest.from_function(_lang_page).run()
    assert at.button[0].label == "🌐 EN"
    at.button[0].click().run()
    assert "LANG:EN" in [m.value for m in at.markdown] and at.button[0].label == "🌐 RO"
