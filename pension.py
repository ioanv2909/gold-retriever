"""Proiectia pensiei de stat (Pilonul I, sistemul pe puncte al legii 360/2023) si a pilonilor II / III.

Totul e in bani de azi: valoarea punctului de referinta (VPR) e presupusa indexata cu inflatia, iar
randamentele pilonilor II / III si randamentul folosit pentru valoarea "ca avere" sunt reale (peste inflatie).
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
    "retire_age": 65.0,
    "points_per_year": 1.0,   # ~ salariul brut / castigul salarial mediu brut pe economie
    "vpr": 81.0,              # valoarea punctului de referinta, lei
    "payout_years": 18.0,     # cati ani se estimeaza ca se plateste pensia
    "real_return": 2.0,       # % pe an peste inflatie, pentru valoarea "ca avere"
    "p2_balance": 0.0, "p2_monthly": 0.0, "p2_return": 3.0,
    "p3_balance": 0.0, "p3_monthly": 0.0, "p3_return": 3.0,
}

# (camp, minim, maxim)
LIMITS = {
    "points": (0, 200), "contrib_years": (0, 60), "birth_year": (1930, 2015), "birth_month": (1, 12),
    "retire_age": (40, 75), "points_per_year": (0, 10), "vpr": (0, 100000), "payout_years": (1, 50),
    "real_return": (-5, 15), "p2_balance": (0, 1e9), "p2_monthly": (0, 1e7), "p2_return": (-5, 15),
    "p3_balance": (0, 1e9), "p3_monthly": (0, 1e7), "p3_return": (-5, 15),
}


def clean(data):
    """Setarile cunoscute, ca numere in limite; restul se ignora."""
    out = copy.deepcopy(DEFAULTS)
    for key, (lo, hi) in LIMITS.items():
        try:
            value = float((data or {}).get(key, out[key]))
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        out[key] = min(max(value, lo), hi)
    out["birth_year"] = int(out["birth_year"])
    out["birth_month"] = int(out["birth_month"])
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


def project(cfg, today=None):
    """Proiectia la varsta de pensionare, in bani de azi."""
    cfg = clean(cfg)
    today = today or date.today()
    retire_month_index = (cfg["birth_year"] * 12 + cfg["birth_month"] - 1) + round(cfg["retire_age"] * 12)
    months_left = max(0, retire_month_index - (today.year * 12 + today.month - 1))
    years_left = months_left / 12
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    years_at_retire = cfg["contrib_years"] + years_left
    # punctele de azi includ deja stabilitatea castigata; se adauga doar cea castigata de acum incolo
    extra_stability = stability_points(years_at_retire) - stability_points(cfg["contrib_years"])
    points_at_retire = cfg["points"] + cfg["points_per_year"] * years_left + extra_stability
    pension_now = cfg["points"] * cfg["vpr"]
    pension_at_retire = points_at_retire * cfg["vpr"]
    payout_months = round(cfg["payout_years"] * 12)
    wealth_at_retire = annuity_value(pension_at_retire, cfg["real_return"], payout_months)
    wealth_today = wealth_at_retire / (1 + _monthly_rate(cfg["real_return"])) ** months_left
    p2 = future_value(cfg["p2_balance"], cfg["p2_monthly"], cfg["p2_return"], months_left)
    p3 = future_value(cfg["p3_balance"], cfg["p3_monthly"], cfg["p3_return"], months_left)
    timeline = []
    for age in range(int(age_now) + 1, int(cfg["retire_age"]) + 1):
        if (age - int(cfg["retire_age"])) % 5 and age != int(cfg["retire_age"]):
            continue
        y = max(0.0, age - age_now)
        pts = cfg["points"] + cfg["points_per_year"] * y + stability_points(cfg["contrib_years"] + y) - stability_points(cfg["contrib_years"])
        timeline.append({"age": age, "year": today.year + round(y), "points": pts, "pension": pts * cfg["vpr"]})
    return {
        "age_now": age_now, "years_left": years_left, "months_left": months_left,
        "retire_year": cfg["birth_year"] + int((cfg["birth_month"] - 1 + cfg["retire_age"] * 12) // 12),
        "contrib_years_at_retire": years_at_retire, "extra_stability": extra_stability,
        "points_at_retire": points_at_retire, "pension_now": pension_now, "pension_at_retire": pension_at_retire,
        "wealth_at_retire": wealth_at_retire, "wealth_today": wealth_today,
        "p2_at_retire": p2, "p3_at_retire": p3, "timeline": timeline,
    }
