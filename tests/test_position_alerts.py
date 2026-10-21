import json

import pytest

import notify
import position_alerts as pa
import users

HOLD = {
    "AAPL": {"name": "Apple", "price": 210.0, "ccy": "USD", "value": 700.0},
    "KO": {"name": "Coca-Cola", "price": 60.0, "ccy": "USD", "value": 300.0},
}


def test_price_alert_fires_once():
    alerts = [
        {"id": "a", "ticker": "AAPL", "op": "above", "price": 200.0, "active": True},
        {"id": "b", "ticker": "AAPL", "op": "below", "price": 150.0, "active": True},
        {"id": "c", "ticker": "KO", "op": "below", "price": 60.0, "active": True},
        {"id": "d", "ticker": "GONE", "op": "below", "price": 1e9, "active": True},
    ]
    fired, out = pa.check_prices(alerts, HOLD, now=100.0)
    assert [(f["ticker"], f["op"]) for f in fired] == [("AAPL", "above"), ("KO", "below")]
    assert [a["active"] for a in out] == [False, True, False, True]
    assert out[0]["triggered_at"] == 100.0
    fired, _ = pa.check_prices(out, HOLD, now=200.0)
    assert fired == []


def test_score_first_value_is_baseline_then_alerts():
    rule = {"enabled": True, "kinds": ["quality", "dividend"], "below": 50, "drop": 15}
    fired, state = pa.check_scores(rule, {"X": {"quality": 70, "dividend": 55, "risk": 10}}, {})
    assert fired == [] and "risk" not in state["X"]

    fired, state = pa.check_scores(rule, {"X": {"quality": 54, "dividend": 48}}, state)
    assert [(f["score_kind"], f["reason"], f["previous"]) for f in fired] == [("quality", "drop", 70), ("dividend", "below", 55)]

    # sub prag in continuare: nu se repeta; revine peste prag + 5, apoi scade iar: alerta din nou
    fired, state = pa.check_scores(rule, {"X": {"dividend": 45}}, state)
    assert fired == []
    fired, state = pa.check_scores(rule, {"X": {"dividend": 56}}, state)
    fired, state = pa.check_scores(rule, {"X": {"dividend": 49}}, state)
    assert [f["reason"] for f in fired] == ["below"]


def test_score_drop_measured_from_peak():
    rule = {"enabled": True, "kinds": ["risk"], "below": 0, "drop": 10}
    _, state = pa.check_scores(rule, {"X": {"risk": 60}}, {})
    _, state = pa.check_scores(rule, {"X": {"risk": 80}}, state)
    fired, state = pa.check_scores(rule, {"X": {"risk": 69}}, state)
    assert fired and fired[0]["previous"] == 80


def test_disabled_rules_do_nothing():
    off = {"enabled": False, "kinds": ["quality"], "below": 50, "drop": 1}
    assert pa.check_scores(off, {"X": {"quality": 1}}, {}) == ([], {})
    assert pa.check_concentration({"enabled": False, "max_pct": 1}, {"X": 50}, {}) == ([], {})


def test_concentration_with_hysteresis():
    rule = {"enabled": True, "max_pct": 20}
    fired, state = pa.check_concentration(rule, {"A": 25.0, "B": 10.0}, {})
    assert [f["ticker"] for f in fired] == ["A"]
    fired, state = pa.check_concentration(rule, {"A": 19.0}, state)
    assert fired == [] and state["A"] is True
    fired, state = pa.check_concentration(rule, {"A": 17.0}, state)
    fired, state = pa.check_concentration(rule, {"A": 21.0}, state)
    assert [f["ticker"] for f in fired] == ["A"]


