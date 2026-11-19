"""Logo-urile pozitiilor: cache local, insigna cu initiale, alegerea iconului, fara adrese private."""
import base64
import io
import json
import os
import socket

import pytest
from PIL import Image

import logos


def _png(size=(128, 128), color=(200, 30, 30, 255)):
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, "PNG")
    return out.getvalue()


def _ico():
    out = io.BytesIO()
    Image.new("RGBA", (48, 48), (0, 0, 255, 255)).save(out, "ICO", sizes=[(16, 16), (48, 48)])
    return out.getvalue()


def test_initials_and_badge_are_stable():
    assert logos.initials("Apple Inc.", "AAPL_US_EQ") == "AP"
    assert logos.initials("Vanguard FTSE All-World", "VWCEd_EQ") == "VF"
    assert logos.initials("", "MSFT_US_EQ") == "MS"
    a, b = logos.badge_uri("Apple", "AAPL"), logos.badge_uri("Apple", "AAPL")
    assert a == b and a.startswith("data:image/svg+xml;base64,")
    assert b"AP" in base64.b64decode(a.split(",", 1)[1])


def test_badge_escapes_name():
    svg = base64.b64decode(logos.badge_uri("<script>", "X").split(",", 1)[1])
    assert b"<script>" not in svg


def test_icon_candidates_prefer_large_touch_icons_and_skip_svg():
    page = """<html><head>
      <link rel="icon" href="/small.png" sizes="16x16">
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel="apple-touch-icon" href="/touch.png" sizes="180x180">
      <link rel="shortcut icon" href="https://cdn.example.com/fav.ico">
    </head></html>"""
    urls = logos.icon_candidates(page, "https://www.example.com/home")
    assert urls[0] == "https://www.example.com/touch.png"
    assert "https://www.example.com/logo.svg" not in urls
    assert urls[-1] == "https://www.example.com/favicon.ico"
    assert len(urls) == len(set(urls))


def test_to_png_handles_png_ico_and_garbage():
    for raw in (_png(), _png((300, 100)), _ico()):
        img = Image.open(io.BytesIO(logos.to_png(raw)))
        assert img.size == (64, 64) and img.format == "PNG"
    assert logos.to_png(b"not an image") is None
    assert logos.to_png(_png((8, 8))) is None


def test_logo_uri_uses_cache_and_falls_back_to_badge():
    assert logos.logo_uri("AAPL_US_EQ", "Apple").startswith("data:image/svg+xml")
    os.makedirs(logos.LOGO_DIR)
    with open(os.path.join(logos.LOGO_DIR, "a.png"), "wb") as f:
        f.write(_png())
    with open(logos.INDEX_FILE, "w") as f:
        json.dump({"AAPL_US_EQ": {"file": "a.png", "ts": 1}}, f)
    assert logos.logo_uri("AAPL_US_EQ", "Apple").startswith("data:image/png;base64,")
    assert logos.needs_fetch("AAPL_US_EQ")  # intrare fara versiune: se reface


def test_misses_are_retried_after_the_retry_period():
    logos._save_entry("X_EQ", {"file": None, "ts": 1000.0, "v": logos.VERSION})
    assert not logos.needs_fetch("X_EQ", now=1000.0 + 60)
    assert logos.needs_fetch("X_EQ", now=1000.0 + logos.RETRY_MISS_S + 1)
    assert logos.needs_fetch("NEW_EQ")


def test_fetch_logo_uses_company_site_only(monkeypatch):
    calls = []
    page = b'<link rel="apple-touch-icon" href="/touch.png">'

    def fake_get(url, limit):
        calls.append(url)
        if url == "https://www.example.com":
            return "https://www.example.com/", page, "text/html"
        if url == "https://www.example.com/touch.png":
            return url, _png(), "image/png"
        raise ValueError("404")

    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: "EX")
    monkeypatch.setattr(logos, "fmp_logo", lambda sym: None)
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: ("https://www.example.com", "Example Inc", False))
    monkeypatch.setattr(logos, "_get", fake_get)
    assert logos.fetch_logo("EX_US_EQ") is True
    assert all(u.startswith("https://www.example.com") for u in calls)
    assert logos.logo_uri("EX_US_EQ", "Example").startswith("data:image/png")


def test_fetch_logo_without_website_records_a_miss(monkeypatch):
    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: "ETF")
    monkeypatch.setattr(logos, "fmp_logo", lambda sym: None)
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: ("", "", True))
    monkeypatch.setattr(logos, "_get", lambda *a: pytest.fail("no download without a website"))
    assert logos.fetch_logo("ETF_EQ", "Unknown Fund") is False
    assert logos._load_index()["ETF_EQ"]["file"] is None


def test_private_addresses_are_refused(monkeypatch):
    def fake_getaddrinfo(host, port):
        ip = {"intern.example": "192.168.1.10", "local.example": "127.0.0.1"}.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert not logos._public_host("https://intern.example/")
    assert not logos._public_host("http://local.example/x.png")
    assert logos._public_host("https://www.example.com/")
    with pytest.raises(ValueError):
        logos._get("https://intern.example/", 1000)


def test_issuer_detection():
    assert logos.issuer_site("iShares", "") == "https://www.ishares.com"
    assert logos.issuer_site("", "Vanguard FTSE All-World UCITS ETF") == "https://www.vanguard.com"
    assert logos.issuer_site("Xtrackers MSCI World", "") == "https://etf.dws.com"
    assert logos.issuer_site("", "SPDR S&P 500") == "https://www.ssga.com"
    assert logos.issuer_site("", "Apple Inc") == ""


