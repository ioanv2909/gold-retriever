import re
from datetime import datetime, timezone

from isin_tools import resolve_isin
from t212_api import fetch_fx_rate
from xtb import first_purchase_times, load_xtb
from xtb_prices import load_xtb_prices
from yahoo import resolve_yahoo_symbol


_DIVIDEND_TYPES = {"Dividend", "Withholding tax"}
_PRICE_STATUSES = {"ok", "mismatch"}


def xtb_rows():
    xtb_data = load_xtb()
    prices_data = (load_xtb_prices().get("data") or {})
    isin_map = xtb_data.get("isin") or {}
    cash_ops = xtb_data.get("cash_ops") or {}
    fx_cache = {}
    rows = []

    for account_key, account in (xtb_data.get("accounts") or {}).items():
        account_currency = account.get("currency")
        first_purchase_by_ticker = first_purchase_times(account_key)

        for group in account.get("positions") or []:
            ticker = group.get("ticker")
            initial_fill = group.get("initial_fill") or first_purchase_by_ticker.get(ticker)
            isin = isin_map.get(ticker)
            name = _resolve_name(isin) or group.get("instrument")
            price_info = prices_data.get(ticker) or {}
            current_price, currency_code, price_ok = _current_price(group, price_info)
            quantity = _to_float(group.get("volume"))
            report_value_account = _to_float(group.get("value"))
            cost_account = _subtract(group.get("value"), group.get("net_profit"))

            if price_ok:
                fx_rate = _fetch_fx_rate_cached(currency_code, account_currency, fx_cache)
                value_account = _multiply(quantity, current_price, fx_rate)
            else:
                value_account = report_value_account

            rows.append(
                {
                    "source": "XTB",
                    "account": account.get("label"),
                    "account_key": account_key,
                    "account_currency": account_currency,
                    "ticker": ticker,
                    "yahoo_symbol": resolve_yahoo_symbol(ticker),
                    "isin": isin,
                    "name": name,
                    "type": _position_type(group.get("category")),
                    "category": group.get("category"),
                    "quantity": quantity,
                    "averagePrice": _to_float(group.get("open_price")),
                    "initialFillDate": _utc_iso(initial_fill),
                    "currentPrice": current_price,
                    "currencyCode": currency_code,
                    "price_ok": price_ok,
                    "cost_account": cost_account,
                    "value_account": value_account,
                    "pl_account": _subtract(value_account, cost_account),
                    "report_value_account": report_value_account,
                    "dividends_account": _dividends_for_ticker(cash_ops.get(account_key) or {}, ticker),
                    "report_time": account.get("report_time"),
                }
            )

    return sorted(rows, key=lambda row: (row.get("name") or "", row.get("ticker") or ""))


def xtb_holdings(ticker, isin=None, yahoo_symbol=None):
    xtb_data = load_xtb()
    holdings = []

    for row in xtb_rows():
        if not _matches_holding(row, ticker, isin, yahoo_symbol):
            continue

        account_key = row.get("account_key")
        instrument_ticker = row.get("ticker")
        account = (xtb_data.get("accounts") or {}).get(account_key) or {}
        group = _account_position_group(account, instrument_ticker)
        account_cash_ops = ((xtb_data.get("cash_ops") or {}).get(account_key) or {})

        holdings.append(
            {
                "account": row.get("account"),
                "account_key": account_key,
                "account_currency": row.get("account_currency"),
                "report_time": row.get("report_time"),
                "ticker": instrument_ticker,
                "quantity": row.get("quantity"),
                "averagePrice": row.get("averagePrice"),
                "currencyCode": row.get("currencyCode"),
                "currentPrice": row.get("currentPrice"),
                "cost_account": row.get("cost_account"),
                "value_account": row.get("value_account"),
                "pl_account": row.get("pl_account"),
                "dividends_account": row.get("dividends_account"),
                "price_ok": row.get("price_ok"),
                "lots": _holding_lots(group),
                "purchases": _purchase_events(account_cash_ops, instrument_ticker, group),
                "dividend_events": _dividend_events(account_cash_ops, instrument_ticker),
            }
        )

    return holdings


