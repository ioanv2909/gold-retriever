import re
import time


_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_T212_INDEX_TTL = 10 * 60
_T212_INDEX_CACHE = {}  # utilizator -> (timp, index)


def isin_checksum_ok(isin):
    normalized = _normalize_isin(isin)
    if not _ISIN_RE.fullmatch(normalized):
        return False

    expanded_body = "".join(_isin_char_digits(char) for char in normalized[:11])
    expected_check_digit = _luhn_check_digit(expanded_body)
    return expected_check_digit == int(normalized[11])


def t212_index():
    from userctx import current_user
    uk = current_user() or ""
    now = time.time()
    hit = _T212_INDEX_CACHE.get(uk)
    if hit is not None and now - hit[0] < _T212_INDEX_TTL:
        return hit[1]

    snapshot = _load_cached_snapshot() or {}
    instruments = snapshot.get("instruments") or []
    positions = snapshot.get("positions") or []
    held_tickers = {
        str(position.get("ticker")).strip()
        for position in positions
        if position.get("ticker")
    }

    index = {}
    for instrument in instruments:
        isin = _normalize_isin(instrument.get("isin"))
        ticker = _clean_string(instrument.get("ticker"))
        if not isin or not ticker:
            continue

        entry = {
            "ticker": ticker,
            "name": _clean_string(instrument.get("name")),
            "type": _clean_string(instrument.get("type")),
            "currencyCode": _clean_string(instrument.get("currencyCode")),
            "shortName": _clean_string(instrument.get("shortName")),
            "held": ticker in held_tickers,
        }
        index.setdefault(isin, []).append(entry)

    _T212_INDEX_CACHE[uk] = (now, index)
    return index


def resolve_isin(isin):
    normalized = _normalize_isin(isin)
    t212_matches = t212_index().get(normalized, [])
    justetf_entry = _get_justetf_entry(normalized)

    source = None
    name = None
    if t212_matches:
        source = "T212"
        name = _first_non_empty(
            match.get("name") or match.get("shortName")
            for match in t212_matches
        )
    elif justetf_entry:
        source = "justETF"
        name = justetf_entry.get("name")

    return {
        "name": name,
        "source": source,
        "t212": t212_matches,
        "justetf": justetf_entry,
    }


def isin_issues(ticker, isin, category=None, batch=None):
    normalized_ticker = _clean_string(ticker)
    normalized_isin = _normalize_isin(isin)
    issues = []

    if not _ISIN_RE.fullmatch(normalized_isin):
        issues.append(("error", "Format ISIN invalid."))
    elif not isin_checksum_ok(normalized_isin):
        issues.append(("error", "Cifră de control ISIN invalidă."))

    xtb_data = _load_xtb()
    ticker_accounts = _xtb_ticker_accounts(xtb_data, normalized_ticker)
    saved_isins = xtb_data.get("isin") or {}
    batch = batch or {}

    _add_batch_issues(issues, normalized_ticker, normalized_isin, ticker_accounts, xtb_data, batch)
    _add_saved_isin_issues(issues, normalized_ticker, normalized_isin, ticker_accounts, xtb_data, saved_isins)

    resolved = resolve_isin(normalized_isin)
    t212_matches = resolved["t212"]
    justetf_entry = resolved["justetf"]

    if t212_matches:
        t212_name = _first_non_empty(
            match.get("name") or match.get("shortName")
            for match in t212_matches
        )
        held_tickers = [
            match.get("ticker")
            for match in t212_matches
            if match.get("held") and match.get("ticker")
        ]

        if held_tickers:
            issues.append((
                "info",
                f"coincide cu poziția deținută în Trading 212: {', '.join(held_tickers)} — {t212_name}; se vor comasa în vizualizarea combinată",
            ))
        else:
            listing_count = len(t212_matches)
            tickers = [
                match.get("ticker")
                for match in t212_matches
                if match.get("ticker")
            ]
            ticker_suffix = " ..." if listing_count > 3 else ""
            issues.append((
                "info",
                f"există în Trading 212 pe {listing_count} listări (niciuna deținută): {', '.join(tickers[:3])}{ticker_suffix} — {t212_name}",
            ))

    if normalized_isin and not t212_matches and not justetf_entry:
        issues.append(("warning", "ISIN-ul nu a fost găsit nici în Trading 212, nici în justETF."))

    _add_category_issues(issues, category, t212_matches, justetf_entry)

    if resolved["name"] and resolved["source"]:
        issues.append(("info", f"ISIN → {resolved['name']} ({resolved['source']})"))

    return issues


