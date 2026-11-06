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
