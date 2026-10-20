import json
import os

import pytest

import notify


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls, self.messages = [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, pwd):
        self.calls.append(("login", user, pwd))

    def send_message(self, msg):
        self.messages.append(msg)


class BoomSMTP(FakeSMTP):
    def send_message(self, msg):
        raise RuntimeError("server unavailable")


USERS = {"users": {
    "admin": {"role": "admin", "email": "a@example.com"},
    "boss": {"role": "admin", "email": "b@example.com"},
    "noemail": {"role": "admin"},
    "bob": {"role": "user", "email": "bob@example.com"},
}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "MAIL_FILE", str(tmp_path / "mail.json"))
    monkeypatch.setattr(notify, "STATE_FILE", str(tmp_path / "notify_state.json"))
    monkeypatch.setattr(notify, "USERS_FILE", str(tmp_path / "users.json"))
    FakeSMTP.instances = []
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    (tmp_path / "users.json").write_text(json.dumps(USERS))
    notify.save_settings({
        "host": "smtp.example.com", "port": 587, "security": "starttls", "user": "u",
        "password": "p", "sender": "s@example.com", "events": ["backup", "refresh"], "min_interval_h": 6,
    })
    return tmp_path


def test_recipients_are_admins_with_email(env):
    assert notify.recipients() == ["a@example.com", "b@example.com"]


def test_notify_sends_to_all_admins(env):
    assert notify.notify("backup", "Backup failed", "details", sync=True) is True
    smtp = FakeSMTP.instances[0]
    assert smtp.calls == ["starttls", ("login", "u", "p")]
    msg = smtp.messages[0]
    assert msg["Subject"] == "[GoldRetriever] Backup failed"
    assert "a@example.com" in msg["To"] and "b@example.com" in msg["To"]
    assert "bob@example.com" not in msg["To"]


def test_disabled_event_is_not_sent(env):
    assert notify.notify("security", "x", "y", sync=True) is False
    assert FakeSMTP.instances == []


def test_same_alert_is_throttled(env):
    assert notify.notify("backup", "s", "b", key="k1", sync=True) is True
    assert notify.notify("backup", "s", "b", key="k1", sync=True) is False
    assert notify.notify("backup", "s", "b", key="k2", sync=True) is True
    assert len(FakeSMTP.instances) == 2


def test_not_configured_or_no_recipients(env):
    notify.save_settings({"host": ""})
    assert notify.notify("backup", "s", "b", sync=True) is False
    notify.save_settings({"host": "smtp.example.com"})
    (env / "users.json").write_text(json.dumps({"users": {"admin": {"role": "admin"}}}))
    assert notify.notify("backup", "s", "b", sync=True) is False
    assert FakeSMTP.instances == []


def test_send_failure_is_recorded(env, monkeypatch):
    monkeypatch.setattr(notify.smtplib, "SMTP", BoomSMTP)
    assert notify.notify("backup", "s", "b", sync=True) is False
    assert "server unavailable" in notify.last_state()["last_error"]


def test_test_email_ignores_event_toggles(env):
    notify.save_settings({"events": []})
    ok, info = notify.send_test()
    assert ok is True and "a@example.com" in info


def test_save_settings_cleans_values(env):
    cfg = notify.save_settings({"port": "2525", "events": ["backup", "bogus"], "security": "weird"})
    assert cfg["port"] == 2525
    assert cfg["events"] == ["backup"]
    assert cfg["security"] == "starttls"
    assert os.stat(notify.MAIL_FILE).st_mode & 0o777 == 0o600


def test_min_hours_overrides_default(env):
    assert notify.notify("backup", "s", "b", key="k", sync=True, min_hours=0) is True
    assert notify.notify("backup", "s", "b", key="k", sync=True, min_hours=0) is True
