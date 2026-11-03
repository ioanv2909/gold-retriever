import asyncio
import json
import os

import pytest
from streamlit.testing.v1 import AppTest

import auth
import known_devices
import tsauth
import users

PW = "ana-secret-pass-42"


def _scope(path, headers=(), kind="http"):
    return {"type": kind, "path": path, "raw_path": path.encode(), "headers": [(k.encode(), v.encode()) for k, v in headers],
            "client": ("172.29.0.1", 5000), "scheme": "http"}


def _h(scope):
    return {k.decode(): v.decode() for k, v in scope["headers"]}


@pytest.fixture
def secret():
    return tsauth.secret(create=True)


def test_secret_is_created_once_and_private(secret):
    assert len(secret) >= 24 and tsauth.secret() == secret
    assert oct(os.stat(tsauth.SECRET_FILE).st_mode & 0o777) == "0o600"
    assert tsauth.serve_command() == ("docker exec tailscale tailscale serve --bg --https=8443 "
                                      "http://127.0.0.1:8501/ts-" + secret)


def test_request_through_serve_is_marked_and_unprefixed(secret):
    hdr = [("host", "127.0.0.1:8501"), ("x-forwarded-host", "casaos.tail.ts.net:8443"),
           ("x-forwarded-for", "100.64.0.5"), ("tailscale-user-login", "Ana@Example.com"),
           ("tailscale-user-name", "Ana")]
    out = tsauth.rewrite(_scope("/ts-%s/_stcore/stream" % secret, hdr, "websocket"))
    h = _h(out)
    assert out["path"] == "/_stcore/stream" and out["raw_path"] == b"/_stcore/stream"
    assert h["host"] == "casaos.tail.ts.net:8443" and out["client"] == ("100.64.0.5", 0)
    assert out["scheme"] == "wss" and "x-forwarded-for" not in h
    assert tsauth.identity({"Tailscale-User-Login": h["tailscale-user-login"], "x-goldretriever-ts": h["x-goldretriever-ts"]}) \
        == ("ana@example.com", None)
    root = tsauth.rewrite(_scope("/ts-" + secret, hdr))
    assert root["path"] == "/"


def test_direct_requests_cannot_claim_an_identity(secret):
    spoof = [("tailscale-user-login", "ana@example.com"), ("x-goldretriever-ts", "anything"), ("host", "192.168.68.4:8501")]
    for path in ("/", "/_stcore/stream", "/ts-wrong/", "/ts-%sX/" % secret, "/x/ts-%s/" % secret):
        out = tsauth.rewrite(_scope(path, spoof))
        h = _h(out)
        assert out["path"] == path
        assert "tailscale-user-login" not in h and "x-goldretriever-ts" not in h and h["host"] == "192.168.68.4:8501"
    assert tsauth.identity({"Tailscale-User-Login": "ana@example.com", "x-goldretriever-ts": "anything"}) == (None, None)


def test_without_secret_nothing_is_trusted():
    out = tsauth.rewrite(_scope("/ts-abc/", [("tailscale-user-login", "a@b.c")]))
    assert out["path"] == "/ts-abc/" and "tailscale-user-login" not in _h(out)


def test_middleware_passes_lifespan_and_rewrites_http(secret):
    seen = []

    async def app(scope, receive, send):
        seen.append(scope)

    mw = tsauth.Middleware(app)
    asyncio.run(mw({"type": "lifespan"}, None, None))
    asyncio.run(mw(_scope("/ts-%s/x" % secret), None, None))
    assert seen[0] == {"type": "lifespan"} and seen[1]["path"] == "/x"


def test_server_entry_point_wraps_app_py():
    src = open(os.path.join(os.path.dirname(tsauth.__file__), "server.py"), encoding="utf-8").read()
    assert 'st.App("app.py"' in src and "tsauth.Middleware" in src
    docker = open(os.path.join(os.path.dirname(tsauth.__file__), "Dockerfile"), encoding="utf-8").read()
    assert '"streamlit", "run", "server.py"' in docker


# --- conturi ---

@pytest.fixture
def ana():
    users.create_user("ana", PW, "admin")
    return "ana"


