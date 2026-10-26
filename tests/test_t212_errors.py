import base64
import json

import pytest
import requests

import i18n
import returns_summary
import t212_api
import t212_history
import t212_history_rebuild
from userctx import as_user

KEY, SECRET = "KEYID123456", "SuperSecretValue987"
TOKEN = base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def respond(monkeypatch, tmp_path):
    monkeypatch.setattr(t212_api, "INSTRUMENTS_CACHE_FILE", str(tmp_path / "instr.json"))
    monkeypatch.setattr(t212_api, "ACCOUNT_INFO_CACHE_FILE", str(tmp_path / "info.json"))
    monkeypatch.setattr(t212_api.time, "sleep", lambda s: None)
    monkeypatch.setattr(t212_history.time, "sleep", lambda s: None)
    monkeypatch.setattr(t212_history_rebuild.time, "sleep", lambda s: None)
    monkeypatch.setattr(returns_summary.time, "sleep", lambda s: None)

    def set_(status, body=None):
        body = body if body is not None else {"code": "Err", "echo": f"Basic {TOKEN} {KEY} {SECRET}"}
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(status, body))
    return set_


def _no_secret(text):
    for s in (KEY, SECRET, TOKEN, "Authorization"):
        assert s not in text


CALLS = {
    "cash": lambda: t212_api.fetch_cash(KEY, SECRET),
    "portfolio": lambda: t212_api.fetch_portfolio(KEY, SECRET),
    "instruments": lambda: t212_api.fetch_instruments(KEY, SECRET),
    "orders": lambda: t212_api.fetch_order_history_for_ticker(KEY, SECRET, "AAPL_US_EQ"),
    "dividends": lambda: t212_api.fetch_dividends_for_ticker(KEY, SECRET, "AAPL_US_EQ"),
}
EXPECTED = {
    401: ("cheia API sau secretul nu sunt acceptate", "the API key or secret is not accepted"),
    403: ("lipsesc permisiuni", "lacks permissions"),
    429: ("prea multe cereri", "too many requests"),
    500: ("HTTP 500): eroare API", "HTTP 500): API error"),
}


@pytest.mark.parametrize("code", sorted(EXPECTED))
@pytest.mark.parametrize("name", sorted(CALLS))
def test_message_by_status_and_log_line(name, code, respond, capsys, monkeypatch):
    respond(code)
    with as_user("ana"):
        data, err = CALLS[name]()
    assert data is None
    ro, en = EXPECTED[code]
    assert ro in err and f"HTTP {code}" in err
    _no_secret(err)
    monkeypatch.setattr(i18n, "lang", lambda: "EN")
    assert en in i18n.x(err)
    log = capsys.readouterr().out
    assert f"user=ana endpoint=/equity/" in log and f"http={code}" in log
    assert "body=" in log and "***" in log
    _no_secret(log)


def test_account_info_error_without_cache(respond, capsys):
    respond(401)
    code, err = t212_api.fetch_account_currency(KEY, SECRET)
    assert code is None and "HTTP 401" in err
    log = capsys.readouterr().out
    assert "endpoint=/equity/account/info" in log and "http=401" in log
    _no_secret(err + log)


def test_log_body_is_cut_to_200_chars_after_scrubbing(respond, capsys):
    respond(500, SECRET + "x" * 1000)
    t212_api.fetch_cash(KEY, SECRET)
    log = capsys.readouterr().out
    body = log.split("body=", 1)[1].strip()
    assert body == repr("***" + "x" * 197)
    _no_secret(log)


def test_secret_split_at_cut_does_not_leak(respond, capsys):
    respond(500, "y" * 190 + SECRET)
    t212_api.fetch_cash(KEY, SECRET)
    log = capsys.readouterr().out
    assert SECRET[:8] not in log


def test_network_error_does_not_show_secret(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError(f"failed with {SECRET}")
    monkeypatch.setattr(requests, "get", boom)
    _, err = t212_api.fetch_cash(KEY, SECRET)
    assert "Eroare rețea" in err
    _no_secret(err)


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_history_endpoints_log_errors(code, respond, capsys, monkeypatch):
    respond(code)
    monkeypatch.setattr(t212_history_rebuild, "load_config", lambda: {"api_key_id": KEY, "api_secret": SECRET})
    monkeypatch.setattr(t212_history_rebuild, "load_json_file", lambda *a, **k: {})
    with as_user("ana"):
        assert t212_history.fetch_pages(KEY, SECRET, "/equity/history/transactions", "tx") == ([], False)
        assert returns_summary._fetch_transactions(KEY, SECRET) == ([], False)
        t212_history_rebuild._sync_fills()
    log = capsys.readouterr().out
    for ep in ("/equity/history/transactions", "/equity/history/orders"):
        assert f"user=ana endpoint={ep} http={code}" in log
    assert EXPECTED[code][0] in log  # mesajul scriptului t212_history
    _no_secret(log)


def test_every_error_message_has_both_languages():
    for key in ("t212.err.401", "t212.err.403", "t212.err.429", "t212.err.other"):
        assert i18n._T[key]["RO"] and i18n._T[key]["EN"]
