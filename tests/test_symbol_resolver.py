import json
import os

import pytest

import core
import symbol_resolver as sr
import yahoo


@pytest.fixture
def yahoo_fake(monkeypatch):
    priced = {"IITU.L", "EXI2.DE", "AAPL"}
    searches = {"IITU": ["IITU.L", "IUIT.L"], "DE0006289382": ["EXI2.DE"]}
    calls = []
    monkeypatch.setattr(sr, "has_prices", lambda s: calls.append(s) or s in priced)
    monkeypatch.setattr(sr, "_search", lambda q: searches.get(q, []))
    monkeypatch.setattr(core, "load_ticker_map", lambda: {})
    monkeypatch.setattr(yahoo, "load_ticker_map", lambda: {})
    return calls


def test_wrong_guess_is_fixed_by_base_symbol_and_by_isin(yahoo_fake):
    fixed = sr.fix_symbols(["IITU", "DJGTEEX.DE", "AAPL_US_EQ"], {"DJGTEEX.DE": "DE0006289382"}, now=1000)
    assert fixed == {"IITU": "IITU.L", "DJGTEEX.DE": "EXI2.DE"}
    assert yahoo.resolve_yahoo_symbol("IITU") == "IITU.L"
    assert yahoo.resolve_yahoo_symbol("DJGTEEX.DE") == "EXI2.DE"
    assert yahoo.resolve_yahoo_symbol("AAPL_US_EQ") == "AAPL"


def test_checked_tickers_wait_a_week(yahoo_fake):
    sr.fix_symbols(["AAPL_US_EQ"], now=1000)
    yahoo_fake.clear()
    sr.fix_symbols(["AAPL_US_EQ"], now=1000 + sr.RECHECK_S - 1)
    assert yahoo_fake == []
    sr.fix_symbols(["AAPL_US_EQ"], now=1000 + sr.RECHECK_S + 1)
    assert yahoo_fake == ["AAPL"]


def test_manual_mapping_wins(yahoo_fake, monkeypatch):
    monkeypatch.setattr(core, "load_ticker_map", lambda: {"IITU": "MINE.L"})
    monkeypatch.setattr(yahoo, "load_ticker_map", lambda: {"IITU": "MINE.L"})
    assert sr.fix_symbols(["IITU"], now=1000) == {}
    assert yahoo.resolve_yahoo_symbol("IITU") == "MINE.L"


def test_not_found_is_remembered_without_a_symbol(yahoo_fake):
    assert sr.fix_symbols(["ZZZZ_EQ"], now=1000) == {}
    data = json.load(open(os.fspath(sr.AUTO_MAP_FILE)))
    assert data["ZZZZ_EQ"]["symbol"] is None and data["ZZZZ_EQ"]["guess"] == "ZZZZ"
    assert yahoo.resolve_yahoo_symbol("ZZZZ_EQ") == "ZZZZ"
