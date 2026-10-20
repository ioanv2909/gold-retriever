import copy
from datetime import datetime, timedelta

import pytest

import xtb
from test_xtb_parse import make_report


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(xtb, "XTB_FILE", str(tmp_path / "xtb.json"))
    return tmp_path


@pytest.fixture
def parsed():
    return xtb.parse_xtb_file(make_report())


def stored(parsed):
    data = xtb.load_xtb()
    key = parsed["account_key"]
    return data, data["accounts"][key], data["cash_ops"][key], data["closed"][key]


def test_first_import(store, parsed):
    r = xtb.import_xtb(parsed, "h1")
    assert r["already_imported"] is False
    assert r["new_cash_ops"] == 4
    assert r["duplicate_cash_ops"] == 0
    assert r["new_closed"] == 1
    assert r["snapshot_status"] == "actualizat"
    assert r["cash_ok"] is True
    assert r["positions_ok"] is True

    data, account, ops, closed = stored(parsed)
    assert account["currency"] == "EUR"
    assert account["label"] == "XTB EUR"
    assert len(account["positions"]) == 2
    assert account["files"] == ["h1"]
    assert len(ops) == 4
    assert len(closed) == 1
    assert data["isin"]["VWCE.DE"] == "IE00BK5BQT80"


def test_same_file_twice_changes_nothing(store, parsed):
    xtb.import_xtb(parsed, "h1")
    r = xtb.import_xtb(parsed, "h1")
    assert r["already_imported"] is True
    assert r["new_cash_ops"] == 0
    assert r["snapshot_status"] == "identic"

    _, account, ops, closed = stored(parsed)
    assert account["files"] == ["h1"]
    assert len(ops) == 4 and len(closed) == 1


def test_other_file_same_content_is_deduplicated(store, parsed):
    xtb.import_xtb(parsed, "h1")
    r = xtb.import_xtb(parsed, "h2")
    assert r["already_imported"] is False
    assert r["new_cash_ops"] == 0
    assert r["duplicate_cash_ops"] == 4
    assert r["new_closed"] == 0
    assert r["duplicate_closed"] == 1
    assert r["snapshot_status"] == "identic"

    _, account, ops, closed = stored(parsed)
    assert account["files"] == ["h1", "h2"]
    assert len(ops) == 4 and len(closed) == 1


def test_new_operation_is_added_without_duplicating_old_ones(store, parsed):
    xtb.import_xtb(parsed, "h1")
    extra = [["Deposit", None, None, None, datetime(2025, 9, 20), 500.0, 5, "Deposit", None]]
    bigger = xtb.parse_xtb_file(make_report(extra_cash=extra))
    assert bigger["account_key"] == parsed["account_key"]

    r = xtb.import_xtb(bigger, "h2")
    assert r["new_cash_ops"] == 1
    assert r["duplicate_cash_ops"] == 4

    _, _, ops, _ = stored(parsed)
    assert len(ops) == 5
    assert sum(o["amount"] for o in ops.values()) == pytest.approx(1227.5)


def test_older_report_does_not_overwrite_snapshot(store, parsed):
    xtb.import_xtb(parsed, "h1")
    older = copy.deepcopy(parsed)
    older["report_time"] = (datetime.fromisoformat(parsed["report_time"]) - timedelta(days=1)).isoformat()
    older["positions"] = []

    r = xtb.import_xtb(older, "h2")
    assert r["snapshot_status"] == "ignorat: mai vechi"

    _, account, _, _ = stored(parsed)
    assert account["report_time"] == parsed["report_time"]
    assert len(account["positions"]) == 2


def test_report_flags_inconsistent_totals(store, parsed):
    bad = copy.deepcopy(parsed)
    bad["checks"]["total_row"] = 999.0
    r = xtb.import_xtb(bad, "h9")
    assert r["cash_ok"] is False


def test_import_does_not_leak_into_another_store(tmp_path, monkeypatch, parsed):
    monkeypatch.setattr(xtb, "XTB_FILE", str(tmp_path / "a.json"))
    xtb.import_xtb(parsed, "h1")
    monkeypatch.setattr(xtb, "XTB_FILE", str(tmp_path / "b.json"))
    data = xtb.load_xtb()
    assert data["accounts"] == {}
    assert data["cash_ops"] == {}
