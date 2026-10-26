import json
import time

import pytest

import auth
import session_policy as sp
import users

H = 3600
D = 86400


@pytest.fixture
def ana(monkeypatch):
    users.create_user("ana", "ana-old-pass", "admin")
    return "ana"


def test_defaults_without_setting():
    assert sp.limits() == (sp.DEFAULT_IDLE_HOURS, sp.DEFAULT_MAX_DAYS) == (8, 30)


def test_admin_setting_is_saved_and_read():
    assert sp.save_limits(2, 7) is None
    assert sp.limits() == (2, 7)
    sp.reset_limits()
    assert sp.limits() == (8, 30)


@pytest.mark.parametrize("idle,days,err", [(0, 30, "idle"), (721, 30, "idle"), (8, 0, "days"), (8, 366, "days"),
                                           ("8", 30, "idle"), (8, 1.5, "days"), (True, 30, "idle")])
def test_out_of_range_setting_rejected(idle, days, err):
    assert sp.save_limits(idle, days) == err
    assert sp.limits() == (8, 30)


def test_corrupt_setting_falls_back_to_defaults():
    with open(sp.POLICY_FILE, "w") as f:
        f.write("{not json")
    assert sp.limits() == (8, 30)
    with open(sp.POLICY_FILE, "w") as f:
        json.dump({"idle_hours": -3, "max_days": "x"}, f)
    assert sp.limits() == (8, 30)


def test_token_within_limit_is_valid(ana):
    now = time.time()
    tok = users.make_token("ana", now=now)
    assert users.token_exp(tok) == int(now + 30 * D)
    assert users.check_token(tok, now=now + 29 * D) == "ana"


def test_expired_token_is_rejected(ana):
    now = time.time()
    tok = users.make_token("ana", now=now)
    assert users.check_token(tok, now=now + 30 * D + 1) is None


def test_lower_limit_applies_to_existing_tokens(ana):
    now = time.time()
    tok = users.make_token("ana", now=now)
    sp.save_limits(8, 7)
    assert users.check_token(tok, now=now) is None
    assert users.check_token(users.make_token("ana", now=now), now=now + 6 * D) == "ana"


def test_higher_limit_does_not_extend_existing_tokens(ana):
    now = time.time()
    sp.save_limits(8, 7)
    tok = users.make_token("ana", now=now)
    sp.save_limits(8, 30)
    assert users.check_token(tok, now=now + 8 * D) is None


def test_idle_rule():
    now = 1_000_000.0
    assert not sp.is_idle(now - 8 * H + 60, now)
    assert sp.is_idle(now - 8 * H - 1, now)
    assert not sp.is_idle(None, now)  # cookie emis inainte de registru: nimeni nu iese la deploy
    sp.save_limits(1, 30)
    assert sp.is_idle(now - H - 1, now)


def test_activity_registry_without_token_on_disk(ana):
    tok = users.make_token("ana")
    tid = sp.token_id(tok)
    assert sp.last_activity(tid) is None
    assert sp.touch(tid, 1000.0 + 30 * D)
    assert sp.last_activity(tid) == 1000.0 + 30 * D
    raw = open(sp.ACTIVITY_FILE).read()
    assert tok.rsplit(".", 1)[-1] not in raw and "ana" not in raw


def test_activity_writes_are_throttled_and_pruned():
    now = time.time()
    assert sp.touch("old", now - 31 * D)
    assert sp.touch("a", now)
    assert not sp.touch("a", now + 60)
    assert sp.last_activity("a") == now
    assert sp.touch("a", now + sp.WRITE_EVERY + 1)
    assert sp.last_activity("old") is None  # mai vechi decat durata maxima: sters


def test_revoked_cookie_stays_idle():
    now = time.time()
    sp.touch("a", now)
    sp.revoke("a", now)
    assert sp.is_idle(sp.last_activity("a"), now)
    sp.touch("a", now + D, force=True)
    assert sp.is_idle(sp.last_activity("a"), now + D)


@pytest.fixture
def session(monkeypatch):
    state = {}
    monkeypatch.setattr(auth.st, "session_state", state)
    return state


def test_open_session_expires_on_inactivity(session):
    now = time.time()
    session.update(_auth_exp=int(now + 30 * D), _last_active=now)
    assert not auth._session_expired(now + 8 * H - 60)
    assert auth._session_expired(now + 8 * H + 1)


def test_open_session_expires_at_absolute_limit(session):
    now = time.time()
    session.update(_auth_exp=int(now + 30 * D), _last_active=now + 30 * D)
    assert not auth._session_expired(now + 30 * D - 60)
    assert auth._session_expired(now + 30 * D + 1)


def test_automatic_rerun_is_not_activity(session):
    session.update(_last_active=123.0, _tok_id="a", _auto_rerun=True)
    auth._mark_activity()
    assert session["_last_active"] == 123.0 and "_auto_rerun" not in session
    auth._mark_activity()
    assert session["_last_active"] > 123.0
