from datetime import date

import journal

XTB = {
    "accounts": {"EUR-abc123": {"currency": "EUR", "label": "XTB EUR"}},
    "cash_ops": {"EUR-abc123": {
        "1": {"type": "Deposit", "time": "2026-01-10T09:00:00", "amount": 1000.0, "instrument": None, "ticker": None},
        "2": {"type": "Stock purchase", "time": "2026-01-11T10:00:00", "amount": -500.0, "instrument": "Apple",
              "ticker": "AAPL.US", "comment": "OPEN BUY AAPL.US 2/2 @ 250"},
        "3": {"type": "Dividend", "time": "2026-03-01T00:00:00", "amount": 4.2, "ticker": "AAPL.US"},
        "4": {"type": "Withholding tax", "time": "2026-03-01T00:00:00", "amount": -0.63, "ticker": "AAPL.US"},
        "5": {"type": "Free funds interest", "time": "2026-04-01T00:00:00", "amount": 1.5},
        "6": {"type": "Something new", "time": "2026-04-02T00:00:00", "amount": -1.0},
        "7": {"type": "Deposit", "time": None, "amount": 5.0},
    }},
}
FLOWS = {"flows": [{"t": "2026-02-01T12:00:00Z", "type": "DEPOSIT", "amount": 300.0},
                   {"t": "2026-05-01T12:00:00Z", "type": "WITHDRAW", "amount": 100.0}]}
DIVS = {"dividends": {"MA_US_EQ": {"total": 2.0, "payments": [{"paidOn": "2026-02-09T00:00:00Z", "amount": 2.0}]},
                      "OLD_US_EQ": {"total": 1.0, "count": 1}}}


def _all():
    return journal.xtb_operations(XTB) + journal.t212_operations(FLOWS, DIVS, "EUR", {"MA_US_EQ": "Mastercard"})


def test_xtb_types_are_normalized_and_undated_rows_skipped():
    ops = journal.xtb_operations(XTB)
    assert len(ops) == 6
    kinds = sorted(op["type"] for op in ops)
    assert kinds == ["buy", "deposit", "dividend", "interest", "other", "tax"]
    other = next(op for op in ops if op["type"] == "other")
    assert other["raw_type"] == "Something new"
    assert all(op["account"] == "XTB EUR" and op["ccy"] == "EUR" for op in ops)


def test_t212_withdrawal_is_negative_and_dividends_use_payments():
    ops = journal.t212_operations(FLOWS, DIVS, "EUR", {"MA_US_EQ": "Mastercard"})
    by_type = {op["type"]: op for op in ops}
    assert by_type["deposit"]["amount"] == 300.0
    assert by_type["withdrawal"]["amount"] == -100.0
    assert by_type["dividend"]["instrument"] == "Mastercard"
    assert by_type["dividend"]["date"] == date(2026, 2, 9)
    assert len(ops) == 3  # OLD_US_EQ nu are plati in cache (format vechi)


def test_t212_missing_files():
    assert journal.t212_operations(None, None, "EUR") == []


def test_filter_by_type_account_and_period_newest_first():
    ops = _all()
    deps = journal.filter_ops(ops, types={"deposit"})
    assert [op["date"] for op in deps] == [date(2026, 2, 1), date(2026, 1, 10)]
    only_xtb = journal.filter_ops(ops, types={"deposit"}, accounts={"XTB EUR"})
    assert len(only_xtb) == 1
    feb = journal.filter_ops(ops, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert {op["type"] for op in feb} == {"deposit", "dividend"}


def test_totals_by_type_and_currency():
    sums = journal.totals(journal.filter_ops(_all(), types={"deposit", "withdrawal"}))
    assert sums[("deposit", "EUR")] == (2, 1300.0)
    assert sums[("withdrawal", "EUR")] == (1, -100.0)


def test_period_start():
    today = date(2026, 11, 3)
    assert journal.period_start("ytd", today) == date(2026, 1, 1)
    assert journal.period_start("30d", today) == date(2026, 10, 4)
    assert journal.period_start("all", today) is None
    assert journal.period_start("custom", today) is None
