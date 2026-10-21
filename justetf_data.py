from datetime import date, datetime
import math
import threading
import time

from core import (
    JUSTETF_CACHE_FILE,
    JUSTETF_REFRESH_INTERVAL,
    load_json_file,
    save_json_file,
)


JUSTETF_COLUMNS = [
    "ticker",
    "wkn",
    "name",
    "inception_date",
    "domicile_country",
    "hedged",
    "securities_lending",
    "dividends",
    "ter",
    "replication",
    "size",
    "number_of_holdings",
    "strategy",
    "currency",
]


def _is_missing(value):
    if value is None:
        return True

    value_type_name = type(value).__name__
    if value_type_name in {"NAType", "NaTType"}:
        return True

    try:
        return bool(value != value)
    except Exception:
        return False


def _to_json_value(value):
    if _is_missing(value):
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return _to_json_value(value.item())
        except Exception:
            pass

    if isinstance(value, float):
        return None if math.isnan(value) else value

    if isinstance(value, (str, int, bool)):
        return value

    return str(value)


def refresh_justetf_cache(force=False):
    cache = load_json_file(JUSTETF_CACHE_FILE, {})
    fetched_at = cache.get("fetched_at")

    if (
        not force
        and isinstance(fetched_at, (int, float))
        and time.time() - fetched_at < JUSTETF_REFRESH_INTERVAL
    ):
        return False

    try:
        try:
            import justetf_scraping
        except ImportError as e:
            print(f"[justetf] {e}", flush=True)
            return False

        import health
        with health.timed("justetf"):
            df = justetf_scraping.load_overview(strategy="epg-longOnly")

        if "isin" not in df.columns and df.index.name == "isin":
            df = df.reset_index()

        if "isin" not in df.columns:
            raise ValueError("Missing 'isin' column in JustETF overview")

        columns = [column for column in JUSTETF_COLUMNS if column in df.columns]
        data = {}

        for _, row in df.iterrows():
            isin = _to_json_value(row["isin"])
            if not isin:
                continue

            data[str(isin)] = {
                column: _to_json_value(row[column])
                for column in columns
            }

        payload = {"fetched_at": time.time(), "data": data}
        if not save_json_file(JUSTETF_CACHE_FILE, payload):
            raise OSError(f"Could not save {JUSTETF_CACHE_FILE}")

        return True
    except Exception as e:
        print(f"[justetf] {e}", flush=True)
        return False


_JE_MEM = {"mtime": None, "data": {}}


def _justetf_data_cached():
    import os as _os
    try:
        m = _os.path.getmtime(JUSTETF_CACHE_FILE)
    except OSError:
        return {}
    if _JE_MEM["mtime"] != m:
        cache = load_json_file(JUSTETF_CACHE_FILE, {})
        _JE_MEM["data"] = cache.get("data") or {}
        _JE_MEM["mtime"] = m
    return _JE_MEM["data"]


def get_justetf_entry(isin):
    if not isin:
        return None

    data = _justetf_data_cached()
    entry = data.get(str(isin))

    return entry if isinstance(entry, dict) else None


def start_justetf_refresh_background(force=False):
    thread = threading.Thread(
        target=refresh_justetf_cache,
        args=(force,),
        daemon=True,
    )
    thread.start()