def _matches_holding(row, ticker, isin, yahoo_symbol):
    return (
        row.get("ticker") == ticker
        or (isin is not None and row.get("isin") == isin)
        or (yahoo_symbol is not None and row.get("yahoo_symbol") == yahoo_symbol)
    )


def _account_position_group(account, ticker):
    for group in account.get("positions") or []:
        if group.get("ticker") == ticker:
            return group
    return {}


def _holding_lots(group):
    lots = [
        {
            "position_id": lot.get("position_id"),
            "open_time": lot.get("open_time"),
            "volume": lot.get("volume"),
            "open_price": lot.get("open_price"),
            "value": lot.get("value"),
        }
        for lot in group.get("lots") or []
    ]
    return sorted(lots, key=lambda lot: _time_sort_key(lot.get("open_time")))


def _purchase_events(account_cash_ops, ticker, group):
    purchase_comment_pattern = re.compile(
        r"OPEN BUY\s+(?:[A-Za-z][A-Za-z0-9.\-]*\s+)?([\d.]+)(?:/([\d.]+))?\s*@\s*([\d.]+)"
    )
    tolerance = 1e-6
    max_group_gap_seconds = 10 * 60
    lot_position_ids = {lot.get("position_id") for lot in group.get("lots") or []}
    purchase_groups = []

    def parsed_time(value):
        if not value:
            return None

        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)

        return parsed

    def is_within_group_window(previous_time, current_time):
        previous = parsed_time(previous_time)
        current = parsed_time(current_time)

        if previous is None or current is None:
            return False

        delta_seconds = (current - previous).total_seconds()
        return 0 <= delta_seconds <= max_group_gap_seconds

    def new_purchase_group(operation, total):
        return {
            "position_id": operation.get("position_id"),
            "time": operation.get("time"),
            "amount": 0.0,
            "_total": total,
            "_part_sum": 0.0,
            "_price_weighted_sum": 0.0,
            "_matched_parts": 0.0,
            "_last_time": operation.get("time"),
            "_operation_count": 0.0,
        }

    def add_operation(purchase_group, operation, match):
        operation_time = operation.get("time")
        operation_position_id = operation.get("position_id")

        if _time_sort_key(operation_time) < _time_sort_key(purchase_group.get("time")):
            purchase_group["time"] = operation_time

        if purchase_group.get("position_id") not in lot_position_ids and operation_position_id in lot_position_ids:
            purchase_group["position_id"] = operation_position_id

        purchase_group["amount"] += _to_float(operation.get("amount")) or 0.0
        purchase_group["_last_time"] = operation_time
        purchase_group["_operation_count"] += 1.0

        if match is None:
            return

        part = float(match.group(1))
        price = float(match.group(3))
        purchase_group["_part_sum"] += part
        purchase_group["_price_weighted_sum"] += part * price
        purchase_group["_matched_parts"] += 1.0

    def last_open_group(total, operation_time):
        for purchase_group in reversed(purchase_groups):
            if purchase_group.get("_total") is None:
                continue
            if abs(purchase_group["_total"] - total) > tolerance:
                continue
            if purchase_group["_part_sum"] >= purchase_group["_total"] - tolerance:
                continue
            if not is_within_group_window(purchase_group.get("_last_time"), operation_time):
                continue

            return purchase_group

        return None

    operations = sorted(
        (
            operation
            for operation in account_cash_ops.values()
            if operation.get("type") == "Stock purchase" and operation.get("ticker") == ticker
        ),
        key=lambda operation: _time_sort_key(operation.get("time")),
    )

    for operation in operations:
        match = purchase_comment_pattern.search(str(operation.get("comment") or ""))

        if match is None:
            purchase_group = new_purchase_group(operation, None)
            purchase_groups.append(purchase_group)
            add_operation(purchase_group, operation, None)
            continue

        total = float(match.group(2)) if match.group(2) is not None else None
        purchase_group = last_open_group(total, operation.get("time")) if total is not None else None

        if purchase_group is None:
            purchase_group = new_purchase_group(operation, total)
            purchase_groups.append(purchase_group)

        add_operation(purchase_group, operation, match)

    purchases = []
    for purchase_group in purchase_groups:
        total = purchase_group.get("_total")
        volume = total if total is not None else purchase_group["_part_sum"]
        price = None

        if purchase_group["_matched_parts"] > 0.0 and purchase_group["_part_sum"] != 0.0:
            price = purchase_group["_price_weighted_sum"] / purchase_group["_part_sum"]

        purchases.append(
            {
                "position_id": purchase_group.get("position_id"),
                "time": purchase_group.get("time"),
                "volume": float(volume or 0.0),
                "price": price,
                "amount": float(purchase_group.get("amount") or 0.0),
                "parts": float(purchase_group.get("_operation_count") or 0.0),
            }
        )

    return sorted(purchases, key=lambda purchase: _time_sort_key(purchase.get("time")))


