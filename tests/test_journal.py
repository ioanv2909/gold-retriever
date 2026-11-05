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


def test_t212_fees_interest_and_transfers():
    flows = {"flows": [
        {"t": "2026-03-01T00:00:00Z", "type": "FEE", "amount": 2.5, "signed": -2.5, "ccy": "EUR"},
        {"t": "2026-03-02T00:00:00Z", "type": "INTEREST_ON_FREE_CASH", "amount": 1.2, "signed": 1.2, "ccy": "EUR"},
        {"t": "2026-03-03T00:00:00Z", "type": "LENDING_INTEREST", "amount": 0.3, "signed": 0.3},
        {"t": "2026-03-04T00:00:00Z", "type": "TRANSFER", "amount": 50.0, "signed": -50.0},
    ]}
    ops = {op["raw_type"]: op for op in journal.t212_operations(flows, None, "EUR")}
    assert ops["FEE"]["type"] == "fee" and ops["FEE"]["amount"] == -2.5
    assert ops["INTEREST_ON_FREE_CASH"]["type"] == "interest" and ops["INTEREST_ON_FREE_CASH"]["amount"] == 1.2
    assert ops["LENDING_INTEREST"]["type"] == "interest"
    assert ops["TRANSFER"]["type"] == "other" and ops["TRANSFER"]["amount"] == -50.0


def test_t212_fills_give_trades_and_order_fees():
    fills = {"fills": [
        {"id": "1", "ticker": "MA_US_EQ", "time": "2026-04-01T14:00:00Z", "qty": 2.0, "price": 500.0, "net": 905.0,
         "wccy": "EUR", "ftype": "TRADE", "side": "BUY",
         "taxes": [{"name": "CURRENCY_CONVERSION_FEE", "amount": -1.36, "ccy": "EUR", "time": "2026-04-01T14:00:00Z"}]},
        {"id": "2", "ticker": "MA_US_EQ", "time": "2026-05-01T14:00:00Z", "qty": -1.0, "price": 520.0, "net": 470.0,
         "wccy": "EUR", "ftype": "TRADE", "side": "SELL", "taxes": []},
        {"id": "3", "ticker": "MA_US_EQ", "time": "2026-06-01T14:00:00Z", "qty": 1.0, "price": 0, "net": 0,
         "ftype": "STOCK_SPLIT"},
    ]}
    ops = journal.t212_operations(None, None, "EUR", {"MA_US_EQ": "Mastercard"}, fills)
    kinds = sorted(op["type"] for op in ops)
    assert kinds == ["buy", "fee", "sell"]
    fee = next(op for op in ops if op["type"] == "fee")
    assert fee["amount"] == -1.36 and fee["instrument"] == "Mastercard"
    assert fee["comment"] == "Taxă de conversie valutară"
    assert next(op for op in ops if op["type"] == "buy")["amount"] == -905.0
    assert next(op for op in ops if op["type"] == "sell")["amount"] == 470.0


def test_xirr_flows_ignore_fees_and_interest(monkeypatch):
    import returns_summary
    flows = {"updated": 0, "v": returns_summary.FLOWS_VERSION, "flows": [
        {"t": "2024-01-01T00:00:00Z", "type": "DEPOSIT", "amount": 5000.0},
        {"t": "2025-01-01T00:00:00Z", "type": "FEE", "amount": 4000.0},
        {"t": "2025-02-01T00:00:00Z", "type": "INTEREST_ON_FREE_CASH", "amount": 4000.0},
    ]}
    monkeypatch.setattr(returns_summary, "_flows", lambda: flows)
    monkeypatch.setattr(returns_summary, "_base_ccy", lambda: "EUR")
    import t212_api
    monkeypatch.setattr(t212_api, "load_cached_snapshot", lambda: {"cash": {"total": 6000.0}})
    lines, _notes = returns_summary.compute(show_t212=True, show_xtb=False)
    # comisioanele/dobanzile nu sunt bani retrasi: castigul net ramane 6000 - 5000
    assert any("5,000" in ln and "+1,000" in ln for ln in lines), lines


def test_forced_t212_downloads_start_even_when_fresh(monkeypatch, tmp_path):
    import time
    import returns_summary
    import t212_history_rebuild as rb
    started = []
    monkeypatch.setattr(rb, "FILE", str(tmp_path / "rebuilt.json"))
    (tmp_path / "rebuilt.json").write_text('{"updated": %f}' % time.time())
    monkeypatch.setattr(rb, "_run", lambda: started.append("rebuild"))
    monkeypatch.setattr(rb, "_running", False)
    assert rb.ensure_async() is False
    assert rb.ensure_async(force=True) is True
    assert rb.ensure_async(force=True) is False  # deja pornita
    monkeypatch.setattr(returns_summary, "_refresh_flows", lambda: started.append("flows"))
    monkeypatch.setattr(returns_summary, "_running", False)
    assert returns_summary.start_refresh() is True
    assert returns_summary.start_refresh() is False
    time.sleep(0.2)
    assert sorted(started) == ["flows", "rebuild"]


def test_first_investment_and_months():
    from datetime import date
    import journal
    ops = [{"date": date(2024, 3, 1), "account": "XTB EUR", "type": "deposit"},
           {"date": date(2023, 1, 1), "account": "Trading 212", "type": "dividend"},
           {"date": date(2023, 6, 1), "account": "Trading 212", "type": "buy"}]
    assert journal.first_investment(ops) == date(2023, 6, 1)
    assert journal.first_investment(ops, {"XTB EUR"}) == date(2024, 3, 1)
    assert journal.first_investment(ops, {"Nimic"}) is None
    assert round(journal.months_since(date(2024, 1, 1), date(2025, 1, 1))) == 12
    assert journal.months_since(date(2025, 1, 1), date(2025, 1, 5)) == 1.0
