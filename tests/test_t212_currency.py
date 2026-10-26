import json
import time

import pytest
import requests

import history_multi
import t212_api


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "account_info_cache.json"
    monkeypatch.setattr(t212_api, "ACCOUNT_INFO_CACHE_FILE", str(path))
    return path


def _fail(*a, **k):
    raise requests.ConnectionError("rate limited")


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


def test_fresh_cache_is_used_without_request(cache, monkeypatch):
    cache.write_text(json.dumps({"fetched_at": time.time(), "currencyCode": "RON"}))
    monkeypatch.setattr(t212_api.requests, "get", _fail)
    assert t212_api.fetch_account_currency("k", "s") == ("RON", None)


def test_expired_cache_is_used_when_request_fails(cache, monkeypatch):
    cache.write_text(json.dumps({"fetched_at": 0, "currencyCode": "RON"}))
    monkeypatch.setattr(t212_api.requests, "get", _fail)
    assert t212_api.fetch_account_currency("k", "s") == ("RON", None)
    monkeypatch.setattr(t212_api.requests, "get", lambda *a, **k: _Resp(429, {"error": "too many"}))
    assert t212_api.fetch_account_currency("k", "s") == ("RON", None)


def test_no_cache_and_failure_gives_none(cache, monkeypatch):
    monkeypatch.setattr(t212_api.requests, "get", _fail)
    code, err = t212_api.fetch_account_currency("k", "s")
    assert code is None and err


def test_successful_request_refreshes_cache(cache, monkeypatch):
    cache.write_text(json.dumps({"fetched_at": 0, "currencyCode": "EUR"}))
    monkeypatch.setattr(t212_api.requests, "get", lambda *a, **k: _Resp(200, {"currencyCode": "RON"}))
    assert t212_api.fetch_account_currency("k", "s") == ("RON", None)
    assert json.loads(cache.read_text())["currencyCode"] == "RON"


def test_history_point_skipped_when_t212_currency_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(history_multi, "HISTORY_MULTI_FILE", str(tmp_path / "hm.json"))
    monkeypatch.setattr(history_multi, "load_cached_snapshot", lambda: {"cash": {"invested": 1000.0, "ppl": 100.0}})
    monkeypatch.setattr(history_multi, "xtb_rows", lambda: [])
    monkeypatch.setattr(t212_api, "fetch_account_currency", lambda *a: (None, "down"))
    monkeypatch.setattr("core.load_config", lambda: {})
    assert history_multi.record_multi_point(force=True) is False
    assert history_multi.load_multi_history() == []
