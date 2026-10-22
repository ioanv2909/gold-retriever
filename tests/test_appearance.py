from streamlit.testing.v1 import AppTest


def _page():
    import appearance
    appearance.render_settings_section()


def test_theme_buttons_write_the_streamlit_theme_key():
    at = AppTest.from_function(_page).run()
    assert [b.key for b in at.button] == ["theme_System", "theme_Light", "theme_Dark"]
    at.button(key="theme_Dark").click().run()
    js = " ".join(h.proto.body for h in at.get("html"))
    assert "stActiveTheme-" in js and "JSON.stringify('Dark')" in js and "reload" in js
