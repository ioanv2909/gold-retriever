"""Proiectia pensiei de stat (Pilonul I, sistemul pe puncte al legii 360/2023) si a pilonilor II / III.

Totul e in bani de azi: valoarea punctului de referinta (VPR) e presupusa indexata cu inflatia, iar
randamentele pilonilor II / III si randamentul folosit pentru valoarea "ca avere" sunt reale (peste inflatie).
Regulile aplicate (verificate 2026-11-19 pe textul legii si pe ghidurile caselor de pensii):
- puncte de stabilitate: 0,50/an peste 25 de ani de contributie, 0,75/an peste 30, 1/an peste 35 (si fractiuni);
- pensie anticipata: cu cel mult 5 ani inaintea varstei standard, doar cu stagiul complet realizat; diminuare pe
  fiecare luna de anticipare dupa stagiul realizat peste cel complet (tabelul nr. 4): <1 an 0,40%, 1-2 ani 0,35%,
  2-3 ani 0,30%, 3-4 ani 0,25%, 4-5 ani (si peste) 0,20%;
- impozitare: primii 3.000 lei/luna neimpozabili; peste ei 10% CASS, apoi 10% impozit pe ce ramane.
Setarile sunt per utilizator, in data/users/<nume>/pension.json.
"""
import copy
from datetime import date

from core import load_json_file, save_json_file
from userctx import UPath

PENSION_FILE = UPath("pension.json")

DEFAULTS = {
    "points": 0.0,            # punctele din decizia / adeverinta Casei de Pensii, pana azi
    "contrib_years": 0.0,     # anii de contributie de pana azi (stagiul realizat)
    "birth_year": 1980,
    "birth_month": 1,
    "retire_age": 65.0,       # varsta standard de pensionare (anexa 5 a legii; 65 pentru barbati)
    "full_stage": 35.0,       # stagiul complet de cotizare (35 de ani; la femei creste treptat pana la 35)
    "planned_age": 0.0,       # varsta la care vrei sa iesi; 0 = varsta standard
    "points_per_year": 1.0,   # ~ salariul brut / castigul salarial mediu brut pe economie
    "vpr": 81.0,              # valoarea punctului de referinta, lei
    "payout_years": 18.0,     # cati ani se estimeaza ca se plateste pensia
    "real_return": 2.0,       # % pe an peste inflatie, pentru valoarea "ca avere"
    "p2_balance": 0.0, "p2_monthly": 0.0, "p2_return": 3.0,
    "p3_balance": 0.0, "p3_monthly": 0.0, "p3_return": 3.0,
    "currency": "RON",
}

# (camp, minim, maxim)
LIMITS = {
    "points": (0, 200), "contrib_years": (0, 60), "birth_year": (1930, 2015), "birth_month": (1, 12),
    "retire_age": (40, 75), "full_stage": (10, 45), "planned_age": (0, 75), "points_per_year": (0, 10),
    "vpr": (0, 100000), "payout_years": (1, 50), "real_return": (-5, 15),
    "p2_balance": (0, 1e9), "p2_monthly": (0, 1e7), "p2_return": (-5, 15),
    "p3_balance": (0, 1e9), "p3_monthly": (0, 1e7), "p3_return": (-5, 15),
}
CURRENCIES = ("RON", "EUR", "USD")
EARLY_YEARS = 5
TAX_FREE = 3000.0
CASS_RATE = 0.10
TAX_RATE = 0.10


def clean(data):
    """Setarile cunoscute, ca numere in limite; restul se ignora."""
    out = copy.deepcopy(DEFAULTS)
    data = data or {}
    for key, (lo, hi) in LIMITS.items():
        try:
            value = float(data.get(key, out[key]))
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        out[key] = min(max(value, lo), hi)
    out["birth_year"] = int(out["birth_year"])
    out["birth_month"] = int(out["birth_month"])
    if data.get("currency") in CURRENCIES:
        out["currency"] = data["currency"]
    return out


def load():
    return clean(load_json_file(PENSION_FILE, {}))


def save(data):
    cfg = clean(data)
    save_json_file(PENSION_FILE, cfg, raise_errors=True)
    return cfg


def stability_points(years):
    """Punctele de stabilitate pentru stagiul peste 25 de ani: 0,50/an (26-30), 0,75/an (31-35), 1,00/an (peste 35)."""
    years = max(0.0, float(years))
    return (0.50 * min(max(years - 25, 0), 5) + 0.75 * min(max(years - 30, 0), 5) + 1.00 * max(years - 35, 0))


def early_rate(surplus_years):
    """Diminuarea pe luna de anticipare (%), dupa stagiul realizat peste stagiul complet (tabelul nr. 4)."""
    for limit, rate in ((1, 0.40), (2, 0.35), (3, 0.30), (4, 0.25)):
        if surplus_years < limit:
            return rate
    return 0.20


def net_pension(gross):
    """Pensia neta: peste 3.000 lei/luna se retin 10% CASS, apoi 10% impozit pe ce ramane."""
    over = max(0.0, gross - TAX_FREE)
    cass = CASS_RATE * over
    tax = TAX_RATE * max(0.0, over - cass)
    return {"gross": gross, "cass": cass, "tax": tax, "net": gross - cass - tax}


def _monthly_rate(pct):
    return (1 + pct / 100) ** (1 / 12) - 1


