from streamlit.testing.v1 import AppTest

import privacy


def _page():
    import streamlit as st
    import privacy

    privacy.toggle_button("eye")
    st.markdown("VAL:" + privacy.mask("1,234.00 EUR"))


def _val(at):
    return [m.value for m in at.markdown if m.value.startswith("VAL:")][0]


def test_setting_round_trip_per_device():
    assert privacy.load_setting("phone") is False
    privacy.save_setting("phone", True)
    assert privacy.load_setting("phone") is True and privacy.load_setting("desktop") is False


def test_old_shared_setting_applies_to_both_devices():
    from core import save_json_file
    save_json_file(privacy.PRIVACY_FILE, {"hide_on_start": True})
    assert privacy.load_setting("phone") and privacy.load_setting("desktop")
    privacy.save_setting("desktop", False)
    assert privacy.load_setting("phone") and not privacy.load_setting("desktop")


def test_amounts_visible_by_default_and_toggle_hides_them():
    at = AppTest.from_function(_page).run()
    assert _val(at) == "VAL:1,234.00 EUR"
    at.button[0].click().run()
    assert _val(at) == "VAL:" + privacy.MASK


def test_session_starts_hidden_when_set_and_button_reveals():
    privacy.save_setting("desktop", True)
    at = AppTest.from_function(_page).run()
    assert _val(at) == "VAL:" + privacy.MASK
    at.button[0].click().run()
    assert _val(at) == "VAL:1,234.00 EUR"


def test_mask_outside_a_session_shows_the_amount():
    assert privacy.mask("5") == "5"


def test_phone_and_desktop_start_differently():
    privacy.save_setting("phone", True)
    assert _val(AppTest.from_function(_page).run()) == "VAL:1,234.00 EUR"
    at = AppTest.from_function(_page)
    at.query_params["view"] = "compact"
    assert _val(at.run()) == "VAL:" + privacy.MASK
