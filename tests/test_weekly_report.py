import json
from datetime import date, datetime

import pytest

import events
import history_multi
import notify
import t212_api
import weekly_report as wr
import xtb_positions

NOW = datetime(2026, 10, 31, 10, 0)  # sambata


def _pt(ts, value, cost):
    return {"ts": ts, "entries": {"Trading 212": {"ccy": "EUR", "value": value, "cost": cost}}, "rates": {"EUR": 1.0}}


@pytest.fixture
def data(monkeypatch):
    hist = [_pt("2026-10-20T10:00:00", 1000.0, 900.0), _pt("2026-10-24T09:00:00", 1010.0, 900.0),
            _pt("2026-10-31T09:55:00", 1150.0, 1000.0)]
    monkeypatch.setattr(history_multi, "load_multi_history", lambda: hist)
    monkeypatch.setattr(history_multi, "_merged_history", lambda: hist)
    monkeypatch.setattr(t212_api, "load_cached_snapshot", lambda: {
        "positions": [{"ticker": "AAPL_US_EQ"}, {"ticker": "TSLA_US_EQ"}, {"ticker": "KO_US_EQ"}],
        "instruments": [{"ticker": "AAPL_US_EQ", "name": "Apple"}, {"ticker": "TSLA_US_EQ", "name": "Tesla"}]})
    monkeypatch.setattr(xtb_positions, "xtb_rows", lambda: [{"ticker": "VWCE.DE", "name": "Vanguard All-World"}])
    monkeypatch.setattr(t212_api, "load_cached_dividends", lambda: {"dividends": {"AAPL_US_EQ": {"total": 12.5}, "KO_US_EQ": {"total": 3.0}}})
    monkeypatch.setattr(events, "load_cache", lambda: {"AAPL_US_EQ": {"events": [{"type": "earnings", "date": "2026-11-03"}]},
                                                     "KO_US_EQ": {"events": [{"type": "earnings", "date": "2026-12-20"}]}})
    return hist


CHANGES = {"AAPL": 4.2, "TSLA": -6.5, "KO": 0.3, "VWCE.DE": -1.1}


def _changes(symbols):
    return {s: CHANGES[s] for s in symbols if s in CHANGES}


def test_value_summary_uses_the_point_from_a_week_ago(data):
    v = wr.value_summary(NOW)
    assert v["since"] == "2026-10-24" and v["full_week"]
    assert v["value_then"] == 1010.0 and v["value_now"] == 1150.0
    assert v["deposits"] == 100.0  # 900 -> 1000 investit
    assert v["result"] == pytest.approx(40.0)  # P/L 110 -> 150, fara depuneri


def test_report_text(data):
    subject, body, totals = wr.build("RO", NOW.date(), NOW, _changes, state={"div_totals": {"AAPL_US_EQ": 10.0}})
    assert subject == "Raport săptămânal 31.10.2026"
    assert "1,150.00 EUR" in body and "+40.00 EUR (+3.96%)" in body and "+100.00 EUR" in body
    up, down = body.split("Cele mai mari creșteri")[1].split("Cele mai mari scăderi")
    assert "+4.20%  Apple" in up and "Tesla" not in up and "_US_EQ" not in up
    assert down.index("Tesla") < down.index("Vanguard All-World")  # cea mai mare scadere prima
    assert "5.50" in body  # dividende: AAPL +2.5, KO nou +3.0
    assert "2026-11-03  Apple: " in body and "2026-12-20" not in body
    assert "_US_EQ" not in body  # numele complete, nu tickerele T212
    assert totals == {"AAPL_US_EQ": 12.5, "KO_US_EQ": 3.0}


def test_report_in_english_and_without_history(data, monkeypatch):
    monkeypatch.setattr(history_multi, "load_multi_history", lambda: [])
    _s, body, _t = wr.build("EN", NOW.date(), NOW, lambda s: {}, state={})
    assert "not have enough points" in body and "Dividends" not in body
    assert not any(c in body for c in "ăâîșț")


def test_due_once_per_week_on_the_chosen_day_and_hour():
    prefs = {"enabled": True, "weekday": 5, "hour": 9}
    assert wr.due(prefs, NOW, {})
    assert not wr.due(prefs, NOW.replace(hour=8), {})
    assert not wr.due(prefs, datetime(2026, 10, 30, 10), {})  # vineri
    assert not wr.due(prefs, NOW, {"last_week": wr.week_key(NOW.date())})
    assert not wr.due(dict(prefs, enabled=False), NOW, {})


def test_send_marks_the_week_and_keeps_dividend_totals(data, monkeypatch):
    import users
    sent = []
    monkeypatch.setattr(users, "email", lambda u: "ana@example.invalid")
    monkeypatch.setattr(notify, "notify", lambda *a, **k: sent.append((a, k)) or True)
    monkeypatch.setattr(wr, "week_changes", _changes)  # fara Yahoo
    assert wr.maybe_send("ana", NOW) is False  # dezactivat implicit
    wr.save_prefs(True, 5, 9)
    assert wr.maybe_send("ana", NOW) is True
    assert wr.maybe_send("ana", NOW.replace(hour=15)) is False  # aceeasi saptamana
    state = wr._load_state()
    assert state["last_week"] == "2026-W44" and state["div_totals"]["AAPL_US_EQ"] == 12.5
    assert len(sent) == 1 and sent[0][1]["to"] == ["ana@example.invalid"] and sent[0][0][0] == "weekly"


def test_test_send_does_not_mark_the_week(data, monkeypatch):
    import users
    monkeypatch.setattr(users, "email", lambda u: "ana@example.invalid")
    monkeypatch.setattr(notify, "notify", lambda *a, **k: True)
    assert wr.send("ana", NOW, mark=False, changes_fn=_changes)
    assert wr._load_state() == {}


def test_new_notification_types_are_on_for_saved_settings(monkeypatch, tmp_path):
    path = tmp_path / "mail.json"
    monkeypatch.setattr(notify, "MAIL_FILE", str(path))
    path.write_text(json.dumps({"events": ["backup", "security"]}))  # salvat inainte de "weekly"
    assert notify.load_settings()["events"] == ["backup", "security", "weekly"]
    cfg = notify.save_settings({"events": ["backup"]})  # adminul l-a oprit explicit
    assert cfg["events"] == ["backup"] and notify.load_settings()["events"] == ["backup"]


def _settings_page():
    import weekly_report_ui
    weekly_report_ui.render_settings_section("ana")


def test_settings_save_and_preview(data, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(wr, "week_changes", _changes)
    at = AppTest.from_function(_settings_page).run()
    assert not at.exception
    at.checkbox(key="wr_on").check()
    at.selectbox(key="wr_day").select(0)
    at.button(key="wr_save").click().run()
    assert wr.load_prefs() == {"enabled": True, "weekday": 0, "hour": 9}
    at.button(key="wr_preview").click().run()
    assert not at.exception and "Raport săptămânal GoldRetriever" in at.code[0].value
