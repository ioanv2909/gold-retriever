import gzip
import os
import time
from datetime import date, datetime

import pytest

import logstore


def _ts(day):
    return time.mktime(datetime.fromisoformat(day + "T12:00:00").timetuple())


def _make(day, text="x\n"):
    os.makedirs(logstore.LOG_DIR, exist_ok=True)
    with open(os.path.join(logstore.LOG_DIR, "app-%s.log" % day), "w") as f:
        f.write(text)


def test_write_appends_one_file_per_day():
    logstore.write(_ts("2026-11-01"), "first")
    logstore.write(_ts("2026-11-01"), "second")
    logstore.write(_ts("2026-11-02"), "third")
    names = [f["name"] for f in logstore.files()]
    assert names == ["app-2026-11-02.log", "app-2026-11-01.log"]
    text = logstore.read("app-2026-11-01.log").decode()
    assert text.splitlines()[0].endswith("  first") and text.count("\n") == 2


def test_archive_keeps_recent_and_today_and_is_lossless():
    for d in ("2026-10-01", "2026-10-28", "2026-11-03"):
        _make(d, "line of %s\n" % d)
    assert logstore.archive_older_than(7, today=date(2026, 11, 3)) == 1
    by = {f["name"]: f for f in logstore.files()}
    assert "app-2026-10-01.log.gz" in by and "app-2026-10-01.log" not in by
    assert "app-2026-10-28.log" in by and "app-2026-11-03.log" in by
    assert logstore.read("app-2026-10-01.log.gz") == b"line of 2026-10-01\n"
    with gzip.open(os.path.join(logstore.LOG_DIR, "app-2026-10-01.log.gz")) as f:
        assert f.read() == b"line of 2026-10-01\n"


def test_delete_removes_only_old_archives():
    for d in ("2026-06-01", "2026-10-01"):
        _make(d)
    logstore.archive_older_than(1, today=date(2026, 11, 3))
    _make("2026-05-01")  # nearhivat: nu se sterge
    assert logstore.delete_archives_older_than(90, today=date(2026, 11, 3)) == 1
    names = {f["name"] for f in logstore.files()}
    assert names == {"app-2026-10-01.log.gz", "app-2026-05-01.log"}


def test_path_of_rejects_other_names():
    for bad in ("../users.json", "app-2026-11-01.log/../../x", "mail.json", "/etc/passwd"):
        with pytest.raises(ValueError):
            logstore.path_of(bad)


def test_settings_defaults_and_save():
    assert logstore.load_settings() == logstore.DEFAULTS
    logstore.save_settings({"archive_after_days": 3, "alert_free_pct": "15", "other": 1})
    cfg = logstore.load_settings()
    assert cfg["archive_after_days"] == 3 and cfg["alert_free_pct"] == 15 and "other" not in cfg


def test_problems_thresholds():
    cfg = {"archive_after_days": 7, "alert_logs_mb": 1, "alert_free_pct": 10}
    u = {"logs": 2 * 1024 * 1024, "archives": 0, "free_pct": 5.0, "disk_free": 3 * 1024 ** 3}
    out = logstore.problems(u, cfg)
    assert len(out) == 2 and "2 MB" in out[0] and "5.0%" in out[1]
    assert logstore.problems(u, dict(cfg, alert_logs_mb=0, alert_free_pct=0)) == []


def test_check_runs_hourly_archives_and_alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(logstore.notify, "notify", lambda *a, **k: sent.append((a, k)) or True)
    monkeypatch.setattr(logstore, "usage", lambda: {"logs": 0, "archives": 0, "free_pct": 4.0, "disk_free": 1024 ** 3})
    _make("2020-01-01")
    res = logstore.check(now=1000000.0)
    assert res["archived"] == 1 and res["problems"]
    assert sent and sent[0][0][0] == "logs" and sent[0][1]["min_hours"] == 24
    assert logstore.check(now=1000000.0 + 60) is None  # inca nu a trecut ora
