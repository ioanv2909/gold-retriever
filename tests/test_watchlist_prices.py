import json

import pandas as pd
import pytest

import watchlist


@pytest.fixture
def wl(tmp_path, monkeypatch):
    files = {n: tmp_path / (n + ".json") for n in ("watchlist", "cache", "status")}
    monkeypatch.setattr(watchlist, "WATCHLIST_FILE", str(files["watchlist"]))
    monkeypatch.setattr(watchlist, "WATCHLIST_CACHE_FILE", str(files["cache"]))
    monkeypatch.setattr(watchlist, "WATCHLIST_STATUS_FILE", str(files["status"]))
    monkeypatch.setattr(watchlist, "YFINANCE_AVAILABLE", True)
    files["watchlist"].write_text(json.dumps([{"symbol": "nvda"}, {"symbol": "SAP.DE"}, {"symbol": "NEW"}]))
    files["cache"].write_text(json.dumps({
        "NVDA": {"name": "NVIDIA", "price": 100.0, "quality_total": 80, "updated": "2026-10-27T03:00:00"},
        "SAP.DE": {"name": "SAP", "price": 200.0, "updated": "2026-10-27T03:00:01"},
    }))
    return files


def _multi(prices):
    cols = pd.MultiIndex.from_product([list(prices), ["Open", "Close"]])
    row = [v for p in prices.values() for v in (p, p)]
    return pd.DataFrame([row, row], columns=cols)


def test_only_price_changes_and_scores_keep_their_date(wl, monkeypatch):
    calls = []
    monkeypatch.setattr(watchlist.yf, "download", lambda s, **k: calls.append(list(s)) or _multi({"NEW": 1.0, "NVDA": 123.456, "SAP.DE": 210.0}))
    assert watchlist.refresh_watchlist_prices() == {"NEW": 1.0, "NVDA": 123.46, "SAP.DE": 210.0}
    assert calls == [["NEW", "NVDA", "SAP.DE"]]  # o singura cerere pentru toate
    cache = json.loads(wl["cache"].read_text())
    assert cache["NVDA"]["price"] == 123.46 and cache["NVDA"]["quality_total"] == 80
    assert cache["NVDA"]["updated"] == "2026-10-27T03:00:00" and cache["NVDA"]["price_updated"] > "2026-10-27T03"
    assert "NEW" not in cache  # simbolurile noi raman pe calculul complet


def test_single_symbol_frame(wl, monkeypatch):
    wl["watchlist"].write_text(json.dumps([{"symbol": "NVDA"}]))
    monkeypatch.setattr(watchlist.yf, "download", lambda s, **k: pd.DataFrame({"Close": [99.0, 101.0]}))
    assert watchlist.refresh_watchlist_prices() == {"NVDA": 101.0}


def test_skipped_while_the_full_refresh_runs_or_yahoo_fails(wl, monkeypatch):
    before = wl["cache"].read_text()
    monkeypatch.setattr(watchlist, "read_status", lambda p: {"in_progress": True})
    assert watchlist.refresh_watchlist_prices() == {}
    monkeypatch.setattr(watchlist, "read_status", lambda p: {})

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(watchlist.yf, "download", boom)
    assert watchlist.refresh_watchlist_prices() == {}
    assert wl["cache"].read_text() == before
