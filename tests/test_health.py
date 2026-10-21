import json

import pytest

import health
import notify
import yf_compat


def test_no_events_is_gray():
    assert health.status("yahoo")["level"] == "gray"


def test_levels_green_yellow_red():
    health.record("yahoo", True, 0.2, now=1000.0)
    assert health.status("yahoo", now=1001.0)["level"] == "green"

    health.record("yahoo", False, 0.1, "HTTP 500", now=1010.0)
    health.record("yahoo", True, 0.3, now=1020.0)
    s = health.status("yahoo", now=1030.0)
    assert s["level"] == "yellow" and s["fail_1h"] == 1 and s["n_1h"] == 3 and s["error"] == "HTTP 500"
    assert s["avg_ms_1h"] == pytest.approx(200.0)

    # ultima cerere a esuat, dar a mers acum 5 minute: inca galben
    health.record("yahoo", False, error="HTTP 401", now=1300.0)
    assert health.status("yahoo", now=1320.0)["level"] == "yellow"
    # nimic reusit de peste 15 minute: rosu
    assert health.status("yahoo", now=1020.0 + health.RED_AFTER + 1)["level"] == "red"
    # dupa o ora fara erori: verde din nou
    health.record("yahoo", True, now=5000.0)
    assert health.status("yahoo", now=5001.0)["level"] == "green"


def test_unknown_source_is_ignored():
    health.record("nope", False)
    assert "nope" not in health.SOURCES


def test_timed_records_success_and_exception():
    with health.timed("smtp"):
        pass
    with pytest.raises(ValueError):
        with health.timed("smtp"):
            raise ValueError("boom")
    s = health.status("smtp")
    assert s["n_1h"] == 2 and s["fail_1h"] == 1 and "ValueError: boom" in s["error"]


def test_history_survives_a_restart(monkeypatch):
    health.record("justetf", True, 0.5, now=1000.0)
    health.record("justetf", False, error="timeout", now=1001.0)
    health.save(now=1002.0)
    saved = json.load(open(health.HEALTH_FILE))
    assert len(saved["events"]["justetf"]) == 2
    # proces nou: stare goala, se incarca din fisier la prima folosire
    import collections
    monkeypatch.setattr(health, "_events", {s: collections.deque(maxlen=health.KEEP) for s in health.SOURCES})
    monkeypatch.setattr(health, "_last", {s: {"ok": None, "fail": None, "error": None} for s in health.SOURCES})
    monkeypatch.setattr(health, "_saved", {"at": 0.0, "loaded": False})
    s = health.status("justetf", now=1003.0)
    assert s["n_1h"] == 2 and s["error"] == "timeout" and s["last_ok"] == 1000.0


@pytest.mark.parametrize("raw, eff, mtime, now, expected", [
    ({}, {}, None, 1000, ("gray", "never")),
    ({"in_progress": True}, {"in_progress": True}, 900, 1000, ("green", "running")),
    ({"in_progress": True}, {"in_progress": False, "stale": True}, 900, 1000, ("red", "stuck")),
    ({"in_progress": False}, {"in_progress": False}, 1000, 1000 + 2 * 3600, ("green", "fresh")),
    ({"in_progress": False}, {"in_progress": False}, 1000, 1000 + 3 * 3600, ("yellow", "old")),
])
def test_job_level(raw, eff, mtime, now, expected):
    assert health.job_level(raw, eff, mtime, 3600, now=now) == expected


def test_yahoo_requests_are_measured():
    class Resp:
        def __init__(self, code):
            self.status_code = code

    class FakeData:
        codes = [200, 404, 500]

        def _make_request(self, url, *a, **kw):
            code = self.codes.pop(0)
            if code == 500:
                raise ConnectionError("reset")
            return Resp(code)

    yf_compat.install_health(FakeData, health.record)
    d = FakeData()
    d._make_request("https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL?x=1")
    d._make_request("https://query2.finance.yahoo.com/v10/finance/quoteSummary/NOPE")
    with pytest.raises(ConnectionError):
        d._make_request("u")
    s = health.status("yahoo")
    assert s["n_1h"] == 3 and s["fail_1h"] == 1 and "ConnectionError: reset" in s["error"]


class FakeSMTP:
    calls = []

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.calls.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.calls.append("starttls")

    def login(self, user, pwd):
        FakeSMTP.calls.append("login")

    def noop(self):
        FakeSMTP.calls.append("noop")

    def send_message(self, msg):
        raise AssertionError("check_connection must not send")


def test_smtp_check_connects_without_sending(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "MAIL_FILE", str(tmp_path / "mail.json"))
    monkeypatch.setattr(notify, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.calls = []
    assert notify.check_connection()[0] is False  # neconfigurat
    notify.save_settings({"host": "smtp.example.com", "port": 587, "security": "starttls", "user": "u",
                          "password": "p", "sender": "s@example.com"})
    ok, msg = notify.check_connection()
    assert ok and msg == "smtp.example.com:587"
    assert FakeSMTP.calls == [("connect", "smtp.example.com", 587), "starttls", "login", "noop"]
    assert health.status("smtp")["level"] == "green"


def test_sec_probe_needs_an_admin_email(monkeypatch):
    import signals
    monkeypatch.setattr(signals, "ua_email", lambda: None)
    assert health.probe_sec()[0] is None
