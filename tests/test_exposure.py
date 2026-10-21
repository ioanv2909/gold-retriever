import json

import pytest

import exposure as ex

META = {
    "AAPL": {"kind": "stock", "sector": "Technology", "country": "United States", "sectors": {}},
    "SAP": {"kind": "stock", "sector": "Technology", "country": "Germany", "sectors": {}},
    "SPY": {"kind": "etf", "sector": None, "country": None,
            "sectors": {"Technology": 0.5, "Healthcare": 0.3, "Energy": 0.1}},
}
ROWS = [
    {"ticker": "AAPL", "value": 300.0, "currency": "USD"},
    {"ticker": "SAP", "value": 200.0, "currency": "EUR"},
    {"ticker": "SPY", "value": 400.0, "currency": "USD"},
    {"ticker": "NEW", "value": 100.0, "currency": "GBP"},
    {"ticker": "ZERO", "value": 0.0, "currency": "USD"},
]


def as_dict(items):
    return {k: (round(v, 6), round(p, 6)) for k, v, p in items}


def test_parse_meta_stock_and_etf():
    assert ex.parse_meta({"quoteType": "EQUITY", "sector": "Technology", "country": "Germany"}) == {
        "kind": "stock", "sector": "Technology", "country": "Germany", "sectors": {}}
    m = ex.parse_meta({"quoteType": "ETF"}, {"technology": 0.4, "realestate": 0.02, "energy": 0, "bad": "x"})
    assert m["kind"] == "etf" and m["sectors"] == {"Technology": 0.4, "Real Estate": 0.02}
    assert ex.parse_meta({})["kind"] == "other"


def test_sector_breakdown_looks_through_etfs():
    out = as_dict(ex.breakdown(ROWS, META, "sector"))
    assert out["Technology"][0] == pytest.approx(300 + 200 + 200)
    assert out["Healthcare"][0] == pytest.approx(120)
    assert out[ex.OTHER][0] == pytest.approx(40)
    assert out[ex.UNKNOWN][0] == pytest.approx(100)
    assert sum(p for _, p in out.values()) == pytest.approx(100)
    assert ex.breakdown(ROWS, META, "sector")[0][0] == "Technology"


def test_country_and_currency():
    out = as_dict(ex.breakdown(ROWS, META, "country"))
    assert out == {"United States": (300, 30), ex.ETF: (400, 40), "Germany": (200, 20), ex.UNKNOWN: (100, 10)}
    out = as_dict(ex.breakdown(ROWS, META, "currency"))
    assert out == {"USD": (700, 70), "EUR": (200, 20), "GBP": (100, 10)}


def test_empty_portfolio():
    assert ex.breakdown([], META, "sector") == []
    assert ex.breakdown([{"ticker": "A", "value": None}], META, "currency") == []


def test_fetch_only_missing_or_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EXPOSURE_CACHE_FILE", str(tmp_path / "c.json"))
    monkeypatch.setattr(ex, "EXPOSURE_STATUS_FILE", str(tmp_path / "s.json"))
    (tmp_path / "c.json").write_text(json.dumps({
        "FRESH": {"kind": "stock", "fetched_at": 1000.0},
        "OLD": {"kind": "stock", "fetched_at": 1000.0 - ex.EXPOSURE_REFRESH_INTERVAL},
    }))
    calls = []

    def fake(symbol):
        calls.append(symbol)
        return (None, "404") if symbol == "BAD.Y" else (ex.parse_meta({"quoteType": "EQUITY", "sector": "Energy"}), None)

    monkeypatch.setattr(ex, "fetch_meta", fake)
    cache = ex.fetch_and_cache(["FRESH", "OLD", "BAD"], resolve=lambda t: t + ".Y", now=1000.0, sleep=0)
    assert calls == ["OLD.Y", "BAD.Y"]
    assert cache["OLD"]["sector"] == "Energy" and cache["BAD"]["error"] == "404" and cache["BAD"]["kind"] == "other"
    assert set(json.loads((tmp_path / "c.json").read_text())) == {"FRESH", "OLD", "BAD"}
    assert ex.load_status()["in_progress"] is False


def test_parse_countries():
    out = ex.parse_countries([{"name": "United States", "percentage": 59.77}, {"name": "Other", "percentage": 9.3},
                              {"name": "", "percentage": 5}, {"name": "Japan", "percentage": "bad"}, None])
    assert out == pytest.approx({"United States": 0.5977, ex.OTHER: 0.093})
    assert ex.parse_countries(None) == {}


def test_country_breakdown_looks_through_etfs():
    meta = dict(META, SPY=dict(META["SPY"], countries={"United States": 0.9, ex.OTHER: 0.05}))
    out = as_dict(ex.breakdown(ROWS, meta, "country"))
    assert out["United States"][0] == pytest.approx(300 + 360)
    assert out[ex.OTHER][0] == pytest.approx(20 + 20)  # "Other" din justETF + restul pana la 100%
    assert ex.ETF not in out


