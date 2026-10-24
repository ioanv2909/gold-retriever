"""Alerte pe pozitii: pret (peste/sub o valoare), scor (sub prag sau scadere), concentrare in portofoliu si
evenimente importante (8-K, downgrade-uri, cumparari de insideri, din lentilele de strategie).

Regulile si starea sunt per utilizator. Evaluarea ruleaza in fundal; alertele declansate ajung in
jurnal (banner in aplicatie) si, daca utilizatorul are adresa, pe email.
"""
import copy
import json
import os
import time
import uuid

from core import load_json_file, save_json_file, update_json_file
from userctx import UPath, current_user, user_dir

RULES_FILE = UPath("alert_rules.json")
STATE_FILE = UPath("alert_rules_state.json")
LOG_FILE = UPath("alert_log.json")

SCORE_KINDS = ("quality", "risk", "dividend")
DEFAULT_RULES = {
    "price": [],
    "score": {"enabled": False, "kinds": list(SCORE_KINDS), "below": 50, "drop": 15},
    "concentration": {"enabled": False, "max_pct": 20},
    "events": {"enabled": False},
}
SCORE_RESET = 5     # scorul trebuie sa urce cu atat peste prag ca alerta "sub prag" sa se poata repeta
CONC_RESET = 2      # ponderea trebuie sa scada cu atat sub limita ca alerta de concentrare sa se poata repeta
LOG_KEEP = 200
EVENTS_KEEP = 100   # id-uri de evenimente deja vazute, per ticker
EVAL_INTERVAL = 900


# ---------------------------------------------------------------------------
# Reguli
# ---------------------------------------------------------------------------
def load_rules():
    rules = copy.deepcopy(DEFAULT_RULES)
    saved = load_json_file(RULES_FILE, {})
    if isinstance(saved, dict):
        if isinstance(saved.get("price"), list):
            rules["price"] = saved["price"]
        for k in ("score", "concentration", "events"):
            if isinstance(saved.get(k), dict):
                rules[k].update({f: saved[k][f] for f in DEFAULT_RULES[k] if f in saved[k]})
    return rules


def _update_rules(fn):
    def updater(cur):
        rules = copy.deepcopy(DEFAULT_RULES)
        if isinstance(cur, dict):
            rules.update(cur)
        fn(rules)
        return rules
    return update_json_file(RULES_FILE, {}, updater)


def add_price_alert(ticker, op, price, name=None, ccy=None):
    if op not in ("above", "below") or not ticker or price is None or float(price) <= 0:
        return None
    item = {"id": uuid.uuid4().hex[:10], "ticker": ticker, "name": name or ticker, "op": op,
            "price": float(price), "ccy": ccy or "", "active": True, "created": time.time(), "triggered_at": None}
    _update_rules(lambda r: r["price"].append(item))
    return item


def remove_price_alert(alert_id):
    _update_rules(lambda r: r.update(price=[a for a in r["price"] if a.get("id") != alert_id]))


def rearm_price_alert(alert_id):
    def fn(r):
        for a in r["price"]:
            if a.get("id") == alert_id:
                a["active"], a["triggered_at"] = True, None
    _update_rules(fn)


def save_score_rule(enabled, kinds, below, drop):
    rule = {"enabled": bool(enabled), "kinds": [k for k in kinds if k in SCORE_KINDS],
            "below": max(0, min(100, int(below))), "drop": max(1, min(100, int(drop)))}
    _update_rules(lambda r: r.update(score=rule))
    return rule


def save_concentration_rule(enabled, max_pct):
    rule = {"enabled": bool(enabled), "max_pct": max(1, min(100, float(max_pct)))}
    _update_rules(lambda r: r.update(concentration=rule))
    return rule


def save_events_rule(enabled):
    rule = {"enabled": bool(enabled)}
    _update_rules(lambda r: r.update(events=rule))
    return rule


# ---------------------------------------------------------------------------
# Verificari (functii pure)
# ---------------------------------------------------------------------------
def check_prices(price_alerts, holdings, now=None):
    """Intoarce (declansate, alerte actualizate). O alerta de pret se declanseaza o data, apoi se dezactiveaza."""
    now = now or time.time()
    fired, out = [], []
    for a in price_alerts:
        a = dict(a)
        h = holdings.get(a.get("ticker")) or {}
        price = h.get("price")
        if a.get("active") and price is not None:
            hit = price >= a["price"] if a["op"] == "above" else price <= a["price"]
            if hit:
                a["active"], a["triggered_at"] = False, now
                fired.append({"kind": "price", "ticker": a["ticker"], "name": h.get("name") or a.get("name"),
                              "op": a["op"], "target": a["price"], "price": price, "ccy": h.get("ccy") or a.get("ccy", "")})
        out.append(a)
    return fired, out


