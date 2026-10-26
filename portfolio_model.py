import time

import pandas as pd

from t212_api import fetch_fx_rate, load_cached_snapshot
from xtb import load_xtb
from xtb_positions import xtb_rows
from yahoo import resolve_yahoo_symbol


_FX_CACHE_TTL_SECONDS = 600
_FX_CACHE = {}


def fx(from_ccy, to_ccy):
    if from_ccy == to_ccy:
        return 1.0

    key = (from_ccy, to_ccy)
    now = time.time()
    cached = _FX_CACHE.get(key)

    if cached is not None:
        timestamp, value = cached
        if now - timestamp < _FX_CACHE_TTL_SECONDS:
            return value

    rate, err = fetch_fx_rate(from_ccy, to_ccy)
    if err and "USD" not in (from_ccy, to_ccy):
        r1, e1 = fetch_fx_rate(from_ccy, "USD")
        r2, e2 = fetch_fx_rate("USD", to_ccy)
        if not e1 and not e2:
            rate, err = r1 * r2, None
    value = float(rate)
    # un curs esuat (1.0) se tine doar un minut, ca urmatoarele apeluri sa reincerce
    _FX_CACHE[key] = (now - (_FX_CACHE_TTL_SECONDS - 60 if err else 0), value)
    return value


def portfolio_options():
    accounts = (load_xtb().get("accounts") or {}).items()
    xtb_labels = [
        account.get("label") or account_key
        for account_key, account in sorted(
            accounts,
            key=lambda item: ((item[1].get("currency") or ""), (item[1].get("label") or item[0])),
        )
    ]

    return ["Trading 212"] + xtb_labels


def default_currency(portfolios, t212_account_currency):
    selected = list(portfolios or [])

    if len(selected) != 1:
        return t212_account_currency

    account = _xtb_accounts_by_label().get(selected[0])
    if account is None:
        return t212_account_currency

    return account.get("currency") or t212_account_currency


def build_rows(t212_df, display_ccy, portfolios, t212_account_currency):
    selected = set(portfolios or [])
    rows = []

    if "Trading 212" in selected:
        rows.extend(_t212_rows(t212_df, display_ccy, t212_account_currency))

    rows.extend(_selected_xtb_rows(selected, display_ccy))

    if len(selected) > 1:
        rows = _merge_rows(rows)

    rows = [_with_metrics(row) for row in rows]
    rows.sort(key=lambda row: (row.get("name") or "").casefold())

    return pd.DataFrame(rows)


def _t212_rows(t212_df, display_ccy, t212_account_currency):
    if t212_df is None or t212_df.empty:
        return []

    instruments_by_ticker = _instruments_by_ticker()
    factor = fx(t212_account_currency, display_ccy)
    rows = []

    for _, item in t212_df.iterrows():
        source = item.to_dict()
        ticker = source.get("ticker")
        instrument = instruments_by_ticker.get(ticker) or {}
        fx_rate = _to_float(source.get("fx_rate"))

        rows.append(
            {
                "source": "T212",
                "accounts": "Trading 212",
                "ticker": ticker,
                "tickers": [ticker] if ticker else [],
                "yahoo_symbol": resolve_yahoo_symbol(ticker) if ticker else None,
                "isin": instrument.get("isin"),
                "name": source.get("name"),
                "type": instrument.get("type") or instrument.get("instrumentType"),
                "quantity": _to_float(source.get("quantity")),
                "averagePrice": _to_float(source.get("averagePrice")),
                "currentPrice": _to_float(source.get("currentPrice")),
                "currencyCode": source.get("currencyCode"),
                "initialFillDate": source.get("initialFillDate"),
                "value_disp": _multiply(source.get("valoare_curenta"), fx_rate, factor),
                "cost_disp": _t212_cost_disp(source, fx_rate, factor),
                "pl_disp": _multiply(source.get("ppl"), factor),
                "div_disp": _multiply(source.get("dividende_incasate"), factor),
            }
        )

    return rows


def _t212_cost_disp(source, fx_rate, factor):
    value_account = _multiply(source.get("valoare_curenta"), fx_rate)
    pl_account = _to_float(source.get("ppl"))

    if value_account is None or pl_account is None:
        return None

    return _multiply(value_account - pl_account, factor)


def _selected_xtb_rows(selected, display_ccy):
    rows = []

    for source in xtb_rows():
        account = source.get("account")
        if account not in selected:
            continue

        factor = fx(source.get("account_currency"), display_ccy)

        rows.append(
            {
                "source": "XTB",
                "accounts": account,
                "ticker": source.get("ticker"),
                "tickers": [source.get("ticker")] if source.get("ticker") else [],
                "yahoo_symbol": source.get("yahoo_symbol"),
                "isin": source.get("isin"),
                "name": source.get("name"),
                "type": source.get("type"),
                "quantity": _to_float(source.get("quantity")),
                "averagePrice": _to_float(source.get("averagePrice")),
                "currentPrice": _to_float(source.get("currentPrice")),
                "currencyCode": source.get("currencyCode"),
                "initialFillDate": source.get("initialFillDate"),
                "value_disp": _multiply(source.get("value_account"), factor),
                "cost_disp": _multiply(source.get("cost_account"), factor),
                "pl_disp": _multiply(source.get("pl_account"), factor),
                "div_disp": _multiply(source.get("dividends_account"), factor),
            }
        )

    return rows


