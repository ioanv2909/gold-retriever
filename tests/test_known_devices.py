import json

import pytest

import known_devices as kd

CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
CHROME_WIN_NEWER = CHROME_WIN.replace("Chrome/130", "Chrome/131")
FIREFOX_ANDROID = "Mozilla/5.0 (Android 14; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0"


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(kd.alerts, "record_user_event", lambda *a, **k: out.append(a))
    return out


def test_first_login_of_account_does_not_alert(sent):
    assert kd.check_login("ana", CHROME_WIN, "203.0.113.7", now=1000) == "first"
    assert sent == []


def test_same_device_does_not_alert_even_after_browser_update(sent):
    kd.check_login("ana", CHROME_WIN, now=1000)
    assert kd.check_login("ana", CHROME_WIN, now=2000) == "known"
    assert kd.check_login("Ana", CHROME_WIN_NEWER, now=3000) == "known"
    assert sent == []


def test_new_device_alerts_without_secrets(sent):
    kd.check_login("ana", CHROME_WIN, now=1000)
    assert kd.check_login("ana", FIREFOX_ANDROID, "203.0.113.7", now=2000) == "new"
    assert len(sent) == 1
    action, actor, target, detail = sent[0]
    assert (action, actor, target) == ("autentificare de pe dispozitiv nou", "ana", "ana")
    assert "Firefox / Android" in detail and "203.0.x.x" in detail and "203.0.113.7" not in detail


def test_devices_are_per_user(sent):
    kd.check_login("ana", CHROME_WIN, now=1000)
    assert kd.check_login("bob", FIREFOX_ANDROID, now=1000) == "first"
    assert sent == []


def test_list_is_capped_and_oldest_is_dropped(sent, monkeypatch):
    monkeypatch.setattr(kd, "MAX_ALERTS_PER_HOUR", 1000)
    for i in range(15):
        kd.check_login("ana", "UnknownAgent/%d" % i, now=1000 + i)
    data = json.load(open(kd.DEVICES_FILE))
    assert len(data["ana"]) == kd.MAX_DEVICES
    # cel mai vechi a iesit din lista: revine ca dispozitiv nou
    assert kd.check_login("ana", "UnknownAgent/0", now=5000) == "new"
    assert kd.check_login("ana", "UnknownAgent/14", now=5001) == "known"


def test_alerts_are_rate_limited_per_hour(sent):
    kd.check_login("ana", "Agent/first", now=0)
    for i in range(6):
        assert kd.check_login("ana", "Agent/%d" % i, now=100 + i) == "new"
    assert len(sent) == kd.MAX_ALERTS_PER_HOUR
    kd.check_login("ana", "Agent/later", now=100 + 3601)
    assert len(sent) == kd.MAX_ALERTS_PER_HOUR + 1


def test_nothing_sensitive_on_disk(sent):
    kd.check_login("ana", CHROME_WIN, "203.0.113.7", now=1000)
    kd.check_login("ana", FIREFOX_ANDROID, "2001:db8:1234:5678::1", now=2000)
    raw = open(kd.DEVICES_FILE).read()
    assert "203.0" not in raw and "2001" not in raw
    assert "Mozilla" not in raw and "AppleWebKit" not in raw


@pytest.mark.parametrize("ip,out", [("192.168.1.20", "192.168.x.x"), ("2001:db8:1234:5678::1", "2001:0db8:1234::/48"),
                                    ("", "?"), ("not-an-ip", "?")])
def test_short_ip(ip, out):
    assert kd.short_ip(ip) == out
