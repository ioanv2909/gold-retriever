import hashlib
import re
import warnings

import pandas as pd

from core import XTB_FILE, load_json_file, update_json_file


warnings.filterwarnings(
    "ignore",
    message="Workbook contains no default style",
    category=UserWarning,
    module="openpyxl.*",
)


_DEFAULT_XTB_DATA = {"accounts": {}, "cash_ops": {}, "closed": {}, "isin": {}}
_ALLOWED_CASH_TYPES = {
    "Deposit",
    "Withdrawal",
    "Dividend",
    "Withholding tax",
    "Free funds interest",
    "Free funds interest tax",
    "Stock purchase",
    "Stock sale",
}
_STOCK_PURCHASE_RE = re.compile(
    r"OPEN\s+BUY\s+(?P<ticker>[A-Z0-9._-]+)\s+"
    r"(?P<part>\d+)\s*/\s*(?P<total>\d+)\s*@\s*(?P<price>[-+]?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def load_xtb():
    return load_json_file(XTB_FILE, dict(_DEFAULT_XTB_DATA))


def valid_isin(s):
    value = str(s or "").strip().upper()
    return not value or bool(_ISIN_RE.fullmatch(value))


def save_isin(ticker, isin):
    normalized_isin = str(isin or "").strip().upper()

    if not normalized_isin:
        def updater(data):
            data = _normalize_xtb_data(data)
            data["isin"].pop(ticker, None)
            return data

        update_json_file(XTB_FILE, dict(_DEFAULT_XTB_DATA), updater)
        return True, "ISIN șters"

    if not valid_isin(normalized_isin):
        return False, "ISIN invalid"

    def updater(data):
        data = _normalize_xtb_data(data)
        data["isin"][ticker] = normalized_isin
        return data

    update_json_file(XTB_FILE, dict(_DEFAULT_XTB_DATA), updater)
    return True, "ISIN salvat"


def first_purchase_times(account_key):
    data = _normalize_xtb_data(load_xtb())
    operations = data["cash_ops"].get(account_key) or {}
    first_by_ticker = {}

    for operation in operations.values():
        if operation.get("type") != "Stock purchase":
            continue

        ticker = operation.get("ticker")
        purchase_time = operation.get("time")
        if not ticker or _is_empty(purchase_time):
            continue

        current = first_by_ticker.get(ticker)
        if current is None or _compare_iso(purchase_time, current) < 0:
            first_by_ticker[ticker] = purchase_time

    return first_by_ticker


def accounts_summary():
    data = _normalize_xtb_data(load_xtb())
    summaries = []

    for account_key, account in data["accounts"].items():
        summary = account.get("summary") or {}
        cash_ops = data["cash_ops"].get(account_key, {})
        positions = account.get("positions") or []

        summaries.append(
            {
                "account_key": account_key,
                "label": account.get("label"),
                "currency": account.get("currency"),
                "report_time": account.get("report_time"),
                "positions": len(positions),
                "cash_ops": len(cash_ops),
                "value": summary.get("value"),
                "profit": summary.get("profit"),
            }
        )

    return sorted(summaries, key=lambda row: row.get("currency") or "")


def instruments():
    data = _normalize_xtb_data(load_xtb())
    isin_store = data["isin"]
    by_ticker = {}

    for account in data["accounts"].values():
        label = account.get("label")
        for position in account.get("positions") or []:
            ticker = position.get("ticker")
            if not ticker:
                continue

            instrument = by_ticker.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "name": position.get("instrument"),
                    "category": position.get("category"),
                    "isin": isin_store.get(ticker),
                    "accounts": [],
                },
            )

            if not instrument.get("name") and position.get("instrument"):
                instrument["name"] = position.get("instrument")
            if not instrument.get("category") and position.get("category"):
                instrument["category"] = position.get("category")
            if label and label not in instrument["accounts"]:
                instrument["accounts"].append(label)

    for instrument in by_ticker.values():
        instrument["accounts"].sort()

    return sorted(by_ticker.values(), key=lambda row: row["ticker"])


def remove_account(account_key):
    removed = False

    def updater(data):
        nonlocal removed
        data = _normalize_xtb_data(data)
        removed = account_key in data["accounts"]
        data["accounts"].pop(account_key, None)
        data["cash_ops"].pop(account_key, None)
        data["closed"].pop(account_key, None)
        return data

    update_json_file(XTB_FILE, dict(_DEFAULT_XTB_DATA), updater)
    return removed


