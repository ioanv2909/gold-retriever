import lang_prefs


def test_display_currency_pref_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(lang_prefs, "_pref_file", lambda: str(tmp_path / "u" / "ui_prefs.json"))
    assert lang_prefs.load_pref("display_ccy") is None
    lang_prefs.save_pref("lang", "RO")
    lang_prefs.save_pref("display_ccy", "EUR")
    assert lang_prefs.load_pref("display_ccy") == "EUR"
    assert lang_prefs.load_pref("lang") == "RO"  # celelalte preferinte raman


def test_main_page_defaults_to_eur():
    import main_view
    assert main_view.DEFAULT_DISPLAY_CCY == "EUR"
