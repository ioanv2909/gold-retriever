import io
from datetime import datetime

import openpyxl
import pytest

import xtb

REPORT_TIME = datetime(2025, 10, 1, 12, 0, 0)


def make_report(extra_cash=(), with_value_row=True):
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Open Positions"
    rows = [
        ["Account number", 12345678],
        ["Data as of report", REPORT_TIME],
        [],
        ["Metric", "Value", "Currency"],
    ]
    if with_value_row:
        rows.append(["Open position value", 1500.0, "EUR"])
    rows += [
        ["Open position profit", 100.0, "EUR"],
        [],
        ["Product", "Instrument/Position", "Ticker", "Category", "Type", "Volume",
         "Open price", "Current price", "Value", "Net profit", "ISIN", "Open time"],
        [None, "Vanguard FTSE All-World", "VWCE.DE", "ETF", None, 10,
         100.0, None, 1200.0, 200.0, "IE00BK5BQT80", None],
        [None, "1001", None, None, "BUY", 10,
         100.0, 120.0, 1200.0, None, None, datetime(2025, 3, 3, 10, 0)],
        [None, "Coca-Cola", "KO.US", "STOCK", None, 5,
         55.0, None, 300.0, 25.0, "US1912161007", None],
        [None, "1002", None, None, "BUY", 5,
         55.0, 60.0, 300.0, None, None, datetime(2025, 6, 10, 15, 30)],
    ]
    for r in rows:
        ws.append(r)

    cash = wb.create_sheet("Cash Operations")
    cash_rows = [
        ["Type", "Instrument", "Ticker", "Category", "Time", "Amount", "ID", "Comment", "Position ID"],
        ["Deposit", None, None, None, datetime(2025, 3, 1, 9, 0), 2000.0, 1, "Deposit", None],
        ["Stock purchase", "Vanguard FTSE All-World", "VWCE.DE", "ETF",
         datetime(2025, 3, 3, 10, 0), -1000.0, 2, "OPEN BUY VWCE.DE 10/10 @ 100.00", "1001"],
        ["Stock purchase", "Coca-Cola", "KO.US", "STOCK",
         datetime(2025, 6, 10, 15, 30), -275.0, 3, "OPEN BUY KO.US 5/5 @ 55.00", "1002"],
        ["Dividend", "Coca-Cola", "KO.US", "STOCK",
         datetime(2025, 9, 15), 2.5, 4, "KO.US USD 0.51/ SHR", None],
    ]
    cash_rows += [list(r) for r in extra_cash]
    total = sum(r[5] for r in cash_rows[1:])
    cash_rows.append(["Total", None, None, None, None, total, None, None, None])
    for r in cash_rows:
        cash.append(r)

    closed = wb.create_sheet("Closed Positions")
    closed.append(["Instrument", "Ticker", "Category", "Type", "Volume", "Open time",
                   "Open price", "Close time", "Close price", "Profit", "Position ID"])
    closed.append(["Apple", "AAPL.US", "STOCK", "BUY", 2, datetime(2025, 1, 2),
                   150.0, datetime(2025, 2, 2), 160.0, 20.0, "P900"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_basic_fields():
    p = xtb.parse_xtb_file(make_report())
    assert p["currency"] == "EUR"
    assert p["account_key"].startswith("EUR-") and len(p["account_key"]) == len("EUR-") + 6
    assert "2025-10-01" in p["report_time"]
    assert p["summary"]["value"] == pytest.approx(1500.0)
    assert p["summary"]["profit"] == pytest.approx(100.0)


def test_positions_and_lots():
    p = xtb.parse_xtb_file(make_report())
    by_ticker = {x["ticker"]: x for x in p["positions"]}
    assert set(by_ticker) == {"VWCE.DE", "KO.US"}
    vwce = by_ticker["VWCE.DE"]
    assert vwce["volume"] == pytest.approx(10)
    assert vwce["value"] == pytest.approx(1200.0)
    assert vwce["isin"] == "IE00BK5BQT80"
    assert len(vwce["lots"]) == 1
    assert vwce["lots"][0]["open_price"] == pytest.approx(100.0)
    assert vwce["initial_fill"].startswith("2025-03-03")


def test_cash_operations_and_purchase_comment():
    p = xtb.parse_xtb_file(make_report())
    ops = p["cash_ops"]
    assert [o["type"] for o in ops] == ["Deposit", "Stock purchase", "Stock purchase", "Dividend"]
    buy = ops[1]["stock_purchase"]
    assert buy == {"ticker": "VWCE.DE", "part": 10, "total": 10, "price": pytest.approx(100.0)}
    assert ops[3]["amount"] == pytest.approx(2.5)
    assert p["unknown_types"] == []


def test_consistency_checks_match():
    p = xtb.parse_xtb_file(make_report())
    c = p["checks"]
    assert c["cash_sum"] == pytest.approx(727.5)
    assert c["total_row"] == pytest.approx(727.5)
    assert c["positions_value_sum"] == pytest.approx(c["summary_value"])


def test_closed_positions():
    p = xtb.parse_xtb_file(make_report())
    assert len(p["closed"]) == 1
    assert p["closed"][0]["position_id"] == "P900"
    assert p["closed"][0]["Ticker"] == "AAPL.US"


def test_unknown_operation_type_is_reported():
    extra = [["Mystery", None, None, None, datetime(2025, 9, 20), 1.0, 5, "x", None]]
    p = xtb.parse_xtb_file(make_report(extra_cash=extra))
    assert p["unknown_types"] == ["Mystery"]


def test_missing_currency_row_raises():
    with pytest.raises(ValueError, match="Currency"):
        xtb.parse_xtb_file(make_report(with_value_row=False))
