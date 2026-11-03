from datetime import datetime

import history_multi as hm


def test_points_before_the_time_zone_switch_were_utc(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Bucharest")
    # 26.10 (ora de iarna, UTC+2): punct scris in UTC
    assert hm.to_local("2026-10-27T07:20:00") == datetime(2026, 10, 27, 9, 20)
    assert hm.to_local("2026-07-01T10:00:00") == datetime(2026, 7, 1, 13, 0)  # vara: UTC+3
    # dupa v0.3.18: deja ora locala, ramane asa
    assert hm.to_local("2026-11-03T16:10:00") == datetime(2026, 11, 3, 16, 10)
    assert hm.to_local("2026-10-27T09:40:00") == datetime(2026, 10, 27, 9, 40)


def test_aware_and_date_only_values(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Bucharest")
    assert hm.to_local("2026-11-03T14:00:00+00:00") == datetime(2026, 11, 3, 16, 0)
    assert hm.to_local("2026-11-03T14:00:00Z") == datetime(2026, 11, 3, 16, 0)
    assert hm.to_local("2026-10-01") == datetime(2026, 10, 1, 3, 0)  # zi din istoricul vechi (UTC), vara UTC+3
    assert hm.to_local("2026-11-01") == datetime(2026, 11, 1, 0, 0)  # dupa schimbare: ora locala


def test_three_hours_keep_three_hours_of_local_points(monkeypatch):
    """Regresie: punctele locale erau mutate inca o data cu +2 h, deci la 3H se vedea doar ultima ora."""
    monkeypatch.setenv("TZ", "Europe/Bucharest")
    now = datetime(2026, 11, 3, 17, 10)
    pts = ["2026-11-03T%02d:%02d:00" % divmod(m, 60) for m in range(14 * 60 + 10, 17 * 60 + 11, 15)]
    xs = [hm.to_local(p) for p in pts]
    assert max(xs) <= now and min(xs) >= datetime(2026, 11, 3, 14, 10)
    assert len([x for x in xs if x >= datetime(2026, 11, 3, 14, 10)]) == len(pts)
