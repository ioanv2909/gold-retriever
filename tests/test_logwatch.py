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


@pytest.fixture
def tail(monkeypatch):
    buf = lw.collections.deque(maxlen=lw.TAIL)
    monkeypatch.setattr(lw, "_tail", buf)
    return buf


def test_tail_keeps_every_line_in_order(env, tail):
    tee = lw._Tee(io.StringIO())
    tee.write("first\r\nTraceback (most recent call last)\n  File x\nKeyError: 'a'\n\nlast")
    assert [l.split("  ", 1)[1] for l in lw.tail()] == ["first", "Traceback (most recent call last)", "  File x",
                                                       "KeyError: 'a'"]
    tee.write("\n")
    assert lw.tail(1)[0].endswith("  last")


def test_tail_is_capped_at_1000_lines(env, tail):
    tee = lw._Tee(io.StringIO())
    tee.write("".join("line %d\n" % i for i in range(1500)))
    rows = lw.tail()
    assert lw.TAIL == 1000 and len(rows) == 1000
    assert rows[0].endswith("line 500") and rows[-1].endswith("line 1499")
    assert len(lw.tail(100)) == 100 and lw.tail(100)[0].endswith("line 1400")


def test_tail_filters_noise_and_text(env, tail):
    tee = lw._Tee(io.StringIO())
    tee.write("Thread 'MainThread': missing ScriptRunContext! x\n[t212] user=ana http=401\nother\n")
    assert len(lw.tail()) == 3
    assert [r.split("  ", 1)[1] for r in lw.tail(hide_noise=True)] == ["[t212] user=ana http=401", "other"]
    assert [r.split("  ", 1)[1] for r in lw.tail(query="T212")] == ["[t212] user=ana http=401"]


def test_log_tab_only_for_admins(monkeypatch):
    import settings_page
    seen = {}

    def fake_tabs(items, key):
        seen["ids"] = [i for i, _ in items]
        return {i: type("T", (), {"open": False})() for i, _ in items}
    monkeypatch.setattr(settings_page, "url_tabs", fake_tabs)
    monkeypatch.setattr(settings_page.st, "columns", lambda *a, **k: [type("C", (), {
        "button": lambda *a, **k: False, "markdown": lambda *a, **k: None,
        "__enter__": lambda s: s, "__exit__": lambda s, *a: None})() for _ in range(3)])
    monkeypatch.setattr(settings_page, "lang_button", lambda key: None)
    for role, has_log in (("admin", True), ("user", False)):
        monkeypatch.setattr(settings_page.users, "role", lambda me, r=role: r)
        settings_page.render_settings("ana")
        assert ("log" in seen["ids"]) is has_log


def test_tail_newest_first(env, tail):
    tee = lw._Tee(io.StringIO())
    tee.write("".join("line %d\n" % i for i in range(10)))
    rows = [r.split("  ", 1)[1] for r in lw.tail(3, newest_first=True)]
    assert rows == ["line 9", "line 8", "line 7"]
    assert [r.split("  ", 1)[1] for r in lw.tail(3)] == ["line 7", "line 8", "line 9"]


def test_log_tab_shows_newest_first_by_default(env, tail):
    from streamlit.testing.v1 import AppTest

    def page():
        import log_ui
        log_ui.render_log("ana")
    tee = lw._Tee(io.StringIO())
    tee.write("old line\nnew line\n")
    at = AppTest.from_function(page).run()
    assert at.code[0].value.splitlines()[0].endswith("new line")
    at.selectbox(key="lg_order").select("asc").run()
    assert at.code[0].value.splitlines()[0].endswith("old line")