def future_value(balance, monthly, pct, months):
    r = _monthly_rate(pct)
    if months <= 0:
        return balance
    if abs(r) < 1e-12:
        return balance + monthly * months
    g = (1 + r) ** months
    return balance * g + monthly * (g - 1) / r


def annuity_value(payment, pct, months):
    """Cat ar trebui sa ai la inceputul platilor ca sa primesti `payment` lunar timp de `months` luni."""
    r = _monthly_rate(pct)
    if abs(r) < 1e-12:
        return payment * months
    return payment * (1 - (1 + r) ** -months) / r


def _ym(cfg, age):
    """(an, luna) cand se implineste varsta data."""
    idx = cfg["birth_year"] * 12 + cfg["birth_month"] - 1 + round(age * 12)
    return idx // 12, idx % 12 + 1


def project(cfg, today=None):
    """Proiectia la varsta la care vrei sa iesi la pensie, in bani de azi."""
    cfg = clean(cfg)
    today = today or date.today()
    now_idx = today.year * 12 + today.month - 1
    birth_idx = cfg["birth_year"] * 12 + cfg["birth_month"] - 1
    age_now = (now_idx - birth_idx) / 12
    std = cfg["retire_age"]

    def contrib_at(age):
        return cfg["contrib_years"] + max(0.0, age - age_now)

    def points_at(age):
        y = max(0.0, age - age_now)
        return (cfg["points"] + cfg["points_per_year"] * y
                + stability_points(cfg["contrib_years"] + y) - stability_points(cfg["contrib_years"]))

    # cel mai devreme: cu 5 ani inainte de varsta standard, dar abia cand stagiul complet e realizat
    earliest = max(std - EARLY_YEARS, age_now + max(0.0, cfg["full_stage"] - cfg["contrib_years"]))
    early_possible = earliest < std - 1e-9
    planned = cfg["planned_age"] or std
    planned_ok = True
    if planned < std - 1e-9 and (not early_possible or planned < earliest - 1e-9):
        planned_ok = False
    age_out = planned if planned_ok else std
    months_early = max(0, round((std - age_out) * 12))
    surplus = contrib_at(age_out) - cfg["full_stage"]
    rate = early_rate(surplus) if months_early else 0.0
    penalty = min(1.0, months_early * rate / 100)

    months_left = max(0, round((age_out - age_now) * 12))
    points_out = points_at(age_out)
    gross = points_out * cfg["vpr"] * (1 - penalty)
    taxed = net_pension(gross)
    payout_months = round(cfg["payout_years"] * 12)
    wealth_at_retire = annuity_value(taxed["net"], cfg["real_return"], payout_months)
    wealth_today = wealth_at_retire / (1 + _monthly_rate(cfg["real_return"])) ** months_left
    now_taxed = net_pension(cfg["points"] * cfg["vpr"])
    # pensia daca iesi la fiecare varsta: din 5 in 5 ani, plus varsta standard, cea mai devreme si cea aleasa
    last = max(std, age_out)
    ages = {a for a in range(int(age_now) + 1, int(last) + 1) if (int(last) - a) % 5 == 0}
    ages |= {std, age_out} | ({earliest} if early_possible else set())
    timeline = []
    for age in sorted(a for a in ages if a > age_now - 1e-9):
        pts = points_at(age)
        allowed = age >= std - 1e-9 or (early_possible and age >= earliest - 1e-9)
        early_m = max(0, round((std - age) * 12))
        cut = min(1.0, early_m * early_rate(contrib_at(age) - cfg["full_stage"]) / 100) if early_m else 0.0
        g = pts * cfg["vpr"] * (1 - cut)
        timeline.append({"age": age, "year": _ym(cfg, age)[0], "date": _ym(cfg, age), "points": pts,
                         "allowed": allowed, "penalty": cut if allowed else None,
                         "gross": g if allowed else None, "net": net_pension(g)["net"] if allowed else None,
                         "chosen": abs(age - age_out) < 1e-9})
    return {
        "age_now": age_now, "standard_age": std, "standard_date": _ym(cfg, std),
        "early_possible": early_possible, "earliest_age": earliest if early_possible else None,
        "earliest_date": _ym(cfg, earliest) if early_possible else None,
        "full_stage_reached_age": age_now + max(0.0, cfg["full_stage"] - cfg["contrib_years"]),
        "planned_age": planned, "planned_ok": planned_ok, "age_out": age_out, "out_date": _ym(cfg, age_out),
        "months_early": months_early, "early_rate": rate, "penalty": penalty, "surplus_years": surplus,
        "years_left": months_left / 12, "months_left": months_left,
        "contrib_years_at_retire": contrib_at(age_out),
        "extra_stability": stability_points(contrib_at(age_out)) - stability_points(cfg["contrib_years"]),
        "points_at_retire": points_out, "gross_at_retire": gross, "tax_at_retire": taxed,
        "pension_at_retire": taxed["net"], "pension_now": now_taxed["net"], "pension_now_gross": now_taxed["gross"],
        "wealth_at_retire": wealth_at_retire, "wealth_today": wealth_today,
        "p2_at_retire": future_value(cfg["p2_balance"], cfg["p2_monthly"], cfg["p2_return"], months_left),
        "p3_at_retire": future_value(cfg["p3_balance"], cfg["p3_monthly"], cfg["p3_return"], months_left),
        "timeline": timeline,
    }
