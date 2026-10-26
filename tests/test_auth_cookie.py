import auth


def test_cookie_is_written_by_page_script(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "_run_js", calls.append)
    auth._cookie_js("ana.123.abc", 3600)
    auth._cookie_js("", 0)
    assert calls == ["document.cookie = 'pt_auth=ana.123.abc; max-age=3600; path=/; SameSite=Lax';",
                     "document.cookie = 'pt_auth=; max-age=0; path=/; SameSite=Lax';"]


def test_no_deprecated_components_html():
    src = open(auth.__file__, encoding="utf-8").read()
    assert "components.v1" not in src and "components.html" not in src
