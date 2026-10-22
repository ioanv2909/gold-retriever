from streamlit.testing.v1 import AppTest

import privacy


def _page():
    import streamlit as st
    import privacy

    privacy.toggle_button("eye")
    st.markdown("VAL:" + privacy.mask("1,234.00 EUR"))


def _val(at):
    return [m.value for m in at.markdown if m.value.startswith("VAL:")][0]


def test_setting_round_trip():
    assert privacy.load_setting() is False
    privacy.save_setting(True)
    assert privacy.load_setting() is True


def test_amounts_visible_by_default_and_toggle_hides_them():
    at = AppTest.from_function(_page).run()
    assert _val(at) == "VAL:1,234.00 EUR"
    at.button[0].click().run()
    assert _val(at) == "VAL:" + privacy.MASK


def test_session_starts_hidden_when_set_and_button_reveals():
    privacy.save_setting(True)
    at = AppTest.from_function(_page).run()
    assert _val(at) == "VAL:" + privacy.MASK
    at.button[0].click().run()
    assert _val(at) == "VAL:1,234.00 EUR"


def test_mask_outside_a_session_shows_the_amount():
    assert privacy.mask("5") == "5"
