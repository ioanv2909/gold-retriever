"""Extrasul de contributii al unui fond de pensii (exportul CSV "Contributiile mele" de la BT Pensii):
unitatile detinute, ultima valoare a unitatii, totalul depus, contributia lunara medie si randamentul pe bani (XIRR).
Site-ul administratorului blocheaza descarcarile automate, deci extrasul se incarca de mana."""
import csv
import io
from datetime import date, datetime

MAX_BYTES = 2 * 1024 * 1024
COL_DATE = "Data Contributiei"
COL_GROSS = "Valoare bruta - Total (RON)"
COL_VUAN = "VUAN la data contributiei (RON)"
COL_UNITS = "Nr unitati alocate la data contributiei"


class StatementError(ValueError):
    pass


def _num(text):
    text = str(text or "").strip().replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text) if text else 0.0


def xirr(flows, end, value):
    """Randamentul anual (%) pentru depunerile (data, suma) care la data `end` valoreaza `value`."""
    def fv(r):
        return sum(amount * (1 + r) ** ((end - d).days / 365.25) for d, amount in flows)
    lo, hi = -0.9, 2.0
    if not fv(lo) <= value <= fv(hi):
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fv(mid) < value else (lo, mid)
    return lo * 100


def parse(raw):
    """Rezumatul extrasului; StatementError daca fisierul nu are formatul asteptat."""
    if not raw or len(raw) > MAX_BYTES:
        raise StatementError("Fișier gol sau prea mare.")
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or not {COL_DATE, COL_GROSS, COL_VUAN, COL_UNITS} <= set(rows[0]):
        raise StatementError("Formatul nu e recunoscut (lipsesc coloanele exportului de contribuții).")
    entries = []
    for r in rows:
        if not (r.get(COL_DATE) or "").strip():
            continue
        try:
            d = datetime.strptime(r[COL_DATE].strip(), "%d.%m.%Y").date()
            entries.append((d, _num(r[COL_GROSS]), _num(r[COL_VUAN]), _num(r[COL_UNITS])))
        except (ValueError, KeyError):
            raise StatementError(f"Rând invalid: {r.get(COL_DATE)!r}") from None
    if not entries:
        raise StatementError("Extrasul nu are contribuții.")
    entries.sort()
    units = sum(e[3] for e in entries)
    last = entries[-1]
    vuan = next(e[2] for e in reversed(entries) if e[2] > 0)
    flows = [(d, g) for d, g, _, _ in entries if g > 0]
    # ultimele 12 luni calendaristice, inclusiv luna ultimei contributii
    m = last[0].year * 12 + last[0].month - 1 - 11
    since = date(m // 12, m % 12 + 1, 1)
    recent = [g for d, g, _, _ in entries if d >= since]
    return {"units": round(units, 6), "vuan": vuan, "vuan_date": last[0].isoformat(), "value": units * vuan,
            "paid_in": sum(g for _, g in flows), "count": len(flows), "first_date": entries[0][0].isoformat(),
            "monthly_avg": sum(recent) / 12, "xirr": xirr(flows, last[0], units * vuan)}