def check_scores(rule, scores, state):
    """scores: {ticker: {kind: valoare}}. Prima valoare vazuta devine reper, fara alerta.
    Alerta cand scorul trece sub prag sau scade cu cel putin `drop` puncte fata de reper."""
    state = copy.deepcopy(state or {})
    fired = []
    if not rule.get("enabled"):
        return fired, state
    below, drop = rule["below"], rule["drop"]
    for ticker, by_kind in scores.items():
        for kind in rule.get("kinds") or ():
            value = (by_kind or {}).get(kind)
            if value is None:
                continue
            st_ = state.setdefault(ticker, {}).get(kind)
            if st_ is None:
                state[ticker][kind] = {"base": value, "below": value < below}
                continue
            reason = None
            if value < below and not st_["below"]:
                reason = "below"
            elif st_["base"] - value >= drop:
                reason = "drop"
            if reason:
                fired.append({"kind": "score", "ticker": ticker, "score_kind": kind, "reason": reason,
                              "value": value, "previous": st_["base"], "threshold": below if reason == "below" else drop})
                st_["base"] = value
            st_["base"] = max(st_["base"], value)
            if value < below:
                st_["below"] = True
            elif value >= below + SCORE_RESET:
                st_["below"] = False
            state[ticker][kind] = st_
    return fired, state


def check_concentration(rule, weights, state):
    """weights: {ticker: % din portofoliu}. Alerta la depasirea limitei, repetabila dupa ce scade sub limita - CONC_RESET."""
    state = dict(state or {})
    fired = []
    if not rule.get("enabled"):
        return fired, state
    limit = float(rule["max_pct"])
    for ticker, pct in weights.items():
        over = bool(state.get(ticker))
        if pct > limit and not over:
            fired.append({"kind": "concentration", "ticker": ticker, "pct": pct, "limit": limit})
            state[ticker] = True
        elif pct < limit - CONC_RESET and over:
            state[ticker] = False
    return fired, state


def check_events(rule, timelines, state):
    """timelines: {ticker: [evenimente]}. Doar evenimentele marcate "alert". La prima vedere a unui ticker
    evenimentele existente devin reper, fara alerta; apoi fiecare eveniment nou se anunta o data."""
    state = copy.deepcopy(state or {})
    fired = []
    if not rule.get("enabled"):
        return fired, state
    for ticker, events in timelines.items():
        important = [e for e in events or [] if e.get("alert") and e.get("id")]
        seen = state.get(ticker)
        if seen is not None:
            fired += [{"kind": "event", "ticker": ticker, "event_kind": e.get("kind"), "date": e.get("date"),
                       "title": e.get("title"), "link": e.get("link")} for e in important if e["id"] not in seen]
        ids = list(seen or []) + [e["id"] for e in important if e["id"] not in (seen or [])]
        state[ticker] = ids[-EVENTS_KEEP:]
    return fired, state


def timelines_of(strategy_cache, tickers):
    return {t: ((strategy_cache.get(t) or {}).get("m") or {}).get("events") or [] for t in tickers}


# ---------------------------------------------------------------------------
# Date curente
# ---------------------------------------------------------------------------
def merge_holdings(t212_positions, instruments, t212_ccy, xtb, base_ccy, fx):
    """Pozitiile din toate conturile, pe ticker: nume, pret curent (moneda instrumentului) si valoare in base_ccy."""
    meta = {i.get("ticker"): i for i in instruments or []}
    out = {}

    def add(ticker, name, price, ccy, value):
        if not ticker:
            return
        h = out.setdefault(ticker, {"name": name or ticker, "price": price, "ccy": ccy, "value": 0.0})
        if h["price"] is None and price is not None:
            h["price"], h["ccy"] = price, ccy
        h["value"] += value or 0.0

    for p in t212_positions or []:
        ticker = p.get("ticker")
        ccy = (meta.get(ticker) or {}).get("currencyCode") or ""
        price, qty = p.get("currentPrice"), p.get("quantity") or 0.0
        if ccy == "GBX" and price is not None:
            price, ccy = price / 100, "GBP"
        value = qty * price * fx(ccy, base_ccy) if price is not None and ccy else None
        add(ticker, (meta.get(ticker) or {}).get("name"), price, ccy, value)
    for r in xtb or []:
        value = r.get("value_account")
        if value is not None and r.get("account_currency"):
            value *= fx(r["account_currency"], base_ccy)
        add(r.get("ticker"), r.get("name"), r.get("currentPrice"), r.get("currencyCode"), value)
    return out


def fill_names(holdings, quality):
    """Pozitiile fara nume (nume = simbol, frecvent la XTB) primesc numele Yahoo din cache-ul de scoruri."""
    for ticker, h in holdings.items():
        if not h.get("name") or h["name"] == ticker:
            h["name"] = (quality.get(ticker) or {}).get("name") or h.get("name") or ticker
    return holdings


def weights_of(holdings):
    total = sum(h["value"] for h in holdings.values() if h.get("value"))
    if total <= 0:
        return {}
    return {t: h["value"] / total * 100 for t, h in holdings.items() if h.get("value")}


def scores_of(quality_cache, tickers):
    out = {}
    for t in tickers:
        q = quality_cache.get(t) or {}
        out[t] = {
            "quality": q.get("total") if (q.get("coverage") or 0) >= 50 else None,
            "risk": q.get("risk_total") if (q.get("risk_coverage") or 0) >= 50 else None,
            "dividend": q.get("div_total") if (q.get("div_coverage") or 0) >= 50 else None,
        }
    return out


