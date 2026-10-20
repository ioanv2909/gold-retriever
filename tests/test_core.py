from datetime import datetime, timezone

import pytest

import portfolio_model
import returns_summary
import t212_history
import xtb
import yahoo


def d(y, m, day):
    return datetime(y, m, day, tzinfo=timezone.utc)


XIRRS = [returns_summary.xirr, t212_history.xirr]


@pytest.mark.parametrize("xirr", XIRRS)
def test_xirr_one_year_ten_percent(xirr):
    # 365 zile intre date; formula foloseste 365.25 zile/an
    r = xirr([(d(2023, 1, 1), -1000), (d(2024, 1, 1), 1100)])
    assert r == pytest.approx(1.1 ** (365.25 / 365) - 1, abs=1e-6)


@pytest.mark.parametrize("xirr", XIRRS)
def test_xirr_loss_is_negative(xirr):
    r = xirr([(d(2023, 1, 1), -1000), (d(2024, 1, 1), 900)])
    assert r < 0


@pytest.mark.parametrize("xirr", XIRRS)
def test_xirr_not_enough_or_one_sided_flows(xirr):
    assert xirr([]) is None
    assert xirr([(d(2023, 1, 1), -1000)]) is None
    assert xirr([(d(2023, 1, 1), -1000), (d(2024, 1, 1), -500)]) is None
    assert xirr([(d(2023, 1, 1), 0), (d(2024, 1, 1), 0)]) is None


def test_both_xirr_copies_agree():
    flows = [
        (d(2022, 1, 1), -1000),
        (d(2022, 7, 1), -500),
        (d(2023, 3, 1), -200),
        (d(2024, 6, 1), 2100),
    ]
    assert returns_summary.xirr(flows) == pytest.approx(t212_history.xirr(flows), abs=1e-9)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.56", 1234.56),
        ("1.234,56", 1234.56),
        ("12,5", 12.5),
        ("(12.5)", -12.5),
        ("5%", 5.0),
        ("-3.2", -3.2),
        (7, 7.0),
        (2.5, 2.5),
        ("1\u00a0234,50", 1234.50),
    ],
)
def test_xtb_to_float(raw, expected):
    assert xtb._to_float(raw) == pytest.approx(expected)


def test_xtb_to_float_empty():
    assert xtb._to_float(None) is None
    assert xtb._to_float("") is None


def test_annualize():
    assert yahoo.annualize(10, 365) == pytest.approx(10.0)
    assert yahoo.annualize(0, 100) == pytest.approx(0.0)
    assert yahoo.annualize(21, 730) == pytest.approx(10.0)


@pytest.fixture
def clean_fx_cache(monkeypatch):
    monkeypatch.setattr(portfolio_model, "_FX_CACHE", {})


def test_fx_same_currency_needs_no_lookup(clean_fx_cache, monkeypatch):
    def boom(*a):
        raise AssertionError("nu trebuie apelat")

    monkeypatch.setattr(portfolio_model, "fetch_fx_rate", boom)
    assert portfolio_model.fx("EUR", "EUR") == 1.0


def test_fx_direct_and_cached(clean_fx_cache, monkeypatch):
    calls = []

    def fake(f, t):
        calls.append((f, t))
        return 0.2, None

    monkeypatch.setattr(portfolio_model, "fetch_fx_rate", fake)
    assert portfolio_model.fx("RON", "EUR") == pytest.approx(0.2)
    assert portfolio_model.fx("RON", "EUR") == pytest.approx(0.2)
    assert calls == [("RON", "EUR")]  # a doua oara vine din cache


def test_fx_cross_rate_via_usd(clean_fx_cache, monkeypatch):
    table = {("RON", "USD"): 0.2, ("USD", "EUR"): 0.9}

    def fake(f, t):
        if (f, t) in table:
            return table[(f, t)], None
        return None, "no direct pair"

    monkeypatch.setattr(portfolio_model, "fetch_fx_rate", fake)
    assert portfolio_model.fx("RON", "EUR") == pytest.approx(0.18)
