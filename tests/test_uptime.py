import http.server
import json
import threading

import pytest

import notify
import uptime


def test_alert_after_two_failures_then_recovery_once():
    s, msg = uptime.step({}, True, "HTTP 200 ok", 1000.0)
    assert msg is None and s["fails"] == 0 and s["last_ok"] == 1000.0

    s, msg = uptime.step(s, False, "ConnectionRefusedError", 1300.0)
    assert msg is None and s["fails"] == 1 and s["down_since"] == 1300.0

    s, msg = uptime.step(s, False, "ConnectionRefusedError", 1600.0)
    assert msg[0] == "Aplicația nu răspunde" and "de 2 ori" in msg[1] and s["alerted"] is True

    s, msg = uptime.step(s, False, "timeout", 1900.0)
    assert msg is None and s["fails"] == 3  # o singura alerta pe toata perioada

    s, msg = uptime.step(s, True, "HTTP 200 ok", 2200.0)
    assert msg[0] == "Aplicația răspunde din nou" and "15 minute" in msg[1]
    assert s["fails"] == 0 and s["alerted"] is False and s["down_since"] is None


def test_single_failure_recovered_sends_nothing():
    s, _ = uptime.step({}, False, "blip", 1.0)
    s, msg = uptime.step(s, True, "ok", 2.0)
    assert msg is None


@pytest.fixture
def server():
    class H(http.server.BaseHTTPRequestHandler):
        body = b"ok"

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(H.body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/_stcore/health" % srv.server_port, H
    srv.shutdown()


def test_check_real_http(server):
    url, handler = server
    ok, detail = uptime.check(url)
    assert ok and detail.startswith("HTTP 200 ok")
    handler.body = b"starting"
    assert uptime.check(url)[0] is False
    ok, detail = uptime.check("http://127.0.0.1:1/_stcore/health", timeout=2)
    assert not ok and "Error" in detail


def test_run_writes_state_and_mails_on_transition(tmp_path, monkeypatch):
    monkeypatch.setattr(uptime, "STATUS_FILE", str(tmp_path / "uptime_status.json"))
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *a, **kw: sent.append(a) or True)
    results = iter([(False, "down"), (False, "down"), (True, "HTTP 200 ok")])
    monkeypatch.setattr(uptime, "check", lambda: next(results))
    assert uptime.run(now=1.0) == 1 and sent == []
    assert uptime.run(now=301.0) == 1 and sent[0][0] == "uptime"
    assert uptime.run(now=601.0) == 0 and len(sent) == 2
    assert json.load(open(uptime.STATUS_FILE))["last_ok_check"] is True