def test_ts_login_is_unique_and_case_insensitive(ana):
    users.create_user("bob", PW)
    assert users.set_ts_login("ana", "Ana@Example.com") is None
    assert users.by_ts_login("ANA@example.com") == "ana" and users.ts_login("ana") == "ana@example.com"
    assert users.set_ts_login("bob", "ana@example.com") == "ts_taken"
    assert users.set_ts_login("ana", "") is None and users.by_ts_login("ana@example.com") is None
    assert users.set_ts_login("nobody", "x@y.z") == "name"


def test_rename_keeps_everything_and_ends_sessions(ana, tmp_path):
    users.set_ts_login("ana", "ana@example.com")
    users.set_email("ana", "ana@example.com")
    folder = tmp_path / "users" / "ana"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{}")
    known_devices.check_login("ana", "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0")
    tok = users.make_token("ana")
    key, err = users.rename_user("ana", "Ioanv")
    assert (key, err) == ("ioanv", None)
    assert not users.exists("ana") and users.role("ioanv") == "admin" and users.verify("ioanv", PW)
    assert users.by_ts_login("ana@example.com") == "ioanv" and users.email("ioanv") == "ana@example.com"
    assert (tmp_path / "users" / "ioanv" / "config.json").exists() and not folder.exists()
    assert users.check_token(tok) is None  # cookie-urile vechi nu mai sunt valide
    devices = json.loads(open(known_devices.DEVICES_FILE).read())
    assert "ioanv" in devices and "ana" not in devices
    assert next(r["name"] for r in users.records() if r["key"] == "ioanv") == "Ioanv"


def test_rename_errors(ana, tmp_path):
    users.create_user("bob", PW)
    assert users.rename_user("ana", "bob") == (None, "exists")
    assert users.rename_user("ana", "x") == (None, "name")
    assert users.rename_user("nobody", "zed") == (None, "name")
    (tmp_path / "users" / "zed").mkdir(parents=True)
    assert users.rename_user("ana", "zed") == (None, "dir_exists")
    assert users.exists("ana")


def test_scheduler_restarts_when_its_thread_stopped(monkeypatch):
    import threading

    import background
    started = []

    def fake(user):
        th = threading.Thread(target=lambda: None)
        th.start()
        th.join()
        started.append(user)
        return th

    monkeypatch.setattr(background, "_start_scheduler", fake)
    monkeypatch.setattr(background, "_schedulers", {})
    background.start_background_scheduler("zed")
    background.start_background_scheduler("zed")
    assert started == ["zed", "zed"]  # firul oprit (cont sters/redenumit) nu blocheaza un fir nou


# --- autentificarea, cu AppTest ---

def _page():
    import auth
    import streamlit as st
    me = auth.require_login()
    st.write("in:" + me)


@pytest.fixture
def ts_env(ana, monkeypatch):
    cookies = []
    monkeypatch.setattr(auth, "_cookie_js", lambda v, a: cookies.append(v))
    monkeypatch.setattr(auth, "_check_device", lambda me: None)
    monkeypatch.setattr(auth, "_read_cookie", lambda: None)
    monkeypatch.setattr(auth, "_client", lambda: ("UA", "100.64.0.5"))
    monkeypatch.setattr(auth, "_run_js", lambda js: None)
    state = {"login": "ana@example.com", "paused": False}
    monkeypatch.setattr(tsauth, "identity", lambda headers=None: (state["login"], "Ana"))
    monkeypatch.setattr(tsauth, "via_tailscale", lambda headers=None: True)
    monkeypatch.setattr(auth, "_ts_paused", lambda: state["paused"])
    return state


def test_linked_tailscale_login_signs_in_without_password(ts_env, capsys):
    users.set_ts_login("ana", "ana@example.com")
    at = AppTest.from_function(_page).run()
    assert any(m.value == "in:ana" for m in at.markdown)
    assert "[auth] login ok user=ana ip=100.64.0.5 via=tailscale ts=ana@example.com" in capsys.readouterr().out


def test_unlinked_or_paused_tailscale_login_asks_for_password(ts_env):
    at = AppTest.from_function(_page).run()
    assert not any(m.value.startswith("in:") for m in at.markdown)
    assert any("ana@example.com" in c.value for c in at.caption)
    users.set_ts_login("ana", "ana@example.com")
    ts_env["paused"] = True
    at = AppTest.from_function(_page).run()
    assert not any(m.value.startswith("in:") for m in at.markdown)