def current_holdings():
    from core import load_config, QUALITY_CACHE_FILE
    from portfolio_model import fx
    from t212_api import fetch_account_currency, load_cached_snapshot
    from xtb_positions import xtb_rows

    snap = load_cached_snapshot() or {}
    xtb = xtb_rows()
    t212_ccy = None
    if snap.get("positions"):
        cfg = load_config()
        t212_ccy, _ = fetch_account_currency(cfg.get("api_key_id"), cfg.get("api_secret"))
    base = t212_ccy or next((r.get("account_currency") for r in xtb if r.get("account_currency")), None) or "EUR"
    holdings = merge_holdings(snap.get("positions") if t212_ccy else [], snap.get("instruments"), t212_ccy, xtb, base, fx)
    quality = load_json_file(QUALITY_CACHE_FILE, {})
    return fill_names(holdings, quality), quality


# ---------------------------------------------------------------------------
# Evaluare si trimitere
# ---------------------------------------------------------------------------
def load_log():
    return load_json_file(LOG_FILE, [])


def dismiss(ts=None):
    """Marcheaza ca vazute alertele din jurnal (toate, sau doar cea cu ts dat)."""
    def updater(log):
        for e in log:
            if ts is None or e.get("ts") == ts:
                e["seen"] = True
        return log
    update_json_file(LOG_FILE, [], updater)


def _user_lang():
    try:
        with open(os.path.join(user_dir(), "ui_prefs.json"), encoding="utf-8") as f:
            return "EN" if str(json.load(f).get("lang", "")).upper() == "EN" else "RO"
    except Exception:
        return "RO"


def describe(e, lang="RO"):
    from i18n import t
    name = e.get("name") or e["ticker"]
    if e["kind"] == "price":
        return t("pa.msg.price_" + e["op"], _lang=lang, name=name, price="%.2f %s" % (e["price"], e.get("ccy", "")),
                 target="%.2f" % e["target"]).strip()
    if e["kind"] == "event":
        kind = t("st.kind." + e["event_kind"], _lang=lang) if e.get("event_kind") else ""
        return t("pa.msg.event", _lang=lang, name=name, kind=kind, date=e.get("date") or "", title=e.get("title") or "")
    if e["kind"] == "score":
        return t("pa.msg.score_" + e["reason"], _lang=lang, name=name, kind=t("pa.kind." + e["score_kind"], _lang=lang),
                 value="%.0f" % e["value"], prev="%.0f" % e["previous"], th="%.0f" % e["threshold"])
    return t("pa.msg.concentration", _lang=lang, name=name, pct="%.1f" % e["pct"], limit="%.0f" % e["limit"])


def evaluate(user=None, now=None, holdings=None, quality=None, timelines=None):
    """Ruleaza toate regulile; salveaza starea si jurnalul; trimite un email cu alertele noi. Intoarce alertele declansate."""
    now = now or time.time()
    rules = load_rules()
    if not (rules["price"] or rules["score"]["enabled"] or rules["concentration"]["enabled"]
            or rules["events"]["enabled"]):
        return []
    if holdings is None:
        holdings, quality = current_holdings()
    state = load_json_file(STATE_FILE, {})

    fired_p, price_alerts = check_prices(rules["price"], holdings, now)
    fired_s, state["score"] = check_scores(rules["score"], scores_of(quality or {}, holdings), state.get("score"))
    fired_c, state["concentration"] = check_concentration(rules["concentration"], weights_of(holdings), state.get("concentration"))
    if timelines is None and rules["events"]["enabled"]:
        import strategies
        timelines = timelines_of(strategies.load_cache(), holdings)
    fired_e, state["events"] = check_events(rules["events"], timelines or {}, state.get("events"))
    save_json_file(STATE_FILE, state)
    if fired_p:
        fired_ids = {a["id"] for a in price_alerts if a.get("triggered_at") == now}

        def fn(r):
            for a in r["price"]:
                if a.get("id") in fired_ids:
                    a["active"], a["triggered_at"] = False, now
        _update_rules(fn)

    fired = fired_p + fired_s + fired_c + fired_e
    if not fired:
        return []
    for e in fired:
        e["ts"], e["seen"] = now, False
        e["name"] = e.get("name") or (holdings.get(e["ticker"]) or {}).get("name")
    update_json_file(LOG_FILE, [], lambda log: (list(log) + fired)[-LOG_KEEP:])
    _send(fired, user or current_user())
    return fired


def _send(fired, user):
    import notify
    import users
    from i18n import t

    email = users.email(user) if user else None
    if not email:
        return False
    lang = _user_lang()
    body = t("pa.mail_intro", _lang=lang) + "\n\n" + "\n".join("- " + describe(e, lang) for e in fired)
    return notify.notify("positions", t("pa.mail_subject", _lang=lang, n=len(fired)), body, to=[email],
                         key="positions:%s:%s" % (user, fired[0]["ts"]), min_hours=0, sync=True)