def test_fetch_countries_falls_back_without_expansion(monkeypatch):
    import types
    calls = []

    def overview(isin, include_gettex=True, expand_allocations=True):
        calls.append(expand_allocations)
        return {"countries": [] if expand_allocations else [{"name": "United States", "percentage": 97.5}]}

    monkeypatch.setattr(ex, "_justetf", lambda: types.SimpleNamespace(get_etf_overview=overview))
    assert ex.fetch_countries("IE00B5BMR087") == pytest.approx({"United States": 0.975})
    assert calls == [True, False]


def test_etf_countries_fetched_and_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EXPOSURE_CACHE_FILE", str(tmp_path / "c.json"))
    monkeypatch.setattr(ex, "EXPOSURE_STATUS_FILE", str(tmp_path / "s.json"))
    (tmp_path / "c.json").write_text(json.dumps({
        "OLD_ETF": {"kind": "etf", "sectors": {}, "fetched_at": 1000.0},          # dinainte de tari: se reia
        "STOCK": {"kind": "stock", "country": "United States", "fetched_at": 1000.0},
    }))
    monkeypatch.setattr(ex, "fetch_meta", lambda s: (ex.parse_meta({"quoteType": "ETF"}), None))
    asked = []

    def countries(isin):
        asked.append(isin)
        return None if isin == "DOWN" else {"Japan": 1.0}

    isins = {"OLD_ETF": "IE1", "NEW_ETF": "DOWN", "STOCK": "US1"}
    cache = ex.fetch_and_cache(["OLD_ETF", "NEW_ETF", "STOCK"], resolve=str, now=2000.0, sleep=0,
                               isins=isins, countries_fn=countries)
    assert asked == ["IE1", "DOWN"]
    assert cache["OLD_ETF"]["countries"] == {"Japan": 1.0}
    assert cache["NEW_ETF"]["countries"] == {} and cache["NEW_ETF"]["countries_error"] is True
    # eroarea se reincearca dupa o zi, nu la fiecare tur
    asked.clear()
    ex.fetch_and_cache(["NEW_ETF"], resolve=str, now=2000.0 + 3600, sleep=0, isins=isins, countries_fn=countries)
    assert asked == []
    ex.fetch_and_cache(["NEW_ETF"], resolve=str, now=2000.0 + ex.COUNTRIES_RETRY, sleep=0, isins=isins,
                       countries_fn=countries)
    assert asked == ["DOWN"]


def test_stock_without_yahoo_country_uses_isin(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EXPOSURE_CACHE_FILE", str(tmp_path / "c.json"))
    monkeypatch.setattr(ex, "EXPOSURE_STATUS_FILE", str(tmp_path / "s.json"))
    # intrare veche, fara tara: se reia o data, apoi nu mai e "stale"
    (tmp_path / "c.json").write_text(json.dumps({"NOCTRY": {"kind": "stock", "country": None, "fetched_at": 1000.0}}))
    monkeypatch.setattr(ex, "fetch_meta", lambda s: (ex.parse_meta({"quoteType": "EQUITY", "sector": "Energy"}), None))
    asked = []
    cache = ex.fetch_and_cache(["NOCTRY", "ZZ"], resolve=str, now=2000.0, sleep=0,
                               isins={"NOCTRY": "NL0000235190", "ZZ": "XX123"}, countries_fn=asked.append)
    assert cache["NOCTRY"]["country"] == "Netherlands" and cache["NOCTRY"]["isin_checked"] is True
    assert cache["ZZ"]["country"] is None and asked == []  # prefix necunoscut; actiunile nu se cauta pe justETF
    ex.fetch_and_cache(["ZZ"], resolve=str, now=2100.0, sleep=0, isins={"ZZ": "XX123"},
                       countries_fn=asked.append)
    assert ex.load_cache()["ZZ"]["fetched_at"] == 2000.0  # verificat deja, nu se reia


def test_unclassified_found_on_justetf_becomes_etf(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EXPOSURE_CACHE_FILE", str(tmp_path / "c.json"))
    monkeypatch.setattr(ex, "EXPOSURE_STATUS_FILE", str(tmp_path / "s.json"))
    monkeypatch.setattr(ex, "fetch_meta", lambda s: (ex.parse_meta({"quoteType": "NONE"}), None))
    cache = ex.fetch_and_cache(["X"], resolve=str, now=1.0, sleep=0, isins={"X": "IE1"},
                               countries_fn=lambda isin: {"Japan": 1.0})
    assert cache["X"]["kind"] == "etf" and cache["X"]["countries"] == {"Japan": 1.0}


def test_justetf_session_gets_a_timeout(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

    def fake_request(self, method, url, **kwargs):
        seen.update(kwargs)
        return Resp()

    monkeypatch.setattr(ex.requests.Session, "request", fake_request)
    assert isinstance(ex._TimeoutSession().get("https://example.invalid"), Resp)
    assert seen["timeout"] == ex.JUSTETF_TIMEOUT
    assert ex.health.status("justetf")["level"] == "green"
