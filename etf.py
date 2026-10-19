from datetime import date

import pandas as pd

from justetf_data import get_justetf_entry
from t212_api import load_cached_snapshot
from yf_compat import yf


ETF_INDICATORS = [
    {
        "key": "ter",
        "label": "TER (%)",
        "weight": 35,
        "target": 0.20,
        "red_flag": 0.60,
        "higher_is_better": False,
    },
    {
        "key": "aum",
        "label": "AUM (mil. EUR)",
        "weight": 20,
        "target": 300,
        "red_flag": 50,
        "higher_is_better": True,
    },
    {
        "key": "age",
        "label": "Vechime (ani)",
        "weight": 10,
        "target": 5,
        "red_flag": 1,
        "higher_is_better": True,
    },
    {
        "key": "top10",
        "label": "Concentrare Top 10 (%)",
        "weight": 15,
        "target": 25,
        "red_flag": 60,
        "higher_is_better": False,
    },
    {
        "key": "holdings",
        "label": "Număr deținuri",
        "weight": 10,
        "target": 500,
        "red_flag": 50,
        "higher_is_better": True,
    },
    {
        "key": "replication",
        "label": "Replicare fizică (1) / swap (0)",
        "weight": 10,
        "target": 1,
        "red_flag": 0,
        "higher_is_better": True,
    },
]


def _is_missing(value):
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _to_float(value):
    if _is_missing(value):
        return None

    if isinstance(value, str):
        value = (
            value.strip()
            .replace("%", "")
            .replace("\u00a0", " ")
            .replace(",", "")
        )
        if not value:
            return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value):
    if _is_missing(value):
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "da", "1"}:
            return True
        if normalized in {"false", "no", "n", "nu", "0"}:
            return False

    return None


def _distribution_label(value):
    if _is_missing(value):
        return None

    if value == "Accumulating":
        return "Acc"
    if value == "Distributing":
        return "Dist"

    return None


def _age_years(inception_date):
    if _is_missing(inception_date):
        return None

    try:
        start = date.fromisoformat(str(inception_date))
    except ValueError:
        return None

    today = date.today()
    years = today.year - start.year

    if (today.month, today.day) < (start.month, start.day):
        years -= 1

    return float(max(0, years))


def _yahoo_info(yahoo_symbol):
    if not yahoo_symbol:
        return {}

    try:
        info = yf.Ticker(yahoo_symbol).info
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _yahoo_top10(yahoo_symbol):
    if not yahoo_symbol:
        return None

    try:
        top_holdings = yf.Ticker(yahoo_symbol).funds_data.top_holdings
        if top_holdings is None or len(top_holdings) < 5:
            return None

        weights = pd.to_numeric(top_holdings.iloc[:, -1], errors="coerce").dropna()
        if len(weights) < 5:
            return None

        return float(weights.sum() * 100)
    except Exception:
        return None


def _etf_indicator_score(value, target, red_flag, higher_is_better):
    if value is None or pd.isna(value):
        return None

    if higher_is_better:
        if target == red_flag:
            return 1.0 if value >= target else 0.0
        score = (value - red_flag) / (target - red_flag)
    else:
        if red_flag == target:
            return 1.0 if value <= target else 0.0
        score = (red_flag - value) / (red_flag - target)

    return float(min(1.0, max(0.0, score)))


def get_instrument(ticker_t212):
    snapshot = load_cached_snapshot() or {}
    instruments = snapshot.get("instruments") or []

    for instrument in instruments:
        if not isinstance(instrument, dict):
            continue

        if instrument.get("ticker") == ticker_t212:
            return {
                "isin": instrument.get("isin"),
                "type": instrument.get("type"),
                "name": instrument.get("name"),
                "currencyCode": instrument.get("currencyCode"),
            }

    return None


def extract_etf_metrics(isin, yahoo_symbol=None, manual=None):
    metrics = {ind["key"]: None for ind in ETF_INDICATORS}
    labels = {
        "isin": isin,
        "nume": None,
        "domiciliu": None,
        "distributie": None,
        "hedged": None,
        "securities_lending": None,
        "replicare": None,
        "strategie": None,
    }
    notes = {}

    entry = get_justetf_entry(isin)

    if entry:
        replication_text = entry.get("replication")

        labels.update({
            "nume": entry.get("name"),
            "domiciliu": entry.get("domicile_country"),
            "distributie": _distribution_label(entry.get("dividends")),
            "hedged": _to_bool(entry.get("hedged")),
            "securities_lending": _to_bool(entry.get("securities_lending")),
            "replicare": replication_text,
            "strategie": entry.get("strategy"),
        })

        metrics["ter"] = _to_float(entry.get("ter"))
        metrics["aum"] = _to_float(entry.get("size"))
        metrics["age"] = _age_years(entry.get("inception_date"))
        metrics["holdings"] = _to_float(entry.get("number_of_holdings"))

        if not _is_missing(replication_text):
            metrics["replication"] = 0.0 if "swap" in str(replication_text).lower() else 1.0
    else:
        notes["justetf"] = "ISIN negăsit în justETF"

        info = _yahoo_info(yahoo_symbol)
        metrics["ter"] = _to_float(info.get("netExpenseRatio"))

        total_assets = _to_float(info.get("totalAssets"))
        if total_assets is not None:
            metrics["aum"] = total_assets / 1_000_000
            notes["aum"] = "AUM Yahoo, monedă incertă"

    metrics["top10"] = _yahoo_top10(yahoo_symbol)

    manual = manual or {}
    if manual.get("ter") is not None:
        metrics["ter"] = _to_float(manual.get("ter"))
        notes["ter"] = "TER manual"

    if manual.get("aum") is not None:
        metrics["aum"] = _to_float(manual.get("aum"))
        notes["aum"] = "AUM manual"

    return metrics, labels, notes


def compute_etf_score(metrics):
    rows = []
    total_points = 0.0
    coverage = 0.0

    for ind in ETF_INDICATORS:
        key = ind["key"]
        val = metrics.get(key)
        weight = ind["weight"]
        target = ind["target"]
        red_flag = ind["red_flag"]
        higher_is_better = ind["higher_is_better"]

        if val is None or pd.isna(val):
            score = None
            points = None
        else:
            score = _etf_indicator_score(val, target, red_flag, higher_is_better)
            points = score * weight
            total_points += points
            coverage += weight

        rows.append({
            "key": key,
            "label": ind["label"],
            "value": val,
            "target": target,
            "red_flag": red_flag,
            "weight": weight,
            "score": score,
            "points": points,
        })

    total = float((total_points / coverage) * 100) if coverage > 0 else 0.0

    if coverage < 50:
        rating = "Date insuficiente"
    elif total >= 80:
        rating = "Excelent"
    elif total >= 65:
        rating = "Aprobat"
    elif total >= 50:
        rating = "Vulnerabil"
    else:
        rating = "Respins"

    return {
        "rows": rows,
        "total": total,
        "coverage": coverage,
        "rating": rating,
    }