def parse_xtb_file(file_like):
    open_positions = _read_sheet(file_like, "Open Positions")
    cash_operations = _read_sheet(file_like, "Cash Operations")
    closed_positions = _read_sheet(file_like, "Closed Positions")

    currency = _extract_currency(open_positions)
    account = _extract_account(open_positions)
    if account is None:
        account = _extract_account(cash_operations)
    account_key = f"{currency}-{hashlib.sha256(str(account).encode()).hexdigest()[:6]}"

    report_time = _extract_report_time(open_positions)
    summary = _extract_summary(open_positions)
    positions = _extract_positions(open_positions)
    cash_ops, total_row = _extract_cash_ops(cash_operations)
    closed = _extract_closed_positions(closed_positions)

    cash_sum = sum(op["amount"] for op in cash_ops if op.get("amount") is not None)
    positions_value_sum = sum(pos["value"] for pos in positions if pos.get("value") is not None)
    unknown_types = sorted(
        {
            op.get("type")
            for op in cash_ops
            if op.get("type") and op.get("type") not in _ALLOWED_CASH_TYPES
        }
    )

    return {
        "account_key": account_key,
        "currency": currency,
        "report_time": report_time,
        "summary": summary,
        "positions": positions,
        "cash_ops": cash_ops,
        "total_row": total_row,
        "closed": closed,
        "checks": {
            "cash_sum": cash_sum,
            "total_row": total_row,
            "positions_value_sum": positions_value_sum,
            "summary_value": summary["value"],
        },
        "unknown_types": unknown_types,
    }


def import_xtb(parsed, file_hash):
    account_key = parsed["account_key"]
    currency = parsed["currency"]
    label = f"XTB {currency}"
    checks = parsed.get("checks", {})
    total_row = checks.get("total_row")
    cash_sum = checks.get("cash_sum", 0)
    positions_value_sum = checks.get("positions_value_sum", 0)
    summary_value = checks.get("summary_value", 0)

    existing = load_xtb()
    existing_account = existing.get("accounts", {}).get(account_key, {})
    if file_hash in existing_account.get("files", []):
        return _import_report(
            parsed=parsed,
            label=label,
            already_imported=True,
            new_cash_ops=0,
            duplicate_cash_ops=0,
            new_closed=0,
            duplicate_closed=0,
            snapshot_status="identic",
        )

    report_counts = {
        "new_cash_ops": 0,
        "duplicate_cash_ops": 0,
        "new_closed": 0,
        "duplicate_closed": 0,
        "snapshot_status": "actualizat",
    }

    def updater(data):
        data = _normalize_xtb_data(data)
        accounts = data["accounts"]
        cash_ops_store = data["cash_ops"].setdefault(account_key, {})
        closed_store = data["closed"].setdefault(account_key, {})
        isin_store = data["isin"]

        account = accounts.setdefault(
            account_key,
            {
                "currency": currency,
                "label": label,
                "report_time": None,
                "summary": {},
                "positions": [],
                "total_row": None,
                "files": [],
            },
        )

        if file_hash in account.get("files", []):
            report_counts["snapshot_status"] = "identic"
            return data

        account["currency"] = currency
        account["label"] = label

        for op in parsed.get("cash_ops", []):
            op_id = str(op.get("id", ""))
            if op_id in cash_ops_store:
                report_counts["duplicate_cash_ops"] += 1
                continue
            cash_ops_store[op_id] = op
            report_counts["new_cash_ops"] += 1

        for row in parsed.get("closed", []):
            position_id = str(row.get("Position ID") or row.get("position_id") or "")
            if position_id in closed_store:
                report_counts["duplicate_closed"] += 1
                continue
            closed_store[position_id] = row
            report_counts["new_closed"] += 1

        saved_report_time = account.get("report_time")
        parsed_report_time = parsed["report_time"]
        cmp = _compare_iso(parsed_report_time, saved_report_time)
        if saved_report_time and cmp < 0:
            report_counts["snapshot_status"] = "ignorat: mai vechi"
        else:
            report_counts["snapshot_status"] = "identic" if saved_report_time and cmp == 0 else "actualizat"
            account["report_time"] = parsed_report_time
            account["summary"] = parsed.get("summary", {})
            account["positions"] = parsed.get("positions", [])
            account["total_row"] = parsed.get("total_row")

        files = list(account.get("files", []))
        files.append(file_hash)
        account["files"] = files

        _update_isin_map(isin_store, parsed)
        return data

    update_json_file(XTB_FILE, dict(_DEFAULT_XTB_DATA), updater)

    return _import_report(
        parsed=parsed,
        label=label,
        already_imported=False,
        new_cash_ops=report_counts["new_cash_ops"],
        duplicate_cash_ops=report_counts["duplicate_cash_ops"],
        new_closed=report_counts["new_closed"],
        duplicate_closed=report_counts["duplicate_closed"],
        snapshot_status=report_counts["snapshot_status"],
        cash_ok=total_row is None or abs(cash_sum - total_row) < 0.05,
        positions_ok=abs(positions_value_sum - summary_value) < 0.05,
    )


