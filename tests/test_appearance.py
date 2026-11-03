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


def test_sticky_header_css_targets_the_keyed_container(monkeypatch):
    import appearance
    shown, js = [], []
    monkeypatch.setattr(appearance.st, "markdown", lambda body, **k: shown.append(body))
    monkeypatch.setattr(appearance, "_run_js", js.append)
    appearance.sticky_header("app_header")
    css = shown[0]
    assert ".st-key-app_header" in css and "position: sticky" in css and "backdrop-filter" in css
    assert "%(" not in css and "90%," in css  # sablonul a fost completat
    assert "--gr-bg" in js[0] and "stApp" in js[0]
