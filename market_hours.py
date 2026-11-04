"""Programul de tranzactionare al burselor (fara UI): bursa unui simbol Yahoo, sesiunile unei zile in ora locala,
starea curenta (deschisa/inchisa) si urmatoarea schimbare. Program obisnuit, fara sarbatori si zile scurte."""
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# sufix Yahoo -> (cheie, nume, fus orar, sesiuni locale [(deschidere, inchidere)])
_EU = [(time(9, 0), time(17, 30))]
EXCHANGES = {
    "": ("US", "NYSE / Nasdaq", "America/New_York", [(time(9, 30), time(16, 0))]),
    ".TO": ("TSX", "Toronto", "America/Toronto", [(time(9, 30), time(16, 0))]),
    ".L": ("LSE", "London", "Europe/London", [(time(8, 0), time(16, 30))]),
    ".IR": ("ISE", "Dublin", "Europe/Dublin", [(time(8, 0), time(16, 30))]),
    ".DE": ("XETRA", "Xetra", "Europe/Berlin", _EU),
    ".F": ("FRA", "Frankfurt", "Europe/Berlin", [(time(8, 0), time(22, 0))]),
    ".PA": ("EPA", "Euronext Paris", "Europe/Paris", _EU),
    ".AS": ("AMS", "Euronext Amsterdam", "Europe/Amsterdam", _EU),
    ".BR": ("EBR", "Euronext Brussels", "Europe/Brussels", _EU),
    ".LS": ("ELI", "Euronext Lisbon", "Europe/Lisbon", [(time(8, 0), time(16, 30))]),
    ".MI": ("BIT", "Borsa Italiana", "Europe/Rome", _EU),
    ".MC": ("BME", "Madrid", "Europe/Madrid", _EU),
    ".SW": ("SIX", "SIX Swiss", "Europe/Zurich", [(time(9, 0), time(17, 20))]),
    ".VI": ("WBAG", "Wien", "Europe/Vienna", [(time(9, 0), time(17, 30))]),
    ".WA": ("GPW", "Warszawa", "Europe/Warsaw", [(time(9, 0), time(17, 0))]),
    ".PR": ("PSE", "Praha", "Europe/Prague", [(time(9, 0), time(16, 25))]),
    ".BD": ("BET", "Budapest", "Europe/Budapest", [(time(9, 0), time(17, 0))]),
    ".RO": ("BVB", "București", "Europe/Bucharest", [(time(10, 0), time(17, 45))]),
    ".CO": ("CPH", "Copenhagen", "Europe/Copenhagen", [(time(9, 0), time(17, 0))]),
    ".ST": ("STO", "Stockholm", "Europe/Stockholm", _EU),
    ".OL": ("OSE", "Oslo", "Europe/Oslo", [(time(9, 0), time(16, 20))]),
    ".HE": ("HEL", "Helsinki", "Europe/Helsinki", [(time(10, 0), time(18, 30))]),
    ".T": ("TSE", "Tokyo", "Asia/Tokyo", [(time(9, 0), time(11, 30)), (time(12, 30), time(15, 30))]),
    ".HK": ("HKEX", "Hong Kong", "Asia/Hong_Kong", [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0))]),
    ".AX": ("ASX", "Sydney", "Australia/Sydney", [(time(10, 0), time(16, 0))]),
    ".NS": ("NSE", "India NSE", "Asia/Kolkata", [(time(9, 15), time(15, 30))]),
    ".SA": ("B3", "São Paulo", "America/Sao_Paulo", [(time(10, 0), time(17, 0))]),
}


def local_zone():
    try:
        return ZoneInfo(os.environ.get("TZ") or "Europe/Bucharest")
    except Exception:
        return ZoneInfo("UTC")


def exchange_of(yahoo_symbol):
    """Sufixul bursei pentru un simbol Yahoo, sau None (valute, indici, cripto, burse necunoscute)."""
    sym = str(yahoo_symbol or "").strip().upper()
    if not sym or sym.startswith("^") or "=" in sym or sym.endswith(("-USD", "-EUR")):
        return None
    if "." not in sym:
        return ""
    suffix = "." + sym.rsplit(".", 1)[1]
    if suffix in EXCHANGES:
        return suffix
    # clase de actiuni americane (BRK.B) au sufix de o litera, care nu e bursa
    return "" if len(suffix) == 2 and sym.count(".") == 1 else None


def _sessions_on(suffix, exch_date):
    """Sesiunile (inceput, sfarsit, cu fus) dintr-o zi a bursei; nimic in weekend."""
    if exch_date.weekday() >= 5:
        return []
    _, _, tz, sessions = EXCHANGES[suffix]
    zone = ZoneInfo(tz)
    return [(datetime.combine(exch_date, a, zone), datetime.combine(exch_date, b, zone)) for a, b in sessions]


def sessions_between(suffix, start, end):
    """Sesiunile care se suprapun cu [start, end), taiate la margini, in fusul lui start."""
    zone = start.tzinfo
    out = []
    day = (start - timedelta(days=1)).date()
    while day <= (end + timedelta(days=1)).date():
        for a, b in _sessions_on(suffix, day):
            a, b = max(a, start), min(b, end)
            if a < b:
                out.append((a.astimezone(zone), b.astimezone(zone)))
        day += timedelta(days=1)
    return sorted(out)


def status(suffix, now):
    """(deschisa acum, momentul urmatoarei schimbari in fusul lui now sau None)."""
    for a, b in sessions_between(suffix, now - timedelta(days=1), now + timedelta(days=8)):
        if a <= now < b:
            return True, b
        if a > now:
            return False, a
    return False, None


def group_positions(rows):
    """rows: [{ticker, name, yahoo_symbol}] -> ({sufix: [nume]}, [tickere fara bursa cunoscuta])."""
    groups, unknown = {}, []
    for r in rows:
        suffix = exchange_of(r.get("yahoo_symbol"))
        label = r.get("name") or r.get("ticker")
        if suffix is None:
            unknown.append(r.get("ticker"))
        else:
            groups.setdefault(suffix, []).append(label)
    return groups, unknown


def region_of(suffix):
    """Regiunea unei burse dupa fusul orar: europe, america, asia, oceania."""
    return EXCHANGES[suffix][2].split("/")[0].lower().replace("australia", "oceania")


def group_by_hours(groups, day_start, now):
    """Bursele cu aceleasi sesiuni azi (ora locala) si din aceeasi regiune intr-o singura bara.
    groups: {sufix: [pozitii]} -> [{region, exchanges, sessions, positions, open}], ordonate dupa prima deschidere."""
    day_end = day_start + timedelta(days=1)
    bars = {}
    for suffix, names in groups.items():
        sessions = tuple(sessions_between(suffix, day_start, day_end))
        bar = bars.setdefault((region_of(suffix), sessions), {
            "region": region_of(suffix), "exchanges": [], "sessions": list(sessions), "positions": 0,
            "open": any(a <= now < b for a, b in sessions)})
        bar["exchanges"].append(EXCHANGES[suffix][1])
        bar["positions"] += len(names)
    return sorted(bars.values(), key=lambda b: (b["sessions"][0][0] if b["sessions"] else day_end, b["region"]))
