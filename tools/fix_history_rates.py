#!/usr/bin/env python3
"""Diagnostic si curatare pentru punctele din istoric salvate cu un curs valutar inventat (1.0).

Pana la v0.3.5, cand Yahoo nu raspundea, cursul cadea pe 1.0 si ramanea in cache; punctele din
portfolio_history_multi.json scrise atunci au valori de cateva ori prea mari sau prea mici.

Utilizare (din folderul proiectului, pe host):
  python3 tools/fix_history_rates.py                  # doar arata (fara sume): puncte suspecte, cursuri, raport fata de mediana
  python3 tools/fix_history_rates.py --apply          # scoate punctele cu un curs non-EUR exact 1.0 (copie .bak inainte)
  python3 tools/fix_history_rates.py --apply --max-ratio 2
                                                      # scoate si punctele de peste 2x (sau sub 1/2) fata de mediana celor dinainte
"""
import argparse
import glob
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = 20  # puncte anterioare pentru mediana


def made_up_rate(p):
    return any(c != "EUR" and v == 1.0 for c, v in (p.get("rates") or {}).items())


def total_eur(p):
    """Valoarea totala in EUR cu cursurile salvate in punct (rates[c] = cat face 1 c in moneda pivot)."""
    rates = p.get("rates") or {}
    eur = rates.get("EUR")
    if not eur:
        return None
    total = 0.0
    for e in (p.get("entries") or {}).values():
        r = rates.get(e.get("ccy"))
        if r is None:
            return None
        total += float(e.get("value") or 0) * r / eur
    return total


def analyse(history, max_ratio):
    """Lista de (index, motiv, raport) pentru punctele de scos."""
    bad, ratios, good_totals = [], {}, []
    for i, p in enumerate(history):
        t = total_eur(p)
        med = statistics.median(good_totals[-WINDOW:]) if good_totals else None
        ratio = (t / med) if (t and med) else None
        ratios[i] = ratio
        if made_up_rate(p):
            bad.append((i, "curs 1.0", ratio))
        elif max_ratio and ratio and (ratio > max_ratio or ratio < 1 / max_ratio):
            bad.append((i, "raport %.2f" % ratio, ratio))
        elif t:
            good_totals.append(t)
    return bad, ratios


def rates_text(p):
    return " ".join("%s=%s" % kv for kv in sorted((p.get("rates") or {}).items()))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="scoate punctele gasite (cu copie .bak)")
    ap.add_argument("--max-ratio", type=float, default=0, help="scoate si punctele cu raport peste X sau sub 1/X")
    ap.add_argument("--days", type=int, default=3, help="cate zile recente se afiseaza in detaliu (implicit 3)")
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(ROOT, "data", "users", "*", "portfolio_history_multi.json")))
    files += glob.glob(os.path.join(ROOT, "data", "portfolio_history_multi.json"))
    if not files:
        print("nu am gasit niciun portfolio_history_multi.json")
        return 1
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - args.days * 86400))
    for f in files:
        name = os.path.relpath(f, ROOT)
        try:
            with open(f, encoding="utf-8") as fh:
                history = json.load(fh)
        except Exception as e:
            print("== %s: nu se poate citi (%s)" % (name, type(e).__name__))
            continue
        bad, ratios = analyse(history, args.max_ratio)
        print("== %s: %d puncte, %s .. %s; de scos: %d" % (
            name, len(history), history[0].get("ts") if history else "-", history[-1].get("ts") if history else "-", len(bad)))
        bad_idx = {i for i, _, _ in bad}
        for i, p in enumerate(history):
            if p.get("ts", "") < since and i not in bad_idx:
                continue
            r = ratios.get(i)
            print("   %s %s  %-28s %s" % ("X" if i in bad_idx else " ", p.get("ts"),
                                         "raport %.2f" % r if r else "raport -", rates_text(p)))
        if args.apply and bad:
            backup = "%s.bak-%s" % (f, time.strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(f, backup)
            kept = [p for i, p in enumerate(history) if i not in bad_idx]
            fd, tmp = tempfile.mkstemp(prefix=".fix.", suffix=".tmp", dir=os.path.dirname(f))
            with os.fdopen(fd, "w") as fh:
                json.dump(kept, fh, indent=2)
            shutil.copymode(f, tmp)
            os.replace(tmp, f)
            print("   scos %d puncte; copie: %s" % (len(bad), os.path.relpath(backup, ROOT)))
    if not args.apply:
        print("\n(doar diagnostic; nimic modificat. Ruleaza cu --apply ca sa scoti punctele marcate cu X.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
