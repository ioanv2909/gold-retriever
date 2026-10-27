import pytest

import descriptions
import i18n


@pytest.fixture
def en(monkeypatch):
    monkeypatch.setattr(i18n, "lang", lambda: "EN")


@pytest.mark.parametrize("ro,en_text", [
    ("Ponderea poziției în portofoliu: 12.5%", "Position weight in the portfolio: 12.5%"),
    ("AAPL există deja în watchlist", "AAPL is already in the watchlist"),
    ("ℹ️ Istoricul de preț de la Yahoo a fost corectat pentru calculele de mai jos: discontinuitate ~1:10 la 2024-05-01.",
     "ℹ️ The Yahoo price history was corrected for the calculations below: discontinuity ~1:10 on 2024-05-01."),
    ("din care efect de curs: +1.25 pp", "of which currency effect: +1.25 pp"),
])
def test_dynamic_texts_are_translated(en, ro, en_text):
    assert i18n.x(ro) == en_text


@pytest.mark.parametrize("key", ["quality", "risk", "valuation", "trend", "weight"])
def test_checklist_tooltips_have_no_romanian_left(en, key):
    out = i18n.x(descriptions.checklist_tooltip(key))
    assert not any(c in out for c in "ăâîșțȘȚ"), out


def test_romanian_ui_is_unchanged(monkeypatch):
    monkeypatch.setattr(i18n, "lang", lambda: "RO")
    s = "AAPL există deja în watchlist"
    assert i18n.x(s) == s
