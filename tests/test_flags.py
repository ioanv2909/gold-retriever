"""Steagurile pentru tari si monede."""
import flags


def test_country_and_currency_codes():
    assert flags.country_code("United States") == "us"
    assert flags.country_code("Netherlands") == "nl"
    assert flags.country_code("Germany") == "de"
    assert flags.country_code("South Korea") == "kr"
    assert flags.country_code("Atlantis") is None and flags.country_code("") is None
    assert flags.currency_code("eur") == "eu" and flags.currency_code("GBX") == "gb" and flags.currency_code("XYZ") is None


def test_flag_images_exist_and_reject_paths():
    uri = flags.flag_uri("ro")
    assert uri and uri.startswith("data:image/png;base64,")
    assert flags.flag_uri("eu") and flags.flag_uri("us")
    assert flags.flag_uri("../../etc/passwd") is None and flags.flag_uri(None) is None


def test_exposure_chart_uses_flags_for_countries_only():
    import exposure_ui
    items = [("Germany", 100.0, 60.0), ("ETF", 50.0, 40.0)]
    fig = exposure_ui._chart(items, "EUR", "country")
    assert len(fig.layout.images) == 1 and list(fig.layout.yaxis.ticktext) == ["", "ETF"]
    assert not exposure_ui._chart([("Tehnologie", 1.0, 100.0)], "EUR", "sector").layout.images
