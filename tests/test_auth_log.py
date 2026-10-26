import pytest
from streamlit.testing.v1 import AppTest

import auth
import logwatch
import users

PW = "ana-secret-pass-42"


def _page():
    import auth
    import streamlit as st
    me = auth._authenticate()
    st.write("in:" + me)
    if st.button("out", key="out"):
        auth._logout()


@pytest.fixture
def ana(monkeypatch):
    users.create_user("ana", PW, "admin")
    monkeypatch.setattr(auth, "_cookie_js", lambda *a: None)
    monkeypatch.setattr(auth, "_check_device", lambda me: None)
    monkeypatch.setattr(auth, "_read_cookie", lambda: None)
    monkeypatch.setattr(auth, "_client", lambda: ("UA", "203.0.113.7"))


def _login(at, name, pw):
    at.text_input[0].input(name)
    at.text_input[1].input(pw)
    return at.button[0].click().run()


def _auth_lines(capsys):
    return [l for l in capsys.readouterr().out.splitlines() if l.startswith("[auth] ")]


def test_login_ok_and_logout_are_logged(ana, capsys):
    at = AppTest.from_function(_page).run()
    _login(at, "Ana", PW)
    assert any(m.value == "in:ana" for m in at.markdown)
    at.button(key="out").click().run()
    lines = _auth_lines(capsys)
    assert lines == ["[auth] login ok user=ana ip=203.0.113.7 via=password", "[auth] logout user=ana ip=203.0.113.7"]
    assert not any(PW in l for l in lines)


def test_failed_login_and_lockout_are_logged_without_password(ana, capsys):
    at = AppTest.from_function(_page).run()
    for _ in range(auth._MAX_FAILS):
        _login(at, "ana", "wrong-" + PW)
    _login(at, "ana", PW)
    lines = _auth_lines(capsys)
    assert sum(l.startswith("[auth] login failed user=ana ") for l in lines) == auth._MAX_FAILS
    assert any(l.startswith("[auth] account locked user=ana ") and "failures=5" in l and "seconds=300" in l
               for l in lines)
    assert lines[-1].startswith("[auth] login refused user=ana ") and "reason=locked" in lines[-1]
    assert not any(PW in l for l in lines)


def test_password_typed_as_name_is_not_logged(ana, capsys):
    at = AppTest.from_function(_page).run()
    _login(at, "My Secret P@ss!", "x")
    lines = _auth_lines(capsys)
    assert lines == [l for l in lines if "user=<invalid>" in l] and lines
    assert not any("Secret" in l for l in lines)


def test_auth_lines_are_shown_in_the_log_but_are_not_problems():
    line = "[auth] login failed user=ana ip=1.2.3.4 reason=bad user or password"
    assert not logwatch.is_problem(line)
    assert not logwatch.IGNORE.search(line)  # „Ascunde zgomotul cunoscut” nu le ascunde


def test_rejected_cookie_is_logged(ana, capsys, monkeypatch):
    tok = users.make_token("ana")
    forged = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    monkeypatch.setattr(auth, "_read_cookie", lambda: forged)
    AppTest.from_function(_page).run()
    assert _auth_lines(capsys)[0] == "[auth] cookie rejected user=- ip=203.0.113.7 reason=invalid"


def test_valid_cookie_resumes_session(ana, capsys, monkeypatch):
    tok = users.make_token("ana")
    monkeypatch.setattr(auth, "_read_cookie", lambda: tok)
    at = AppTest.from_function(_page).run()
    assert any(m.value == "in:ana" for m in at.markdown)
    lines = _auth_lines(capsys)
    assert lines == ["[auth] session resumed user=ana ip=203.0.113.7 via=cookie"]
    assert tok not in lines[0]


def test_ip_header_cannot_inject_text(monkeypatch, capsys):
    monkeypatch.setattr(auth, "_client", lambda: ("UA", "1.2.3.4 user=admin\n[auth] login ok"))
    auth._log("login failed", "ana")
    assert capsys.readouterr().out == "[auth] login failed user=ana ip=<invalid>\n"
    monkeypatch.setattr(auth, "_client", lambda: ("UA", "2001:db8::1"))
    auth._log("login ok", "ana")
    assert capsys.readouterr().out == "[auth] login ok user=ana ip=2001:db8::1\n"
