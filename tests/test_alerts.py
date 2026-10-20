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
