import pace_target as pt


def test_color_levels():
    assert pt.color_for(1000, 1000) == "#21c354"
    assert pt.color_for(950, 1000) == "#e8c547"
    assert pt.color_for(800, 1000) == "#eb8c34"
    assert pt.color_for(500, 1000) == "#ff4b4b"


def test_load_ignores_missing_or_zero(monkeypatch):
    monkeypatch.setattr(pt, "load_pref", lambda k: None)
    assert pt.load() is None
    monkeypatch.setattr(pt, "load_pref", lambda k: {"amount": 0, "ccy": "EUR"})
    assert pt.load() is None
    monkeypatch.setattr(pt, "load_pref", lambda k: {"amount": 500, "ccy": "RON"})
    assert pt.load() == (500.0, "RON")


def test_badge_css_targets_container():
    css = pt.badge_css("pace_metric", "#ff4b4b")
    assert '.st-key-pace_metric [data-testid="stMetricDelta"]' in css and "rgba(255,75,75,0.22)" in css


def _ops(amount):
    from datetime import date
    return [{"type": "deposit", "date": date(2026, 1, 1), "account": "A", "ccy": "EUR", "amount": amount}]


def test_pace_of(monkeypatch):
    from datetime import date
    import portfolio_model
    monkeypatch.setattr(portfolio_model, "fx", lambda a, b: 1.0)
    start, net, months, pace = pt.pace_of(_ops(1000.0), "EUR", today=date(2026, 11, 1))
    assert start == date(2026, 1, 1) and net == 1000.0 and round(months) == 10 and round(pace) == 100
    assert pt.pace_of([], "EUR")[3] is None


def test_email_once_until_back_at_target(monkeypatch):
    from datetime import date
    import portfolio_model
    monkeypatch.setattr(portfolio_model, "fx", lambda a, b: 1.0)
    monkeypatch.setattr(pt, "load_pref", lambda k: {"amount": 200, "ccy": "EUR", "email": True})
    sent = []
    monkeypatch.setattr(pt, "_send", lambda user, pace, tg, months: sent.append(round(pace)) or True)
    day = date(2026, 11, 1)
    assert pt.check_and_notify("bob", _ops(1000.0), day) is True       # 100/luna < 200
    assert pt.check_and_notify("bob", _ops(1000.0), day) is False      # deja anuntat
    assert pt.check_and_notify("bob", _ops(3000.0), day) is False      # inapoi peste tinta: rearmat
    assert pt.check_and_notify("bob", _ops(1950.0), day) is False      # 195 = 97.5%: in marja, fara email
    assert pt.check_and_notify("bob", _ops(1500.0), day) is True       # sub 95% din nou
    assert sent == [100, 150]


def test_no_email_when_disabled(monkeypatch):
    monkeypatch.setattr(pt, "load_pref", lambda k: {"amount": 200, "ccy": "EUR", "email": False})
    monkeypatch.setattr(pt, "_send", lambda *a: (_ for _ in ()).throw(AssertionError("sent")))
    assert pt.check_and_notify("bob", _ops(10.0)) is False