def _merge_rows(rows):
    grouped = {}

    for index, row in enumerate(rows):
        group_key = row.get("isin") or row.get("yahoo_symbol") or f"__row_{index}"
        grouped.setdefault(group_key, []).append(row)

    return [_merge_group(group) for group in grouped.values()]


def _merge_group(group):
    t212_row = next((row for row in group if row.get("source") == "T212"), None)
    preferred_row = t212_row or group[0]
    has_t212 = any(row.get("source") == "T212" for row in group)
    has_xtb = any(row.get("source") == "XTB" for row in group)
    currency_codes = {row.get("currencyCode") for row in group}

    if has_t212 and has_xtb:
        source = "T212+XTB"
    elif has_t212:
        source = "T212"
    else:
        source = "XTB"

    merged = {
        "source": source,
        "accounts": ", ".join(_unique(row.get("accounts") for row in group)),
        "ticker": preferred_row.get("ticker"),
        "tickers": _unique(ticker for row in group for ticker in (row.get("tickers") or [])),
        "yahoo_symbol": preferred_row.get("yahoo_symbol"),
        "isin": preferred_row.get("isin"),
        "name": preferred_row.get("name"),
        "type": preferred_row.get("type"),
        "quantity": _sum_optional(row.get("quantity") for row in group),
        "initialFillDate": _min_present(row.get("initialFillDate") for row in group),
        "value_disp": _sum_optional(row.get("value_disp") for row in group),
        "cost_disp": _sum_optional(row.get("cost_disp") for row in group),
        "pl_disp": _sum_optional(row.get("pl_disp") for row in group),
        "div_disp": _sum_optional(row.get("div_disp") for row in group),
    }

    if len(currency_codes) == 1:
        merged["currencyCode"] = next(iter(currency_codes))
        merged["averagePrice"] = _weighted_average(
            (row.get("averagePrice"), row.get("quantity")) for row in group
        )
        largest_quantity_row = max(group, key=lambda row: _to_float(row.get("quantity")) or 0.0)
        merged["currentPrice"] = largest_quantity_row.get("currentPrice")
    else:
        merged["currencyCode"] = "mixt"
        merged["averagePrice"] = None
        merged["currentPrice"] = None

    return merged


def _with_metrics(row):
    result = dict(row)
    members = result.pop("members", None)
    result["members"] = members or [dict(row)]

    average_price = _to_float(result.get("averagePrice"))
    current_price = _to_float(result.get("currentPrice"))
    value_disp = _to_float(result.get("value_disp"))
    cost_disp = _to_float(result.get("cost_disp"))
    div_disp = _to_float(result.get("div_disp"))

    if average_price and current_price is not None:
        result["randament_%"] = (current_price / average_price - 1) * 100
    elif cost_disp:
        result["randament_%"] = (value_disp / cost_disp - 1) * 100 if value_disp is not None else None
    else:
        result["randament_%"] = None

    result["div_pe_investit_%"] = (div_disp / cost_disp * 100) if cost_disp and div_disp is not None else None

    if result["randament_%"] is not None and result["div_pe_investit_%"] is not None:
        result["randament_total_%"] = result["randament_%"] + result["div_pe_investit_%"]
    else:
        result["randament_total_%"] = None

    return result


def _xtb_accounts_by_label():
    accounts = load_xtb().get("accounts") or {}
    return {
        account.get("label") or account_key: account
        for account_key, account in accounts.items()
    }


def _instruments_by_ticker():
    snapshot = load_cached_snapshot() or {}
    instruments = snapshot.get("instruments") or []

    if isinstance(instruments, dict):
        instruments = instruments.values()

    return {
        instrument.get("ticker"): instrument
        for instrument in instruments
        if isinstance(instrument, dict) and instrument.get("ticker")
    }


def _multiply(*values):
    result = 1.0

    for value in values:
        number = _to_float(value)
        if number is None:
            return None
        result *= number

    return result


def _sum_optional(values):
    total = 0.0
    found = False

    for value in values:
        number = _to_float(value)
        if number is None:
            continue
        total += number
        found = True

    return total if found else None


def _weighted_average(values):
    weighted_sum = 0.0
    weight_sum = 0.0

    for value, weight in values:
        number = _to_float(value)
        quantity = _to_float(weight)

        if number is None or quantity is None:
            continue

        weighted_sum += number * quantity
        weight_sum += quantity

    return weighted_sum / weight_sum if weight_sum else None


def _min_present(values):
    present = [value for value in values if value]
    return min(present) if present else None


def _unique(values):
    result = []
    seen = set()

    for value in values:
        if value is None or value in seen:
            continue
        result.append(value)
        seen.add(value)

    return result


def _to_float(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return None if number != number else number