def _read_sheet(file_like, sheet_name):
    if hasattr(file_like, "seek"):
        file_like.seek(0)
    return pd.read_excel(file_like, sheet_name=sheet_name, header=None)


def _normalize_xtb_data(data):
    normalized = dict(_DEFAULT_XTB_DATA)
    if isinstance(data, dict):
        normalized.update(data)
    for key in _DEFAULT_XTB_DATA:
        if not isinstance(normalized.get(key), dict):
            normalized[key] = {}
    return normalized


def _import_report(
    parsed,
    label,
    already_imported,
    new_cash_ops,
    duplicate_cash_ops,
    new_closed,
    duplicate_closed,
    snapshot_status,
    cash_ok=None,
    positions_ok=None,
):
    checks = parsed.get("checks", {})
    if cash_ok is None:
        total_row = checks.get("total_row")
        cash_ok = total_row is None or abs(checks.get("cash_sum", 0) - total_row) < 0.05
    if positions_ok is None:
        positions_ok = abs(checks.get("positions_value_sum", 0) - checks.get("summary_value", 0)) < 0.05

    return {
        "account_key": parsed["account_key"],
        "label": label,
        "currency": parsed["currency"],
        "report_time": parsed["report_time"],
        "already_imported": already_imported,
        "new_cash_ops": new_cash_ops,
        "duplicate_cash_ops": duplicate_cash_ops,
        "new_closed": new_closed,
        "duplicate_closed": duplicate_closed,
        "snapshot_status": snapshot_status,
        "unknown_types": parsed.get("unknown_types", []),
        "checks": checks,
        "cash_ok": cash_ok,
        "positions_ok": positions_ok,
    }


def _extract_account(df):
    row_idx = _find_label_row(df, "Account number")
    if row_idx is None or df.shape[1] < 2:
        return None
    return _json_value(df.iat[row_idx, 1])


def _extract_currency(df):
    metric_col, _, currency_col = _find_metric_columns(df)
    row_idx = _find_label_row(df, "Open position value", col=metric_col)
    if row_idx is None:
        raise ValueError("Currency is missing: 'Open position value' row was not found.")

    currency = _clean_string(_cell(df, row_idx, currency_col))
    if not currency:
        currency = _clean_string(_cell(df, row_idx, 3))
    if not currency:
        raise ValueError("Currency is missing from the 'Open position value' row.")
    return currency


def _extract_report_time(df):
    for row_idx in range(len(df)):
        label = _clean_string(_cell(df, row_idx, 0))
        if label and label.startswith("Data as of report"):
            for col_idx in range(1, df.shape[1]):
                value = _cell(df, row_idx, col_idx)
                if not _is_empty(value):
                    return _to_iso(value)
    raise ValueError("Report time is missing from Open Positions.")


def _extract_summary(df):
    metric_col, value_col, _ = _find_metric_columns(df)
    value = _summary_value(df, "Open position value", metric_col, value_col)
    profit = _summary_value(df, "Open position profit", metric_col, value_col)
    return {"value": value, "profit": profit}


def _summary_value(df, label, metric_col, value_col):
    row_idx = _find_label_row(df, label, col=metric_col)
    if row_idx is None:
        return None
    return _to_float(_cell(df, row_idx, value_col))


def _find_metric_columns(df):
    for row_idx in range(len(df)):
        for col_idx in range(df.shape[1]):
            if _clean_string(_cell(df, row_idx, col_idx)) == "Metric":
                headers = _headers_from_row(df.iloc[row_idx])
                return (
                    col_idx,
                    _find_header_index(headers, ["Value"], default=col_idx + 1),
                    _find_header_index(headers, ["Currency"], default=3),
                )
    return 0, 1, 3


