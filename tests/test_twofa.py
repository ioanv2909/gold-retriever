import json
import time

import pytest
from streamlit.testing.v1 import AppTest

import auth
import twofa
import users

PW = "ana-secret-pass-42"
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"


def _now_code(secret, offset=0):
    return twofa.code_at(secret, int(time.time() // twofa.STEP) + offset)


@pytest.mark.parametrize("t,code", [(59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
                                    (1234567890, "005924"), (2000000000, "279037")])
def test_rfc6238_vectors(t, code):
    assert twofa.code_at(RFC_SECRET, t // 30) == code
    assert twofa.match_step(RFC_SECRET, code, now=t) == t // 30


def test_window_and_format():
    now = 1234567890
    step = now // 30
    for off in (-1, 0, 1):
        assert twofa.match_step(RFC_SECRET, twofa.code_at(RFC_SECRET, step + off), now=now) == step + off
    for off in (-2, 2):
        assert twofa.match_step(RFC_SECRET, twofa.code_at(RFC_SECRET, step + off), now=now) is None
    assert twofa.match_step(RFC_SECRET, "005 924", now=now) == step
    for bad in ("", "abcdef", "00592", "0059244", None):
        assert twofa.match_step(RFC_SECRET, bad, now=now) is None


def test_secret_uri_and_qr():
    s = twofa.new_secret()
    assert len(s) == 32 and twofa._key(s)
    uri = twofa.provisioning_uri(s, "ana")
    assert uri.startswith("otpauth://totp/GoldRetriever%3Aana?secret=" + s) and "issuer=GoldRetriever" in uri
    assert twofa.qr_png(uri)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def ana():
    users.create_user("ana", PW, "admin")
    return "ana"


def _enable(name="ana"):
    secret = twofa.new_secret()
    codes, err = users.enable_2fa(name, secret, _now_code(secret))
    assert err is None
    return secret, codes


def test_enable_needs_a_correct_code(ana):
    secret = twofa.new_secret()
    assert users.enable_2fa("ana", secret, "000000" if _now_code(secret) != "000000" else "111111") == (None, "bad_code")
    assert not users.has_2fa("ana")
    assert users.enable_2fa("nobody", secret, _now_code(secret)) == (None, "name")


def test_enable_signs_out_old_tokens(ana):
    old = users.make_token("ana")
    _enable()
    assert users.has_2fa("ana") and users.check_token(old) is None
    assert users.check_token(users.make_token("ana")) == "ana"


def test_totp_code_works_once(ana):
    secret, _ = _enable()
    code = _now_code(secret, 1)
    assert users.verify_2fa("ana", code) == "totp"
    assert users.verify_2fa("ana", code) is None
    assert users.verify_2fa("ana", "12345") is None


def test_recovery_codes_work_once_and_are_hashed(ana, tmp_path):
    _, codes = _enable()
    assert len(codes) == twofa.RECOVERY_COUNT == len(set(codes))
    raw = open(users.USERS_FILE).read()
    assert not any(c in raw or c.replace("-", "") in raw for c in codes)
    assert users.verify_2fa("ana", codes[0].upper()) == "recovery"
    assert users.verify_2fa("ana", codes[0]) is None
    assert users.recovery_left("ana") == twofa.RECOVERY_COUNT - 1
    new = users.new_recovery_codes("ana")
    assert users.verify_2fa("ana", codes[1]) is None and users.verify_2fa("ana", new[0]) == "recovery"


def test_disable_removes_everything_and_signs_out(ana):
    _enable()
    tok = users.make_token("ana")
    assert users.disable_2fa("ana") is None
    rec = json.load(open(users.USERS_FILE))["users"]["ana"]
    assert not set(rec) & set(users._TFA_KEYS)
    assert users.check_token(tok) is None and not users.has_2fa("ana")
    assert users.disable_2fa("nobody") == "name"


def test_records_show_2fa_flag(ana):
    users.create_user("bob", PW, "user")
    _enable("bob")
    assert {r["key"]: r["twofa"] for r in users.records()} == {"ana": False, "bob": True}


@pytest.mark.parametrize("policy,name,role,req", [
    ("optional", "ana", "admin", False), ("admins", "ana", "admin", True), ("admins", "bob", "user", False),
    ("all", "bob", "user", True), ("all", "demo", "user", False), ("all", None, None, False)])
def test_policy(policy, name, role, req):
    assert twofa.save_policy(policy) is None and twofa.policy() == policy
    assert twofa.required(name, role) is req


def test_bad_policy_is_rejected():
    assert twofa.save_policy("sometimes") == "policy" and twofa.policy() == "optional"


# --- autentificarea, cu AppTest ---

def _page():
    import auth
    import streamlit as st
    me = auth.require_login()
    st.write("in:" + me)


@pytest.fixture
def login_env(ana, monkeypatch):
    cookies = []
    monkeypatch.setattr(auth, "_cookie_js", lambda v, a: cookies.append(v))
    monkeypatch.setattr(auth, "_check_device", lambda me: None)
    monkeypatch.setattr(auth, "_read_cookie", lambda: None)
    monkeypatch.setattr(auth, "_client", lambda: ("UA", "203.0.113.7"))
    return cookies


def _signed_in(at):
    return any(m.value == "in:ana" for m in at.markdown)


def _password(at, pw=PW):
    at.text_input[0].input("ana")
    at.text_input[1].input(pw)
    return at.button[0].click().run()


def _code(at, code):
    at.text_input[0].input(code)
    return at.button[0].click().run()


def test_password_then_code(login_env, capsys):
    secret, _ = _enable()
    at = _password(AppTest.from_function(_page).run())
    assert not _signed_in(at) and not login_env
    assert "tfa_login_back" in [b.key for b in at.button]
    _code(at, "000000" if _now_code(secret) != "000000" else "111111")
    assert not _signed_in(at) and at.error and not login_env
    assert _code(at, _now_code(secret)).error  # acelasi pas ca la activare: cod deja folosit
    code = _now_code(secret, 1)
    _code(at, code)
    assert _signed_in(at) and login_env
    out = capsys.readouterr().out
    assert "[auth] 2fa required user=ana" in out and "[auth] 2fa failed user=ana" in out
    assert "[auth] login ok user=ana ip=203.0.113.7 via=password+totp" in out
    assert secret not in out and code not in out


def test_recovery_code_signs_in_and_alerts(login_env, monkeypatch, capsys):
    events = []
    monkeypatch.setattr(auth.alerts, "record_user_event", lambda *a: events.append(a))
    _, codes = _enable()
    at = _code(_password(AppTest.from_function(_page).run()), codes[3])
    assert _signed_in(at)
    assert events and events[-1][0] == "cod de rezerva 2FA folosit" and "9" in events[-1][3]
    out = capsys.readouterr().out
    assert codes[3] not in out and "via=password+recovery" in out


def test_wrong_codes_share_the_password_lockout(login_env):
    secret, _ = _enable()
    at = _password(AppTest.from_function(_page).run(), "wrong-" + PW)
    at = _password(at)
    for _ in range(auth._MAX_FAILS - 1):
        _code(at, "abc")
    assert auth._lock_remaining("ana") > 0
    _code(at, _now_code(secret))
    assert not _signed_in(at) and at.error


def test_second_step_expires(login_env, monkeypatch):
    _enable()
    at = _password(AppTest.from_function(_page).run())
    key, started = at.session_state["_pending_2fa"]
    at.session_state["_pending_2fa"] = (key, started - twofa.PENDING_SECONDS - 1)
    at.run()
    assert not _signed_in(at) and len(at.text_input) == 2  # din nou utilizator + parola
    assert any("expirat" in w.value or "expired" in w.value for w in at.warning)


def test_back_returns_to_password(login_env):
    _enable()
    at = _password(AppTest.from_function(_page).run())
    at.button(key="tfa_login_back").click().run()
    assert "_pending_2fa" not in at.session_state and len(at.text_input) == 2


def test_without_2fa_password_is_enough(login_env):
    assert _signed_in(_password(AppTest.from_function(_page).run()))


def test_policy_forces_enrollment(login_env):
    twofa.save_policy("admins")
    at = _password(AppTest.from_function(_page).run())
    assert not _signed_in(at) and "tfa_start" in [b.key for b in at.button]


# --- activarea din Setari ---

def _security():
    import streamlit as st
    import twofa_ui
    st.session_state["_user"] = "ana"
    twofa_ui.render_security("ana")


def test_enroll_from_settings(login_env, monkeypatch, capsys):
    events = []
    monkeypatch.setattr(auth.alerts, "record_user_event", lambda *a: events.append(a))
    at = AppTest.from_function(_security).run()
    at.button(key="tfa_start").click().run()
    secret = at.session_state["_tfa_secret"]
    assert at.get("imgs") or at.get("image")
    at.text_input[0].input(_now_code(secret))
    at.button[0].click().run()
    assert users.has_2fa("ana") and "_tfa_secret" not in at.session_state
    codes = at.session_state["_tfa_codes"]
    assert at.code[0].value == "\n".join(codes)
    assert at.session_state["_sess_ver"] == users.session_version("ana") and login_env  # cookie nou
    at.button(key="tfa_codes_ok").click().run()
    assert any("10" in s.value for s in at.success)
    assert events[-1][0] == "2FA activat"
    out = capsys.readouterr().out
    assert "[auth] 2fa enabled user=ana" in out and secret not in out


def test_disable_needs_password_and_code(login_env):
    secret, _ = _enable()
    at = AppTest.from_function(_security).run()
    assert len(at.text_input) == 4
    at.text_input[2].input("wrong")
    at.text_input[3].input(_now_code(secret))
    at.button[1].click().run()
    assert users.has_2fa("ana") and at.error
    at.text_input[2].input(PW)
    at.text_input[3].input(_now_code(secret, 1))
    at.button[1].click().run()
    assert not users.has_2fa("ana")


def test_disable_blocked_by_policy(login_env):
    _enable()
    twofa.save_policy("all")
    at = AppTest.from_function(_security).run()
    assert len(at.text_input) == 2  # doar formularul pentru coduri noi


def _users_page():
    import auth
    auth.render_users_page("ana", embedded=True)


def test_admin_resets_2fa_of_another_user(login_env, monkeypatch, capsys):
    events = []
    monkeypatch.setattr(auth.alerts, "record_user_event", lambda *a: events.append(a))
    users.create_user("bob", PW, "user")
    _enable("bob")
    tok = users.make_token("bob")
    at = AppTest.from_function(_users_page).run()
    assert at.selectbox(key="adm_tfa_user").options == ["bob"]
    at.button(key="adm_tfa_reset").click().run()
    assert not users.has_2fa("bob") and users.check_token(tok) is None
    assert events[-1][:3] == ("2FA resetat", "ana", "bob")
    assert "[auth] 2fa reset user=bob ip=203.0.113.7 by=ana" in capsys.readouterr().out


def test_admin_sets_policy(login_env, monkeypatch):
    monkeypatch.setattr(auth.alerts, "record_user_event", lambda *a: None)
    at = AppTest.from_function(_users_page).run()
    at.radio[0].set_value("admins")
    form_btns = [b for b in at.button if "tfa_policy_form" in str(b.form_id)]
    form_btns[0].click().run()
    assert twofa.policy() == "admins"