def test_merge_holdings_across_accounts():
    fx = lambda a, b: {("USD", "EUR"): 0.9, ("GBP", "EUR"): 1.2, ("PLN", "EUR"): 0.25}.get((a, b), 1.0)
    t212 = [{"ticker": "AAPL_US_EQ", "quantity": 2, "currentPrice": 200.0},
            {"ticker": "VUSA", "quantity": 10, "currentPrice": 5000.0}]
    instruments = [{"ticker": "AAPL_US_EQ", "name": "Apple", "currencyCode": "USD"},
                   {"ticker": "VUSA", "name": "Vanguard S&P", "currencyCode": "GBX"}]
    xtb = [{"ticker": "AAPL_US_EQ", "name": "Apple Inc", "currentPrice": 201.0, "currencyCode": "USD",
            "value_account": 1000.0, "account_currency": "PLN"}]
    h = pa.merge_holdings(t212, instruments, "EUR", xtb, "EUR", fx)
    assert h["VUSA"]["price"] == 50.0 and h["VUSA"]["ccy"] == "GBP"
    assert h["VUSA"]["value"] == pytest.approx(600.0)
    assert h["AAPL_US_EQ"]["value"] == pytest.approx(360.0 + 250.0)
    assert h["AAPL_US_EQ"]["price"] == 200.0 and h["AAPL_US_EQ"]["name"] == "Apple"
    w = pa.weights_of(h)
    assert sum(w.values()) == pytest.approx(100.0)


def test_scores_of_respects_coverage():
    q = {"X": {"total": 70, "coverage": 80, "risk_total": 40, "risk_coverage": 30, "div_total": 60, "div_coverage": 100}}
    assert pa.scores_of(q, ["X", "Y"]) == {
        "X": {"quality": 70, "risk": None, "dividend": 60},
        "Y": {"quality": None, "risk": None, "dividend": None},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("RULES_FILE", "STATE_FILE", "LOG_FILE"):
        monkeypatch.setattr(pa, name, str(tmp_path / (name.lower() + ".json")))
    monkeypatch.setattr(users, "email", lambda name: "bob@example.com" if name == "bob" else None)
    monkeypatch.setattr(pa, "_user_lang", lambda: "EN")
    sent = []
    monkeypatch.setattr(notify, "notify", lambda *a, **kw: sent.append((a, kw)) or True)
    return sent


def test_rules_roundtrip_and_defaults_not_shared(env):
    r = pa.load_rules()
    r["price"].append("x")
    assert pa.load_rules()["price"] == []
    a = pa.add_price_alert("KO", "below", 55, "Coca-Cola", "USD")
    assert pa.add_price_alert("KO", "sideways", 55) is None
    assert pa.add_price_alert("KO", "below", 0) is None
    pa.save_score_rule(True, ["quality", "bogus"], 40, 0)
    pa.save_concentration_rule(True, 25)
    r = pa.load_rules()
    assert [x["id"] for x in r["price"]] == [a["id"]]
    assert r["score"] == {"enabled": True, "kinds": ["quality"], "below": 40, "drop": 1}
    assert r["concentration"] == {"enabled": True, "max_pct": 25.0}
    pa.remove_price_alert(a["id"])
    assert pa.load_rules()["price"] == []


def test_evaluate_logs_emails_and_disarms(env):
    pa.add_price_alert("KO", "below", 61, "Coca-Cola", "USD")
    pa.save_concentration_rule(True, 50)
    fired = pa.evaluate("bob", now=1000.0, holdings=HOLD, quality={})
    assert {f["kind"] for f in fired} == {"price", "concentration"}
    (event, subject, body), kw = env[0]
    assert event == "positions" and kw["to"] == ["bob@example.com"] and "2" in subject
    assert "Coca-Cola (KO): price fell to 60.00 USD" in body and "Apple (AAPL): now 70.0%" in body
    assert pa.load_rules()["price"][0]["active"] is False
    assert len(pa.load_log()) == 2 and not any(e["seen"] for e in pa.load_log())

    assert pa.evaluate("bob", now=2000.0, holdings=HOLD, quality={}) == []
    assert len(env) == 1
    pa.dismiss()
    assert all(e["seen"] for e in pa.load_log())


def test_evaluate_without_email_still_logs(env):
    pa.save_concentration_rule(True, 50)
    assert len(pa.evaluate("nomail", now=1.0, holdings=HOLD, quality={})) == 1
    assert env == [] and len(pa.load_log()) == 1


def test_evaluate_skips_when_no_rules(env):
    assert pa.evaluate("bob", holdings=None) == []