def suggest_isin(ticker, category):
    base = _ticker_base(ticker)
    category_kind = _category_kind(category)
    if not base or category_kind not in {"ETF", "STOCK"}:
        return None

    t212_candidates = []
    for isin, entries in t212_index().items():
        for entry in entries:
            if (
                _same_text(entry.get("shortName"), base)
                and _t212_type_kind(entry.get("type")) == category_kind
            ):
                t212_candidates.append((isin, entry))

    candidate_isins = {isin for isin, _ in t212_candidates}
    if len(candidate_isins) == 1:
        isin, entry = t212_candidates[0]
        return {
            "isin": isin,
            "name": entry.get("name") or entry.get("shortName"),
            "source": "T212",
        }

    if category_kind != "ETF":
        return None

    justetf_matches = []
    for isin, entry in _justetf_cache_data().items():
        if isinstance(entry, dict) and _same_text(entry.get("ticker"), base):
            justetf_matches.append((isin, entry))

    if len(justetf_matches) == 1:
        isin, entry = justetf_matches[0]
        return {
            "isin": _normalize_isin(isin),
            "name": entry.get("name"),
            "source": "justETF",
        }

    return None


def _add_batch_issues(issues, ticker, isin, ticker_accounts, xtb_data, batch):
    if not isin:
        return

    for other_ticker, other_isin in batch.items():
        other_ticker = _clean_string(other_ticker)
        if not other_ticker or other_ticker == ticker:
            continue
        if _normalize_isin(other_isin) != isin:
            continue

        other_accounts = _xtb_ticker_accounts(xtb_data, other_ticker)
        if _share_account(ticker_accounts, other_accounts):
            issues.append((
                "error",
                f"Același ISIN apare în batch la {other_ticker} din același cont XTB.",
            ))


def _add_saved_isin_issues(issues, ticker, isin, ticker_accounts, xtb_data, saved_isins):
    if not isin:
        return

    for other_ticker, other_isin in saved_isins.items():
        other_ticker = _clean_string(other_ticker)
        if not other_ticker or other_ticker == ticker:
            continue
        if _normalize_isin(other_isin) != isin:
            continue

        other_accounts = _xtb_ticker_accounts(xtb_data, other_ticker)
        if _share_account(ticker_accounts, other_accounts):
            issues.append((
                "warning",
                f"ISIN-ul este deja alocat la {other_ticker} în același cont XTB.",
            ))
        elif ticker_accounts and other_accounts:
            issues.append((
                "info",
                f"ISIN-ul este alocat la {other_ticker} în alt cont XTB; se vor comasa în vizualizarea combinată.",
            ))


def _add_category_issues(issues, category, t212_matches, justetf_entry):
    category_kind = _category_kind(category)
    if category_kind not in {"ETF", "STOCK"}:
        return

    t212_kinds = {
        _t212_type_kind(match.get("type"))
        for match in t212_matches
    }
    t212_kinds.discard(None)

    for t212_kind in sorted(t212_kinds):
        if t212_kind != category_kind:
            issues.append((
                "warning",
                f"Categoria XTB {category_kind} nu se potrivește cu tipul Trading 212 {t212_kind}.",
            ))

    if justetf_entry and category_kind != "ETF":
        issues.append((
            "warning",
            "Categoria XTB STOCK nu se potrivește cu prezența în justETF (ETF/ETC).",
        ))


def _normalize_isin(isin):
    return str(isin or "").strip().upper()


def _clean_string(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _isin_char_digits(char):
    if char.isdigit():
        return char
    return str(ord(char) - ord("A") + 10)


def _luhn_check_digit(expanded_body):
    return (10 - (_luhn_sum(expanded_body + "0") % 10)) % 10


def _luhn_sum(digits):
    total = 0
    double = False

    for digit in reversed(digits):
        value = int(digit)
        if double:
            value *= 2
            value = (value // 10) + (value % 10)
        total += value
        double = not double

    return total


def _ticker_base(ticker):
    text = _clean_string(ticker)
    if not text:
        return None
    return text.split(".", 1)[0]


def _same_text(left, right):
    left = _clean_string(left)
    right = _clean_string(right)
    return bool(left and right and left.upper() == right.upper())


def _first_non_empty(values):
    for value in values:
        if value:
            return value
    return None


def _category_kind(category):
    text = str(category or "").upper()
    if "ETF" in text or "ETC" in text:
        return "ETF"
    if "STOCK" in text or "SHARE" in text or "EQUITY" in text:
        return "STOCK"
    return None


def _t212_type_kind(instrument_type):
    text = str(instrument_type or "").upper()
    if "ETF" in text:
        return "ETF"
    if "STOCK" in text or "SHARE" in text or "EQUITY" in text:
        return "STOCK"
    return None


def _xtb_ticker_accounts(data, ticker):
    if not ticker:
        return set()

    accounts = set()
    for account_key, account in (data.get("accounts") or {}).items():
        for position in account.get("positions") or []:
            if _clean_string(position.get("ticker")) == ticker:
                accounts.add(account_key)
                break

    return accounts


def _share_account(left, right):
    return bool(left and right and left.intersection(right))


def _load_cached_snapshot():
    from t212_api import load_cached_snapshot

    return load_cached_snapshot()


def _get_justetf_entry(isin):
    from justetf_data import get_justetf_entry

    return get_justetf_entry(isin)


def _load_xtb():
    from xtb import load_xtb

    return load_xtb()


def _justetf_cache_data():
    from core import JUSTETF_CACHE_FILE, load_json_file

    cache = load_json_file(JUSTETF_CACHE_FILE, {})
    data = cache.get("data") or {}
    return data if isinstance(data, dict) else {}
