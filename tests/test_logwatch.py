import io
import json
import logging

import pytest

import logwatch as lw
import notify


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(lw, "PROBLEMS_FILE", str(tmp_path / "log_problems.json"))
    monkeypatch.setattr(lw, "_problems", {})
    monkeypatch.setattr(lw, "_state", {"last_mail": None, "dirty": False, "installed": False})
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *a, **kw: sent.append((a, kw)) or True)
    return sent


@pytest.mark.parametrize("line", [
    "[quality] AAPL_US_EQ: division by zero",
    'HTTP Error 401: {"finance":{"error":{"code":"Unauthorized"}}}',
    "2026-10-21 10:00:00.000 ERROR streamlit: Uncaught app exception",
    "Traceback: KeyError: 'price'",
])
def test_problems_are_detected(line):
    assert lw.is_problem(line)


@pytest.mark.parametrize("line", [
    "Cookie fetch from fc.yahoo.com failed (ConnectionError), continuing without it",
    'HTTP Error 404: {"quoteSummary":{"error":{"description":"No fundamentals data found for symbol: VWCE.DE"}}}',
    "Thread 'MainThread': missing ScriptRunContext! This warning can be ignored",
    "[yf_compat] HTTP 401, new crumb and retry 1/2",
    "Exception in thread Thread-1 (<lambda>):",
    "  You can now view your Streamlit app in your browser.",
])
def test_known_noise_is_ignored(line):
    assert not lw.is_problem(line)


def test_signature_groups_same_error_for_different_tickers():
    a = lw.signature("[quality] AAPL_US_EQ: HTTP Error 500 for symbol: AAPL at 12.5s")
    b = lw.signature("[quality] AAPL_US_EQ: HTTP Error 502 for symbol: KO at 3.1s")
    assert a == b
    assert lw.signature('HTTP Error 401: {"a": 1}') == lw.signature('HTTP Error 401: {"b": 2}')


def test_tee_records_lines_and_one_entry_per_traceback(env):
    out = io.StringIO()
    tee = lw._Tee(out)
    tee.write("[events] KO_US_EQ: timeout\nnormal line\n")
    tee.write("Traceback (most recent call last):\n  File \"x.py\", line 1\n    boom()\nValueError: bad value\n")
    tee.write("[events] partial")  # fara newline: inca neinregistrata
    assert out.getvalue().startswith("[events] KO_US_EQ: timeout\n")
    samples = sorted(p["sample"] for p in lw._problems.values())
    assert samples == ["Traceback: ValueError: bad value", "[events] KO_US_EQ: timeout"]


def test_new_pattern_mails_once_and_is_throttled(env):
    lw.record("[alerts] smtp down", now=1000.0)
    lw.record("[alerts] smtp down", now=1001.0)
    assert lw.flush(now=1002.0) is True
    assert len(env) == 1
    (event, subject, body), kw = env[0]
    assert event == "logs" and "(1)" in subject and "2× [alerts] smtp down" in body
    # acelasi tipar din nou: nu mai e nou, fara email
    lw.record("[alerts] smtp down", now=1100.0)
    lw.flush(now=1101.0)
    assert len(env) == 1
    # tipar nou prea curand: asteapta pana trec 30 de minute
    lw.record("[events] calendar failed", now=1200.0)
    lw.flush(now=1201.0)
    assert len(env) == 1
    lw.flush(now=1000.0 + lw.MAIL_EVERY + 5)
    assert len(env) == 2 and "[events] calendar failed" in env[1][0][2]
    saved = json.load(open(lw.PROBLEMS_FILE))["problems"]
    assert len(saved) == 2 and [p["sample"] for p in lw.recent()][0] == "[events] calendar failed"


def test_pattern_is_new_again_after_the_window(env):
    lw.record("[history] disk full", now=1000.0)
    lw.flush(now=1000.0)
    lw.record("[history] disk full", now=1000.0 + lw.WINDOW + 10)
    lw.flush(now=1000.0 + lw.WINDOW + lw.MAIL_EVERY + 20)
    assert len(env) == 2


def test_clear_empties_the_list(env):
    lw.record("[risk] X: boom", now=1.0)
    lw.clear()
    assert lw.recent() == [] and env == []


def test_existing_log_handlers_are_redirected():
    original = io.StringIO()
    handler = logging.StreamHandler(original)
    lg = logging.getLogger("gr_test_logger")
    lg.addHandler(handler)
    tee = lw._Tee(original)
    try:
        lw._redirect_log_handlers({id(original): tee})
        assert handler.stream is tee
    finally:
        lg.removeHandler(handler)
