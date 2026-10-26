import json
import time

import pytest

import history_multi
import portfolio_model
import t212_api

D = 86400


@pytest.fixture
def yahoo(monkeypatch):
    """Yahoo simulat: rates[pair] = curs, sau None pentru esec."""
    rates = {}

    def fake(pair):
        r = rates.get(pair)
        if r is None:
            raise ConnectionError("yahoo down")
        return r

    monkeypatch.setattr(t212_api, "_yahoo_fx", fake)
    monkeypatch.setattr(portfolio_model, "_FX_CACHE", {})
    return rates


def test_success_is_returned_and_saved(yahoo):
    yahoo["RONEUR"] = 0.2
    assert t212_api.fetch_fx_rate("RON", "EUR") == (0.2, None)
    saved = json.load(open(t212_api.FX_LAST_GOOD_FILE))
    assert saved["RONEUR"][1] == 0.2
    assert t212_api.fx_failures() == 0


def test_failure_uses_last_good_rate(yahoo):
    yahoo["RONEUR"] = 0.2
    t212_api.fetch_fx_rate("RON", "EUR")
    yahoo["RONEUR"] = None
    assert t212_api.fetch_fx_rate("RON", "EUR") == (0.2, None)
    assert t212_api.fx_failures() == 0


def test_last_good_rate_survives_restart(yahoo, monkeypatch):
    yahoo["RONEUR"] = 0.2
    t212_api.fetch_fx_rate("RON", "EUR")
    monkeypatch.setattr(t212_api, "_fx_last_good", {})
    monkeypatch.setattr(t212_api, "_fx_state", {"loaded": False, "failures": 0})
    yahoo["RONEUR"] = None
    assert t212_api.fetch_fx_rate("RON", "EUR") == (0.2, None)


def test_failure_without_known_rate_is_counted(yahoo):
    rate, err = t212_api.fetch_fx_rate("RON", "EUR")
    assert rate == 1.0 and err
    assert t212_api.fx_failures() == 1


def test_too_old_last_good_rate_is_not_used(yahoo):
    t212_api._fx_last_good["RONEUR"] = (time.time() - 8 * D, 0.2)
    t212_api._fx_state["loaded"] = True
    rate, err = t212_api.fetch_fx_rate("RON", "EUR")
    assert rate == 1.0 and err and t212_api.fx_failures() == 1


def test_failed_rate_is_cached_one_minute_only(yahoo):
    assert portfolio_model.fx("RON", "EUR") == 1.0
    ts, _ = portfolio_model._FX_CACHE[("RON", "EUR")]
    assert time.time() - ts >= portfolio_model._FX_CACHE_TTL_SECONDS - 61
    yahoo["RONEUR"] = 0.2
    portfolio_model._FX_CACHE[("RON", "EUR")] = (ts - 61, 1.0)  # a trecut minutul
    assert portfolio_model.fx("RON", "EUR") == 0.2


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(history_multi, "HISTORY_MULTI_FILE", str(tmp_path / "hm.json"))
    monkeypatch.setattr(history_multi, "load_cached_snapshot", lambda: {"cash": {"invested": 1000.0, "ppl": 100.0}})
    monkeypatch.setattr(history_multi, "xtb_rows", lambda: [])
    monkeypatch.setattr(history_multi, "fx", lambda a, b: t212_api.fetch_fx_rate(a, b)[0])


def test_history_point_skipped_when_a_rate_is_made_up(yahoo, snapshot):
    yahoo["USDEUR"] = None
    assert history_multi.record_multi_point("EUR", force=True) is False
    assert history_multi.load_multi_history() == []


def test_history_point_written_with_real_rates(yahoo, snapshot):
    yahoo["USDEUR"] = 0.9
    assert history_multi.record_multi_point("EUR", force=True) is True
    (p,) = history_multi.load_multi_history()
    assert p["rates"] == {"EUR": 1.0, "USD": 0.9}
