import json

import presence
import presence_ui
import users

T0 = 1_800_000_000.0
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _file():
    with open(presence.PRESENCE_FILE, encoding="utf-8") as f:
        return json.load(f)["sessions"]


def test_touch_creates_and_updates_record():
    assert presence.touch("s1", "Ana", UA, "10.0.0.5", now=T0)
    rec = _file()["s1"]
    assert rec == {"user": "ana", "first": T0, "last": T0, "ua": UA, "ip": "10.0.0.5"}
    assert presence.touch("s1", "ana", UA, "10.0.0.6", now=T0 + 60)
    rec = _file()["s1"]
    assert rec["first"] == T0 and rec["last"] == T0 + 60 and rec["ip"] == "10.0.0.6"


def test_writes_are_throttled_per_session():
    assert presence.touch("s1", "ana", now=T0)
    assert not presence.touch("s1", "ana", now=T0 + 10)
    assert _file()["s1"]["last"] == T0
    assert presence.touch("s2", "ana", now=T0 + 10)  # alta sesiune, alt contor
    assert presence.touch("s1", "ana", now=T0 + presence.WRITE_EVERY)
    assert _file()["s1"]["last"] == T0 + presence.WRITE_EVERY


def test_user_change_on_same_session_writes_immediately():
    presence.touch("s1", "ana", now=T0)
    assert presence.touch("s1", "bob", now=T0 + 5)
    rec = _file()["s1"]
    assert rec["user"] == "bob" and rec["first"] == T0 + 5


def test_old_records_are_pruned():
    presence.touch("old", "ana", now=T0)
    presence.touch("new", "bob", now=T0 + presence.KEEP + 1)
    assert set(_file()) == {"new"}


def test_unauthenticated_sessions_are_not_recorded():
    assert not presence.touch("s1", None, UA, "1.2.3.4", now=T0)
    assert not presence.touch("s2", "", now=T0)
    assert presence.sessions(now=T0) == {}


def test_online_groups_by_user_and_sorts_by_last_activity():
    presence.touch("a1", "ana", UA, "1.1.1.1", now=T0)
    presence.touch("a2", "ana", "Firefox/120 (Linux)", "2.2.2.2", now=T0 + 100)
    presence.touch("b1", "bob", now=T0 + 200)
    presence.touch("gone", "cid", now=T0 - presence.ONLINE_WINDOW - 1)
    rows = presence.online(now=T0 + 200)
    assert [r["user"] for r in rows] == ["bob", "ana"]
    ana = rows[1]
    assert ana["sessions"] == 2 and ana["first"] == T0 and ana["last"] == T0 + 100 and ana["ip"] == "2.2.2.2"


def test_forget_session_and_user():
    presence.touch("a1", "ana", now=T0)
    presence.touch("a2", "ana", now=T0)
    presence.touch("b1", "bob", now=T0)
    presence.forget_session("b1")
    assert set(presence.sessions(now=T0)) == {"a1", "a2"}
    presence.forget_user("ana")
    assert presence.sessions(now=T0) == {}
    assert presence.touch("a1", "ana", now=T0 + 1)  # limitarea s-a resetat


def test_device_label():
    assert presence.device(UA) == "Chrome / Windows"
    assert presence.device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Version/17.0 Mobile Safari/604.1") == "Safari / iOS"
    assert presence.device("") == "?"


def test_nothing_secret_is_stored():
    presence.touch("s1", "ana", UA, "1.2.3.4", now=T0)
    assert set(_file()["s1"]) == {"user", "first", "last", "ua", "ip"}


def test_admin_sees_rows_and_non_admin_does_not(monkeypatch):
    users.create_user("ana", "ana-pass-123", "admin")
    users.create_user("bob", "bob-pass-123")
    monkeypatch.setattr(presence_ui, "t", lambda key, **kw: key)
    presence.touch("b1", "bob", UA, "1.2.3.4")
    presence.touch("x1", "deleted-user")
    data = presence_ui.rows("ana")
    assert [r["pres.col.user"] for r in data] == ["bob"]
    assert data[0]["pres.col.role"] == "user" and data[0]["pres.col.device"] == "Chrome / Windows"
    assert presence_ui.rows("bob") is None

    shown = []
    monkeypatch.setattr(presence_ui.st, "dataframe", lambda *a, **k: shown.append(a))
    monkeypatch.setattr(presence_ui.st, "button", lambda *a, **k: shown.append(a))
    presence_ui.render_online("bob")
    assert shown == []


def test_bump_session_invalidates_tokens():
    users.create_user("ana", "ana-pass-123", "admin")
    tok = users.make_token("ana")
    assert users.session_version("ana") == 0
    assert users.check_token(tok) == "ana"  # fara versiune, token-urile existente raman valide
    assert users.bump_session("ana") is None
    assert users.session_version("ana") == 1
    assert users.check_token(tok) is None
    assert users.check_token(users.make_token("ana")) == "ana"
    assert users.bump_session("nobody") == "name"