def _extract_positions(df):
    header_idx = _find_table_header(df, "Product", "Instrument/Position")
    if header_idx is None:
        return []

    headers = _headers_from_row(df.iloc[header_idx])
    positions = []
    current = None

    for row_idx in range(header_idx + 1, len(df)):
        row = df.iloc[row_idx]
        if _row_is_empty(row):
            continue

        row_type = _clean_string(_row_value(row, headers, ["Type"]))
        category = _clean_string(_row_value(row, headers, ["Category"]))

        if category and not row_type:
            current = {
                "instrument": _clean_string(_row_value(row, headers, ["Instrument/Position"])),
                "ticker": _clean_string(_row_value(row, headers, ["Ticker"])),
                "category": category,
                "volume": _to_float(_row_value(row, headers, ["Volume"])),
                "value": _to_float(_row_value(row, headers, ["Value", "Market value", "Position value"])),
                "open_price": _to_float(
                    _row_value(row, headers, ["Open price", "Average open price", "Avg open price"])
                ),
                "net_profit": _to_float(
                    _row_value(row, headers, ["Net profit", "Profit", "Profit/Loss", "P/L"])
                ),
                "net_profit_pct": _to_float(
                    _row_value(row, headers, ["Net profit %", "Profit %", "Profit/Loss %", "P/L %"])
                ),
                "lots": [],
                "initial_fill": None,
            }
            isin = _clean_string(_row_value(row, headers, ["ISIN"]))
            if isin:
                current["isin"] = isin
            positions.append(current)
            continue

        if current is not None and row_type.upper() in {"BUY", "SELL"}:
            lot = {
                "position_id": _clean_string(_row_value(row, headers, ["Instrument/Position"])),
                "volume": _to_float(_row_value(row, headers, ["Volume"])),
                "value": _to_float(_row_value(row, headers, ["Value", "Market value", "Position value"])),
                "current_price": _to_float(
                    _row_value(row, headers, ["Current price", "Market price", "Price"])
                ),
                "open_price": _to_float(_row_value(row, headers, ["Open price", "Average open price"])),
                "open_time": _to_iso_or_none(_row_value(row, headers, ["Open time", "Time", "Opening time"])),
            }
            current["lots"].append(lot)
            current["initial_fill"] = _min_iso(current["initial_fill"], lot["open_time"])

    return positions


def _extract_cash_ops(df):
    header_idx = _find_table_header(df, "Type", "Instrument")
    if header_idx is None:
        return [], None

    headers = _headers_from_row(df.iloc[header_idx])
    operations = []
    total_row = None

    for row_idx in range(header_idx + 1, len(df)):
        row = df.iloc[row_idx]
        if _row_is_empty(row):
            continue

        op_type = _clean_string(_row_value(row, headers, ["Type"]))
        if not op_type:
            continue

        amount = _to_float(_row_value(row, headers, ["Amount", "Value"]))
        if op_type == "Total":
            total_row = amount
            continue

        comment = _clean_string(_row_value(row, headers, ["Comment", "Comments"]))
        operation = {
            "type": op_type,
            "instrument": _clean_string(_row_value(row, headers, ["Instrument"])),
            "ticker": _clean_string(_row_value(row, headers, ["Ticker"])),
            "category": _clean_string(_row_value(row, headers, ["Category"])),
            "time": _to_iso_or_none(_row_value(row, headers, ["Time", "Date"])),
            "amount": amount,
            "id": _operation_id(row, headers),
            "comment": comment,
            "position_id": _clean_string(_row_value(row, headers, ["Position ID", "Position Id"])),
        }

        stock_purchase_match = _STOCK_PURCHASE_RE.search(comment or "")
        if op_type == "Stock purchase" and stock_purchase_match:
            operation["stock_purchase"] = {
                "ticker": stock_purchase_match.group("ticker"),
                "part": int(stock_purchase_match.group("part")),
                "total": int(stock_purchase_match.group("total")),
                "price": _to_float(stock_purchase_match.group("price")),
            }
        elif op_type == "Stock purchase":
            operation["stock_purchase"] = {"ticker": None, "part": None, "total": None, "price": None}

        isin = _clean_string(_row_value(row, headers, ["ISIN"]))
        if isin:
            operation["isin"] = isin

        operations.append(operation)

    return operations, total_row


