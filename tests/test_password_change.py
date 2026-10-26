import pytest

import auth
import users


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(auth.alerts, "record_user_event", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(auth.alerts, "record_lockout", lambda *a, **k: sent.append(("lockout",) + a))
    users.create_user("ana", "ana-old-pass", "admin")
    users.create_user("bob", "bob-old-pass")
    return sent


def test_wrong_current_password_is_rejected(events):
    assert auth.change_own_password("ana", "wrong-pass", "ana-new-pass", "ana-new-pass") == "bad_current"
    assert users.verify("ana", "ana-old-pass")
    assert events == []


def test_too_short_new_password_is_rejected(events):
    assert auth.change_own_password("ana", "ana-old-pass", "short", "short") == "pwd_short"
    assert users.verify("ana", "ana-old-pass")
    assert events == []


def test_confirmation_must_match(events):
    assert auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pas") == "mismatch"
    assert users.verify("ana", "ana-old-pass")


def test_change_succeeds_and_records_event_without_password(events):
    assert auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pass") is None
    assert users.verify("ana", "ana-new-pass")
    assert not users.verify("ana", "ana-old-pass")
    assert events == [("parola schimbata de utilizator", "ana", "ana")]
    assert not any("pass" in str(x) for e in events for x in e)


def test_old_token_is_invalidated(events):
    tok = users.make_token("ana")
    assert users.check_token(tok) == "ana"
    auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pass")
    assert users.check_token(tok) is None


def test_cannot_change_another_users_password(events):
    # ana din sesiune, cu parola lui bob: se verifica doar contul ana, bob ramane neatins
    assert auth.change_own_password("ana", "bob-old-pass", "hijacked-pass", "hijacked-pass") == "bad_current"
    assert users.verify("bob", "bob-old-pass")
    assert not users.verify("bob", "hijacked-pass")
    assert auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pass") is None
    assert users.verify("bob", "bob-old-pass")


def test_lockout_after_too_many_attempts(events):
    for _ in range(auth._MAX_FAILS):
        assert auth.change_own_password("ana", "guess", "ana-new-pass", "ana-new-pass") == "bad_current"
    assert ("lockout", "ana", True, auth._MAX_FAILS, auth._LOCK_SECONDS) in events
    # blocat chiar si cu parola corecta, iar contorul e comun cu login-ul
    assert auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pass") == "locked"
    assert auth._lock_remaining("ana") > 0
    assert users.verify("ana", "ana-old-pass")
    assert auth._lock_remaining("bob") == 0


def test_success_resets_fail_counter(events):
    for _ in range(auth._MAX_FAILS - 1):
        auth.change_own_password("ana", "guess", "ana-new-pass", "ana-new-pass")
    assert auth.change_own_password("ana", "ana-old-pass", "ana-new-pass", "ana-new-pass") is None
    assert auth.change_own_password("ana", "guess", "x-new-pass1", "x-new-pass1") == "bad_current"
    assert auth._lock_remaining("ana") == 0


def test_must_change_flag_set_by_admin_and_cleared_by_user(events):
    users.create_user("cara", "temp-pass-1", must_change=True)
    assert users.must_change("cara")
    assert auth.change_own_password("cara", "temp-pass-1", "cara-own-pass", "cara-own-pass") is None
    assert not users.must_change("cara")
    users.set_password("cara", "temp-pass-2", must_change=True)
    assert users.must_change("cara")
    users.set_password("cara", "temp-pass-3")
    assert not users.must_change("cara")
    assert not users.must_change("ana")
