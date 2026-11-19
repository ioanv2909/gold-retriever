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
    "p2_upfront": 30.0,       # % platit odata la pensionare (legea 2/2026: cel mult 30%)
    "p2_years": 8.0,          # anii in care se plateste restul (cel putin 8)
    "inv_monthly": 0.0,       # depunerea lunara la bursa pentru proiectie (in inv_ccy); 0 = ritmul de pana acum
    "inv_return": -99.0,      # randament anual nominal %; -99 = randamentul de pana acum
    "inv_inflation": 2.5,     # inflatia anuala pentru valoarea in bani de azi
    "inv_ccy": "EUR",
    "p3_units": 0.0,          # unitatile de fond din extras (0 = soldul se completeaza de mana)
    "p3_vuan": 0.0,           # ultima valoare cunoscuta a unitatii
    "goal_amount": 0.0,       # obiectivul de avere (investitii + pilonii II/III), in inv_ccy, bani de azi; 0 = fara
    "goal_age": 60.0,
    "currency": "RON",
}

# (camp, minim, maxim)
LIMITS = {
    "points": (0, 200), "contrib_years": (0, 60), "birth_year": (1930, 2015), "birth_month": (1, 12),
    "retire_age": (40, 75), "full_stage": (10, 45), "planned_age": (0, 75), "points_per_year": (0, 10),
    "vpr": (0, 100000), "payout_years": (1, 50), "real_return": (-5, 15),
    "p2_balance": (0, 1e9), "p2_monthly": (0, 1e7), "p2_return": (-5, 15),
    "p3_balance": (0, 1e9), "p3_monthly": (0, 1e7), "p3_return": (-5, 15),
    "p2_upfront": (0, 30), "p2_years": (8, 40),
    "inv_monthly": (0, 1e7), "inv_return": (-99, 30), "inv_inflation": (0, 30),
    "goal_amount": (0, 1e10), "goal_age": (30, 80),
    "p3_units": (0, 1e9), "p3_vuan": (0, 1e6),
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
    if data.get("inv_ccy") in CURRENCIES:
        out["inv_ccy"] = data["inv_ccy"]
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


def private_by_age(cfg, key, ages=(55, 60, 62, 65, 67), today=None):
    """Pilonul II / III ("p2" / "p3"): soldul estimat daca iesi la pensie la fiecare varsta (contributii pana atunci).
    Include si varsta standard si cea aleasa. Pilonul II se plateste odata cu pensia de stat; Pilonul III de la 60 de ani."""
    cfg = clean(cfg)
    today = today or date.today()
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    balance, monthly, ret = cfg[key + "_balance"], cfg[key + "_monthly"], cfg[key + "_return"]
    wanted = set(ages) | {cfg["retire_age"]} | ({cfg["planned_age"]} if cfg["planned_age"] else set())
    rows = []
    for age in sorted(a for a in wanted if a > age_now):
        months = max(0, round((age - age_now) * 12))
        value = future_value(balance, monthly, ret, months)
        paid = balance + monthly * months
        rows.append({"age": age, "date": _ym(cfg, age), "months": months, "paid_in": paid, "value": value,
                     "gain": value - paid, "available": key == "p3" and age >= 60 or key == "p2"})
    return rows


def uniform_return(deposits, months, value):
    """Randamentul anual (%) care, cu depuneri egale lunare insumand `deposits` in `months` luni, ajunge la `value`.
    Aproximare a randamentului pe bani (fara datele exacte ale depunerilor); None daca datele nu ajung."""
    if not deposits or deposits <= 0 or not months or months < 1 or not value or value <= 0:
        return None
    m = deposits / months

    def fv(r):
        return m * months if abs(r) < 1e-12 else m * ((1 + r) ** months - 1) / r
    lo, hi = -0.2, 0.2
    if not fv(lo) <= value <= fv(hi):
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fv(mid) < value else (lo, mid)
    return ((1 + lo) ** 12 - 1) * 100


def invest_by_age(cfg, value_now, monthly, annual_pct, inflation_pct, ages=(55, 60, 62, 65, 67), today=None):
    """Valoarea investitiilor la fiecare varsta: valoarea de azi + depunerea lunara, la randamentul anual dat;
    nominal si in bani de azi (dupa inflatie)."""
    cfg = clean(cfg)
    today = today or date.today()
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    wanted = set(ages) | {cfg["retire_age"]} | ({cfg["planned_age"]} if cfg["planned_age"] else set())
    rows = []
    for age in sorted(a for a in wanted if a > age_now):
        months = max(0, round((age - age_now) * 12))
        value = future_value(value_now, monthly, annual_pct, months)
        rows.append({"age": age, "date": _ym(cfg, age), "months": months, "paid_in": value_now + monthly * months,
                     "value": value, "real": value / (1 + inflation_pct / 100) ** (months / 12)})
    return rows


def real_return(nominal_pct, inflation_pct):
    """Randamentul real (%) din cel nominal si inflatie."""
    return ((1 + nominal_pct / 100) / (1 + inflation_pct / 100) - 1) * 100


def required_monthly(goal, value_now, annual_pct, months):
    """Depunerea lunara necesara ca `value_now` sa ajunga la `goal` in `months` luni la randamentul dat
    (0 daca ajunge si fara depuneri; None fara timp ramas)."""
    if months <= 0:
        return None
    r = _monthly_rate(annual_pct)
    grow = (1 + r) ** months
    rest = goal - value_now * grow
    if rest <= 0:
        return 0.0
    return rest / months if abs(r) < 1e-12 else rest * r / (grow - 1)


def wealth_path(cfg, inv_now, monthly, nominal_pct, inflation_pct, until_age=67, spread=2.0, today=None):
    """Drumul averii pe ani, in bani de azi: investitiile (randament nominal +/- spread, minus inflatia) si pilonii
    II + III (randamente deja reale). Un punct pe an de varsta, de azi pana la until_age."""
    cfg = clean(cfg)
    today = today or date.today()
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    ages = [age_now] + list(range(int(age_now) + 1, int(until_age) + 1))
    out = []
    for age in ages:
        months = max(0, round((age - age_now) * 12))
        deflate = (1 + inflation_pct / 100) ** (months / 12)
        inv = {k: future_value(inv_now, monthly, nominal_pct + d, months) / deflate
               for k, d in (("inv", 0), ("inv_low", -spread), ("inv_high", spread))}
        pillars = (future_value(cfg["p2_balance"], cfg["p2_monthly"], cfg["p2_return"], months)
                   + future_value(cfg["p3_balance"], cfg["p3_monthly"], cfg["p3_return"], months))
        out.append(dict(inv, age=age, pillars=pillars, total=inv["inv"] + pillars,
                        total_low=inv["inv_low"] + pillars, total_high=inv["inv_high"] + pillars))
    return out


def p2_payout(value, upfront_pct, years):
    """Plata Pilonului II dupa legea 2/2026: (plata unica, rata lunara) - cel mult 30% odata, restul lunar in cel
    putin 8 ani. Fara randamentul obtinut in perioada de plata (ratele reale pot iesi putin mai mari)."""
    pct = min(max(float(upfront_pct), 0.0), 30.0) / 100
    months = max(8.0, float(years)) * 12
    return value * pct, value * (1 - pct) / months


def totals_by_age(cfg, today=None, inv=None):
    """Venitul lunar din cei trei piloni daca iesi la pensie la fiecare varsta (lucrand pana atunci).
    Pilonul II se plateste odata cu pensia de stat (plata unica + rate pe p2_years ani); Pilonul III de la 60 de ani,
    impartit orientativ pe payout_years ani. Sub limita legala pentru pensie (anticipata) nu se poate iesi."""
    cfg = clean(cfg)
    today = today or date.today()
    p2 = {x["age"]: x for x in private_by_age(cfg, "p2", today=today)}
    p3 = {x["age"]: x for x in private_by_age(cfg, "p3", today=today)}
    invest = {}
    if inv:  # {"now", "monthly", "ret", "inflation"} in aceeasi moneda ca restul (lei)
        invest = {x["age"]: x for x in invest_by_age(cfg, inv["now"], inv["monthly"], inv["ret"], inv["inflation"],
                                                      ages=tuple(p2), today=today)}
    rows = []
    for age in sorted(p2):
        r = project(dict(cfg, planned_age=age), today=today)
        ok = r["planned_ok"] or age >= cfg["retire_age"] - 1e-9
        state = r["pension_at_retire"] if ok else None
        lump, p2_month = p2_payout(p2[age]["value"], cfg["p2_upfront"], cfg["p2_years"]) if ok else (None, None)
        p3_month = p3[age]["value"] / (cfg["payout_years"] * 12) if p3[age]["available"] else None
        monthly = (state or 0) + (p2_month or 0) + (p3_month or 0) if ok else None
        inv_month = invest[age]["real"] * 0.04 / 12 if age in invest else None
        rows.append({"age": age, "date": _ym(cfg, age), "allowed": ok, "penalty": r["penalty"] if ok else None,
                     "inv_month": inv_month,
                     "state": state, "p2_lump": lump, "p2_month": p2_month, "p3_month": p3_month,
                     "monthly": monthly, "after_p2": (state or 0) + (p3_month or 0) if ok else None})
    return rows


def scenarios(cfg, stop_ages=(55, 60, 65), today=None):
    """Ce pensie primesti daca te opresti din munca acum sau la varstele date (cu acelasi salariu pana atunci).
    Pensia poate incepe cel mai devreme cu 5 ani inainte de varsta standard, si doar daca stagiul complet e atins
    pana la oprire; altfel abia la varsta standard. Punctele raman cele adunate pana la oprire."""
    cfg = clean(cfg)
    today = today or date.today()
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    std = cfg["retire_age"]
    rows = []
    for stop in [None] + [a for a in stop_ages if a > age_now]:
        stop_age = age_now if stop is None else float(stop)
        worked = max(0.0, stop_age - age_now)
        contrib = cfg["contrib_years"] + worked
        pts = (cfg["points"] + cfg["points_per_year"] * worked
               + stability_points(contrib) - stability_points(cfg["contrib_years"]))
        full = contrib >= cfg["full_stage"] - 1e-9
        earliest = max(stop_age, std - EARLY_YEARS) if full else max(stop_age, std)
        earliest = max(earliest, age_now)
        months_early = max(0, round((std - earliest) * 12))
        cut = min(1.0, months_early * early_rate(contrib - cfg["full_stage"]) / 100) if months_early else 0.0
        at_std = max(std, stop_age)
        rows.append({
            "stop_age": None if stop is None else stop_age, "contrib_years": contrib, "points": pts,
            "full_stage": full, "earliest_age": earliest, "earliest_date": _ym(cfg, earliest), "penalty": cut,
            "net_earliest": net_pension(pts * cfg["vpr"] * (1 - cut))["net"],
            "std_age": at_std, "std_date": _ym(cfg, at_std), "net_std": net_pension(pts * cfg["vpr"])["net"],
        })
    return rows


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
