"""Reguli de alertare: praguri, esecuri consecutive, backup lipsa, import XTB."""
import json
import os
import threading
import time

import notify

FAIL_THRESHOLD = 3
BACKUP_MAX_AGE_H = 26
BACKUP_STATUS_FILE = os.path.join(notify.DATA_ROOT, "backup_status.json")

_FAILS = {}
_LOCK = threading.Lock()


def _mask(text, secrets):
    text = str(text)
    for s in secrets or ():
        if s:
            text = text.replace(str(s), "***")
    return text


def record_refresh(source, user, errors, secrets=()):
    """errors: dict nume -> mesaj (valorile goale inseamna OK).
    Alerteaza dupa FAIL_THRESHOLD esecuri consecutive, cel mult o data pe zi."""
    bad = {k: v for k, v in (errors or {}).items() if v}
    key = (source, user)
    with _LOCK:
        if not bad:
            _FAILS.pop(key, None)
            return False
        n = _FAILS[key] = _FAILS.get(key, 0) + 1
    if n < FAIL_THRESHOLD:
        return False
    lines = ["%s: %s" % (k, _mask(v, secrets)[:160]) for k, v in sorted(bad.items())]
    body = "Actualizarea %s a esuat de %d ori la rand (utilizator: %s).\n\n%s" % (source, n, user, "\n".join(lines))
    return notify.notify("refresh", "Actualizare esuata: %s" % source, body,
                         key="refresh:%s:%s" % (source, user), min_hours=24)


def check_backup(path=None, now=None):
    """Alerteaza daca ultimul backup reusit e prea vechi. Nu alerteaza daca fisierul nu a existat niciodata."""
    try:
        with open(path or BACKUP_STATUS_FILE, encoding="utf-8") as f:
            ts = float(json.load(f).get("ts", 0))
    except Exception:
        return False
    age_h = ((now if now is not None else time.time()) - ts) / 3600
    if age_h <= BACKUP_MAX_AGE_H:
        return False
    body = "Ultimul backup reusit a fost acum %d ore (limita: %d ore)." % (age_h, BACKUP_MAX_AGE_H)
    return notify.notify("backup", "Backup lipsa", body, key="backup-missing", min_hours=24)


def record_xtb_import(reports, errors, user):
    problems = []
    for r in reports or []:
        flags = []
        if not r.get("cash_ok"):
            flags.append("cash check failed")
        if not r.get("positions_ok"):
            flags.append("positions check failed")
        if r.get("unknown_types"):
            flags.append("unknown types: " + ", ".join(r["unknown_types"]))
        if flags:
            problems.append("%s: %s" % (r.get("label"), "; ".join(flags)))
    problems += ["error: %s" % e for e in (errors or [])]
    if not problems:
        return False
    body = "Import XTB cu probleme (utilizator: %s).\n\n%s" % (user, "\n".join(problems))
    return notify.notify("xtb_import", "Import XTB cu probleme", body,
                         key="xtb:%s:%s" % (user, "|".join(sorted(problems))))
