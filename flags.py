"""Steaguri pentru tari si monede (imagini PNG 40px in assets/flags/, de la flagcdn.com, gratuite).

Emoji-urile cu steaguri nu apar pe Windows (se vad doua litere), de aceea se folosesc imagini.
"""
import base64
import functools
import json
import os

FLAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "flags")

# nume folosite de Yahoo / justETF care difera de lista flagcdn
ALIASES = {
    "united states": "us", "usa": "us", "us": "us", "united kingdom": "gb", "uk": "gb", "great britain": "gb",
    "south korea": "kr", "korea": "kr", "korea, republic of": "kr", "taiwan": "tw", "russia": "ru",
    "czech republic": "cz", "czechia": "cz", "hong kong": "hk", "macau": "mo", "macao": "mo", "vietnam": "vn",
    "iran": "ir", "syria": "sy", "venezuela": "ve", "bolivia": "bo", "tanzania": "tz", "laos": "la",
    "moldova": "md", "north macedonia": "mk", "ivory coast": "ci", "cote d'ivoire": "ci", "curacao": "cw",
    "netherlands": "nl", "the netherlands": "nl", "bahamas": "bs", "the bahamas": "bs", "uae": "ae",
    "european union": "eu", "eurozone": "eu", "euro area": "eu", "romania": "ro", "românia": "ro",
}

CURRENCY_COUNTRY = {
    "EUR": "eu", "USD": "us", "GBP": "gb", "GBX": "gb", "RON": "ro", "CHF": "ch", "JPY": "jp", "DKK": "dk",
    "SEK": "se", "NOK": "no", "CAD": "ca", "AUD": "au", "HKD": "hk", "CNY": "cn", "PLN": "pl", "CZK": "cz",
    "HUF": "hu", "KRW": "kr", "TWD": "tw", "INR": "in", "BRL": "br", "ZAR": "za", "SGD": "sg", "MXN": "mx",
    "ILS": "il", "TRY": "tr", "NZD": "nz", "BGN": "bg", "ISK": "is", "THB": "th", "IDR": "id", "MYR": "my",
    "PHP": "ph", "SAR": "sa", "AED": "ae", "CLP": "cl", "COP": "co", "PEN": "pe", "ARS": "ar",
}


@functools.lru_cache(maxsize=1)
def _names():
    try:
        with open(os.path.join(FLAG_DIR, "names.json"), encoding="utf-8") as f:
            return {v.lower(): k for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def country_code(name):
    """Codul ISO (2 litere, mic) pentru numele unei tari; None daca nu e cunoscut."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    code = ALIASES.get(key) or _names().get(key)
    if code is None and len(key) == 2 and os.path.exists(os.path.join(FLAG_DIR, key + ".png")):
        code = key
    return code


def currency_code(ccy):
    return CURRENCY_COUNTRY.get(str(ccy or "").upper())


@functools.lru_cache(maxsize=512)
def flag_uri(code):
    """Imaginea steagului ca data URI (PNG); None daca nu exista."""
    if not code:
        return None
    path = os.path.join(FLAG_DIR, os.path.basename(str(code).lower()) + ".png")
    try:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return None
