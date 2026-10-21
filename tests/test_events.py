import json
from datetime import date, datetime

import pytest

import events
import notify
import users

TODAY = date(2026, 10, 21)
CACHE = {
    "AAPL_US_EQ": {"events": [
        {"type": "earnings", "date": "2026-11-02", "eps_avg": 1.98},
        {"type": "ex_dividend", "date": "2026-08-09"},
        {"type": "dividend_payment", "date": "2026-08-12"},
    ]},
    "KO_US_EQ": {"events": [
        {"type": "earnings", "date": "2026-10-27"},
        {"type": "ex_dividend", "date": "2026-11-30"},
        {"type": "dividend_payment", "date": "2026-12-14"},
    ]},
    "OTHER": {"events": [{"type": "earnings", "date": "2026-10-22"}]},
}


def test_parse_calendar_yfinance_dict():
    cal = {
        "Dividend Date": date(2026, 12, 14), "Ex-Dividend Date": date(2026, 11, 30),
        "Earnings Date": [date(2026, 10, 27), date(2026, 10, 29)],
        "Earnings Average": 0.88, "Revenue Average": 12925421630, "Earnings High": 0.89,
    }
    assert events.parse_calendar(cal) == [
        {"type": "earnings", "date": "2026-10-27", "date_end": "2026-10-29", "eps_avg": 0.88, "revenue_avg": 12925421630.0},
        {"type": "ex_dividend", "date": "2026-11-30"},
        {"type": "dividend_payment", "date": "2026-12-14"},
    ]


def test_parse_calendar_empty_or_odd_values():
    assert events.parse_calendar({}) == []
    assert events.parse_calendar(None) == []
    assert events.parse_calendar({"Earnings Date": [], "Dividend Date": None}) == []
    assert events.parse_calendar({"Earnings Date": datetime(2026, 1, 5, 20, 0), "Earnings Average": float("nan")}) == [
        {"type": "earnings", "date": "2026-01-05"}]


def test_upcoming_filters_window_and_tickers():
    rows = events.upcoming(CACHE, ["AAPL_US_EQ", "KO_US_EQ"], TODAY, days=30)
    assert [(r["ticker"], r["type"], r["days"]) for r in rows] == [
        ("KO_US_EQ", "earnings", 6),
        ("AAPL_US_EQ", "earnings", 12),
    ]
    assert len(events.upcoming(CACHE, ["KO_US_EQ"], TODAY, days=60)) == 3


def test_upcoming_keeps_earnings_range_until_last_day():
    cache = {"X": {"events": [{"type": "earnings", "date": "2026-10-19", "date_end": "2026-10-23"}]}}
    rows = events.upcoming(cache, ["X"], TODAY, days=7)
    assert len(rows) == 1 and rows[0]["days"] == -2


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("EVENTS_CACHE_FILE", "EVENTS_PREFS_FILE", "EVENTS_NOTIFIED_FILE", "EVENTS_STATUS_FILE"):
        monkeypatch.setattr(events, name, str(tmp_path / (name.lower() + ".json")))
    monkeypatch.setattr(users, "email", lambda name: "bob@example.com" if name == "bob" else None)
    monkeypatch.setattr(events, "_user_lang", lambda: "EN")
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *a, **kw: sent.append((a, kw)) or True)
    return sent


def test_notify_disabled_by_default(env):
    assert events.notify_upcoming(["KO_US_EQ"], "bob", TODAY, CACHE) is False
    assert env == []


def test_notify_sends_each_event_once(env):
    events.save_prefs(True, 7)
    assert events.notify_upcoming(["KO_US_EQ", "AAPL_US_EQ", "OTHER"], "bob", TODAY, CACHE) is True
    (event, subject, body), kw = env[0]
    assert event == "events" and kw["to"] == ["bob@example.com"]
    assert "2 upcoming" in subject
    assert "KO_US_EQ" in body and "OTHER" in body and "AAPL_US_EQ" not in body

    assert events.notify_upcoming(["KO_US_EQ", "OTHER"], "bob", TODAY, CACHE) is False
    assert len(env) == 1
    # mai tarziu intra in fereastra si rezultatele AAPL: doar ele sunt trimise
    assert events.notify_upcoming(["KO_US_EQ", "AAPL_US_EQ"], "bob", date(2026, 10, 27), CACHE) is True
    body = env[1][0][2]
    assert "AAPL_US_EQ" in body and "KO_US_EQ" not in body


def test_notify_needs_user_email(env):
    events.save_prefs(True, 7)
    assert events.notify_upcoming(["KO_US_EQ"], "nomail", TODAY, CACHE) is False
    assert env == []


def test_fetch_skips_fresh_entries(env, monkeypatch):
    with open(events.EVENTS_CACHE_FILE, "w") as f:
        json.dump({"A": {"events": [], "fetched_at": 1000.0}}, f)
    calls = []
    monkeypatch.setattr(events, "fetch_events", lambda s: calls.append(s) or ([{"type": "earnings", "date": "2026-11-01"}], None))
    cache = events.fetch_and_cache_events(["A", "B"], resolve=lambda t: t + ".Y", now=2000.0, sleep=0)
    assert calls == ["B.Y"]
    assert cache["B"]["symbol"] == "B.Y" and cache["A"]["fetched_at"] == 1000.0
    with open(events.EVENTS_CACHE_FILE) as f:
        assert set(json.load(f)) == {"A", "B"}
    assert events.load_status().get("in_progress") is False