def _extract_closed_positions(df):
    header_idx = _find_table_header(df, "Instrument", "Ticker")
    if header_idx is None:
        return []

    headers = _headers_from_row(df.iloc[header_idx])
    ticker_col = _find_header_index(headers, ["Ticker"])
    if ticker_col is None:
        return []

    rows = []
    for row_idx in range(header_idx + 1, len(df)):
        row = df.iloc[row_idx]
        if _row_is_empty(row):
            continue
        ticker = _clean_string(row.iloc[ticker_col])
        if not ticker:
            continue

        row_dict = {}
        for col_idx, header in enumerate(headers):
            if header:
                row_dict[header] = _json_value(row.iloc[col_idx])
        position_id = _clean_string(row_dict.get("Position ID"))
        if not position_id:
            position_id = hashlib.sha256(repr(row_dict).encode()).hexdigest()[:16]
            row_dict["Position ID"] = position_id
        row_dict["position_id"] = position_id
        rows.append(row_dict)

    return rows


def _operation_id(row, headers):
    value = _row_value(row, headers, ["ID", "Id"])
    op_id = _clean_string(value)
    if op_id:
        return op_id

    normalized = [_json_value(value) for value in row.tolist()]
    return hashlib.sha256(repr(normalized).encode()).hexdigest()[:16]


def _update_isin_map(isin_store, parsed):
    for position in parsed.get("positions", []):
        ticker = position.get("ticker")
        isin = position.get("isin")
        if ticker and isin:
            isin_store[ticker] = isin

    for op in parsed.get("cash_ops", []):
        ticker = op.get("ticker")
        isin = op.get("isin")
        if ticker and isin:
            isin_store[ticker] = isin

    for row in parsed.get("closed", []):
        ticker = row.get("Ticker") or row.get("ticker")
        isin = row.get("ISIN") or row.get("isin")
        if ticker and isin:
            isin_store[ticker] = isin


def _find_table_header(df, first_col_value, second_col_value):
    for row_idx in range(len(df)):
        first = _clean_string(_cell(df, row_idx, 0))
        second = _clean_string(_cell(df, row_idx, 1))
        if first == first_col_value and second == second_col_value:
            return row_idx
    return None


def _find_label_row(df, label, col=0):
    for row_idx in range(len(df)):
        if _clean_string(_cell(df, row_idx, col)) == label:
            return row_idx
    return None


def _headers_from_row(row):
    headers = []
    seen = {}
    for value in row.tolist():
        header = _clean_string(value)
        if header:
            count = seen.get(header, 0)
            seen[header] = count + 1
            if count:
                header = f"{header} {count + 1}"
        headers.append(header)
    return headers


def _find_header_index(headers, candidates, default=None):
    for candidate in candidates:
        if candidate in headers:
            return headers.index(candidate)

    normalized = {_normalize_header(header): idx for idx, header in enumerate(headers) if header}
    for candidate in candidates:
        idx = normalized.get(_normalize_header(candidate))
        if idx is not None:
            return idx

    return default


def _row_value(row, headers, candidates):
    col_idx = _find_header_index(headers, candidates)
    if col_idx is None or col_idx >= len(row):
        return None
    return row.iloc[col_idx]


def _cell(df, row_idx, col_idx):
    if row_idx < 0 or col_idx < 0 or row_idx >= len(df) or col_idx >= df.shape[1]:
        return None
    return df.iat[row_idx, col_idx]


def _row_is_empty(row):
    return all(_is_empty(value) for value in row.tolist())


def _is_empty(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def _clean_string(value):
    if _is_empty(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_header(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _to_float(value):
    if _is_empty(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace("%", "").replace("\u00a0", " ").strip()
    text = re.sub(r"[^\d,.\-+]", "", text)

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    if not text:
        return None

    number = float(text)
    return -number if negative else number


def _to_iso_or_none(value):
    if _is_empty(value):
        return None
    return _to_iso(value)


def _to_iso(value):
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()

    parsed = pd.to_datetime(value, errors="coerce")
    if not pd.isna(parsed):
        return parsed.isoformat()

    text = _clean_string(value)
    if not text:
        return None
    return text


def _min_iso(left, right):
    if not left:
        return right
    if not right:
        return left
    return left if _compare_iso(left, right) <= 0 else right


def _compare_iso(left, right):
    if not right:
        return 1
    if not left:
        return -1

    left_dt = pd.to_datetime(left, errors="coerce")
    right_dt = pd.to_datetime(right, errors="coerce")
    if not pd.isna(left_dt) and not pd.isna(right_dt):
        if left_dt < right_dt:
            return -1
        if left_dt > right_dt:
            return 1
        return 0

    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _json_value(value):
    if _is_empty(value):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    if isinstance(value, float):
        return float(value)
    if isinstance(value, int):
        return int(value)
    return value
