import json
import time

import pytest

import alerts


@pytest.fixture
def calls(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_FAILS", {})
    monkeypatch.setattr(alerts.notify, "notify", lambda *a, **k: sent.append((a, k)) or True)
    return sent


def test_refresh_alerts_only_after_threshold(calls):
    err = {"cash": "HTTP 500"}
    assert alerts.record_refresh("Trading 212", "admin", err) is False
    assert alerts.record_refresh("Trading 212", "admin", err) is False
    assert calls == []
    assert alerts.record_refresh("Trading 212", "admin", err) is True
    (args, kwargs) = calls[0]
    assert args[0] == "refresh"
    assert kwargs["min_hours"] == 24


def test_success_resets_counter(calls):
    err = {"cash": "x"}
    alerts.record_refresh("T", "u", err)
    alerts.record_refresh("T", "u", err)
    alerts.record_refresh("T", "u", {"cash": None})
    alerts.record_refresh("T", "u", err)
    alerts.record_refresh("T", "u", err)
    assert calls == []


def test_users_are_counted_separately(calls):
    for _ in range(2):
        alerts.record_refresh("T", "a", {"x": "e"})
        alerts.record_refresh("T", "b", {"x": "e"})
    assert calls == []


def test_secrets_are_masked(calls):
    err = {"cash": "401 for key SECRET123 on ID999"}
    for _ in range(3):
        alerts.record_refresh("T", "u", err, secrets=("SECRET123", "ID999"))
    body = calls[0][0][2]
    assert "SECRET123" not in body and "ID999" not in body and "***" in body


def test_backup_missing_file_never_alerts(calls, tmp_path):
    assert alerts.check_backup(path=str(tmp_path / "none.json")) is False
    assert calls == []


def test_backup_fresh_and_old(calls, tmp_path):
    p = tmp_path / "backup_status.json"
    p.write_text(json.dumps({"ts": time.time() - 3600}))
    assert alerts.check_backup(path=str(p)) is False
    p.write_text(json.dumps({"ts": time.time() - 30 * 3600}))
    assert alerts.check_backup(path=str(p)) is True
    args, kwargs = calls[0]
    assert args[0] == "backup" and kwargs["key"] == "backup-missing"


def test_xtb_import_ok_is_silent(calls):
    ok = [{"label": "XTB EUR", "cash_ok": True, "positions_ok": True, "unknown_types": []}]
    assert alerts.record_xtb_import(ok, [], "admin") is False
    assert calls == []


def test_xtb_import_problems_alert(calls):
    bad = [{"label": "XTB EUR", "cash_ok": False, "positions_ok": True, "unknown_types": ["Mystery"]}]
    assert alerts.record_xtb_import(bad, ["report.xlsx: boom"], "bob") is True
    body = calls[0][0][2]
    assert "cash check failed" in body and "Mystery" in body and "boom" in body and "bob" in body


def test_lockout_alert_names_existing_user(calls):
    assert alerts.record_lockout("admin", True, 5, 900) is True
    args, kwargs = calls[0]
    assert args[0] == "security" and kwargs["key"] == "lockout:admin" and kwargs["min_hours"] == 1
    assert "admin" in args[2] and "15 minute" in args[2]


def test_lockout_alert_never_echoes_unknown_names(calls):
    alerts.record_lockout("<script>alert(1)</script>", False, 5, 900)
    args, kwargs = calls[0]
    assert "<script>" not in args[2]
    assert kwargs["key"] == "lockout:(nume inexistent)"


def test_user_event_is_never_throttled(calls):
    alerts.record_user_event("parola resetata", "admin", "bob")
    alerts.record_user_event("parola resetata", "admin", "bob")
    assert len(calls) == 2
    assert all(k["min_hours"] == 0 for _, k in calls)
    assert "bob" in calls[0][0][2] and "admin" in calls[0][0][2]