def test_funds_use_issuer_site_even_with_a_website():
    assert logos.choose_site("X", "", ("https://fund.example", "iShares Core MSCI World", True)) == "https://www.ishares.com"
    assert logos.choose_site("X", "Vanguard S&P 500", ("", "", False)) == "https://www.vanguard.com"
    assert logos.choose_site("X", "Apple", ("https://www.apple.com", "Apple Inc.", False)) == "https://www.apple.com"


def test_one_download_per_site(monkeypatch):
    downloads = []
    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: tk)
    monkeypatch.setattr(logos, "fmp_logo", lambda sym: None)
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: ("", "iShares", True))
    monkeypatch.setattr(logos, "_download_icon", lambda site: downloads.append(site) or _png())
    assert logos.fetch_logo("IWDA_EQ", "iShares Core MSCI World") is True
    assert logos.fetch_logo("EIMI_EQ", "iShares Core MSCI EM IMI") is True
    assert downloads == ["https://www.ishares.com"]
    assert logos.logo_uri("EIMI_EQ", "x") == logos.logo_uri("IWDA_EQ", "x")


def test_entries_from_older_versions_are_redone():
    logos._save_entry("OLD_EQ", {"file": None, "ts": 10**12})
    assert logos.needs_fetch("OLD_EQ", now=10**12 + 1)
    logos._save_entry("OLDLOGO_EQ", {"file": "x.png", "ts": 10**12, "v": logos.LOGO_VERSION - 1})
    assert logos.needs_fetch("OLDLOGO_EQ", now=10**12 + 1)
    logos._save_entry("KEEP_EQ", {"file": "x.png", "ts": 10**12, "v": logos.LOGO_VERSION})
    assert not logos.needs_fetch("KEEP_EQ", now=10**12 + 1)
    logos._save_entry("MISS_EQ", {"file": None, "ts": 10**12, "v": logos.VERSION - 1})
    assert logos.needs_fetch("MISS_EQ", now=10**12 + 1)
    logos._save_entry("NEW_EQ", {"file": None, "ts": 10**12, "v": logos.VERSION})
    assert not logos.needs_fetch("NEW_EQ", now=10**12 + 1)


def test_fmp_logo_is_preferred(monkeypatch):
    urls = []

    def fake_get(url, limit):
        urls.append(url)
        if url == logos.FMP_URL.format("SAP.DE"):
            return url, _png(), "image/png"
        raise ValueError("404")

    monkeypatch.setattr(logos, "_get", fake_get)
    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: "SAP.DE")
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: pytest.fail("no site lookup when FMP has the logo"))
    assert logos.fetch_logo("SAPd_EQ", "SAP SE") is True
    assert urls == [logos.FMP_URL.format("SAP.DE")]
    assert logos._load_index()["SAPd_EQ"]["source"] == "fmp"
    assert not logos.needs_fetch("SAPd_EQ")


def test_fmp_rejects_odd_symbols(monkeypatch):
    monkeypatch.setattr(logos, "_get", lambda *a: pytest.fail("no request for an invalid symbol"))
    assert logos.fmp_logo("../etc/passwd") is None
    assert logos.fmp_logo("") is None


def test_falls_back_to_site_when_fmp_has_no_logo(monkeypatch):
    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: "XYZ")
    monkeypatch.setattr(logos, "fmp_logo", lambda sym: None)
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: ("https://www.xyz.example", "XYZ", False))
    monkeypatch.setattr(logos, "_download_icon", lambda site: _png())
    assert logos.fetch_logo("XYZ_US_EQ", "XYZ") is True
    assert logos._load_index()["XYZ_US_EQ"]["source"] == "site"


def test_issuer_parent_logo_when_issuer_site_blocks(monkeypatch):
    asked = []
    monkeypatch.setattr(logos, "yahoo_symbol", lambda tk: "8RMY.DE")
    monkeypatch.setattr(logos, "yahoo_profile", lambda sym: ("", "WisdomTree", True))
    monkeypatch.setattr(logos, "_download_icon", lambda site: None)
    monkeypatch.setattr(logos, "fmp_logo", lambda sym: asked.append(sym) or (_png() if sym == "WT" else None))
    assert logos.fetch_logo("8RMYd_EQ", "WisdomTree Europe Defence") is True
    assert asked == ["8RMY.DE", "WT"]


def test_position_page_shows_the_logo():
    src = open(os.path.join(os.path.dirname(logos.__file__), "detail_view.py"), encoding="utf-8").read()
    assert "logos.logo_uri(ticker, name)" in src and 'width="64"' in src
    assert "_html.escape(str(name))" in src


def test_background_prefetch_passes_names_for_all_tickers(monkeypatch):
    import background
    calls = []
    monkeypatch.setattr(background.logos, "prefetch", lambda items: calls.append(list(items)) or [])
    monkeypatch.setattr(background, "xtb_instruments", lambda: [{"ticker": "SAP.DE", "name": "SAP SE"}])
    snap = {"instruments": [{"ticker": "AAPL_US_EQ", "name": "Apple"}]}
    background.prefetch_logos(snap, ["AAPL_US_EQ", "SAP.DE", "X_EQ"])
    assert calls == [[("AAPL_US_EQ", "Apple"), ("SAP.DE", "SAP SE"), ("X_EQ", "")]]