def _dividend_events(account_cash_ops, ticker):
    events = [
        {
            "time": operation.get("time"),
            "type": operation.get("type"),
            "amount": operation.get("amount"),
        }
        for operation in account_cash_ops.values()
        if operation.get("ticker") == ticker and operation.get("type") in _DIVIDEND_TYPES
    ]
    return sorted(events, key=lambda event: _time_sort_key(event.get("time")))


def _time_sort_key(value):
    return value is None, str(value or "")


def _resolve_name(isin):
    if not isin:
        return None

    resolved = resolve_isin(isin) or {}
    return resolved.get("name")


def _position_type(category):
    text = str(category or "").upper()
    if "ETF" in text or "ETC" in text:
        return "ETF"
    if "STOCK" in text:
        return "STOCK"
    return None


def _current_price(group, price_info):
    if price_info.get("status") in _PRICE_STATUSES and price_info.get("price") is not None:
        return _to_float(price_info.get("price")), price_info.get("currency"), True

    return _first_lot_current_price(group), None, False


def _first_lot_current_price(group):
    for lot in group.get("lots") or []:
        current_price = _to_float(lot.get("current_price"))
        if current_price is not None:
            return current_price
    return None


def _fetch_fx_rate_cached(from_ccy, to_ccy, fx_cache):
    key = (from_ccy, to_ccy)
    if key not in fx_cache:
        fx_cache[key] = fetch_fx_rate(from_ccy, to_ccy)[0]
    return fx_cache[key]


def _dividends_for_ticker(account_cash_ops, ticker):
    total = 0.0

    for operation in account_cash_ops.values():
        if operation.get("ticker") != ticker or operation.get("type") not in _DIVIDEND_TYPES:
            continue

        amount = _to_float(operation.get("amount"))
        if amount is not None:
            total += amount

    return total


def _utc_iso(value):
    if not value:
        return None

    text = str(value)
    if text.endswith("Z"):
        return f"{text[:-1]}+00:00"
    if (
        len(text) >= 6
        and text[-6] in "+-"
        and text[-5:-3].isdigit()
        and text[-3] == ":"
        and text[-2:].isdigit()
    ):
        return text
    if len(text) >= 5 and text[-5] in "+-" and text[-4:].isdigit():
        return text
    return f"{text}+00:00"


def _multiply(*values):
    result = 1.0

    for value in values:
        number = _to_float(value)
        if number is None:
            return None
        result *= number

    return result


def _subtract(left, right):
    left_number = _to_float(left)
    right_number = _to_float(right)

    if left_number is None or right_number is None:
        return None

    return left_number - right_number


def _to_float(value):
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return None if number != number else number
