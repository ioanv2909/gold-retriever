"""Logul aplicatiei pe disc: cate un fisier pe zi in data/logs/ (app-AAAA-LL-ZZ.log), arhivarea (gzip) celor
mai vechi de N zile, stergerea arhivelor vechi si verificarea periodica a spatiului (logurile si discul).
Liniile vin din logwatch (tee pe stdout/stderr). Setarile: data/log_settings.json (admin, Setari -> Log)."""
import gzip
import os
import re
import shutil
import threading
import time
from datetime import date, datetime, timedelta

import notify

LOG_DIR = os.path.join(notify.DATA_ROOT, "logs")
SETTINGS_FILE = os.path.join(notify.DATA_ROOT, "log_settings.json")
DEFAULTS = {"archive_after_days": 7, "alert_logs_mb": 200, "alert_free_pct": 10}
CHECK_EVERY = 3600
_NAME = re.compile(r"^app-(\d{4}-\d{2}-\d{2})\.log(\.gz)?$")

_lock = threading.Lock()
_fh = {"day": None, "f": None}
_state = {"last_check": 0.0}


def load_settings():
    data = notify._read(SETTINGS_FILE, {})
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        try:
            if k in data:
                out[k] = max(0, int(data[k]))
        except (TypeError, ValueError):
            pass
    return out


def save_settings(values):
    cur = load_settings()
    cur.update({k: max(0, int(v)) for k, v in values.items() if k in DEFAULTS})
    notify._write(SETTINGS_FILE, cur)
    return cur


def write(ts, line):
    """Adauga linia in fisierul zilei (ora locala). Nu scrie nimic pe stdout: e apelat din tee."""
    day = time.strftime("%Y-%m-%d", time.localtime(ts))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    try:
        with _lock:
            if _fh["day"] != day or _fh["f"] is None:
                if _fh["f"] is not None:
                    _fh["f"].close()
                os.makedirs(LOG_DIR, exist_ok=True)
                _fh["f"] = open(os.path.join(LOG_DIR, "app-%s.log" % day), "a", encoding="utf-8", buffering=1)
                _fh["day"] = day
            _fh["f"].write("%s  %s\n" % (stamp, line))
    except Exception:
        _fh["f"] = None  # disc plin sau fara drept de scriere: aplicatia merge mai departe


def files():
    """Fisierele de log, cele mai noi primele: {name, day, size, archived}."""
    out = []
    try:
        names = os.listdir(LOG_DIR)
    except OSError:
        return out
    for n in names:
        m = _NAME.match(n)
        if not m:
            continue
        try:
            size = os.path.getsize(os.path.join(LOG_DIR, n))
        except OSError:
            continue
        out.append({"name": n, "day": date.fromisoformat(m.group(1)), "size": size, "archived": bool(m.group(2))})
    return sorted(out, key=lambda f: (f["day"], f["archived"]), reverse=True)


def path_of(name):
    """Calea unui fisier din lista (doar nume valide, fara cai)."""
    if not _NAME.match(str(name)):
        raise ValueError("invalid log file name")
    return os.path.join(LOG_DIR, name)


def read(name):
    p = path_of(name)
    if name.endswith(".gz"):
        with gzip.open(p, "rb") as f:
            return f.read()
    with open(p, "rb") as f:
        return f.read()


def archive_older_than(days, today=None):
    """Comprima (gzip) fisierele .log mai vechi de `days` zile; fisierul zilei curente nu se atinge.
    Intoarce numarul de fisiere arhivate."""
    today = today or date.today()
    limit = today - timedelta(days=max(1, int(days)))
    done = 0
    for f in files():
        if f["archived"] or f["day"] >= limit or f["day"] >= today:
            continue
        src = path_of(f["name"])
        dst = src + ".gz"
        try:
            with open(src, "rb") as fin, gzip.open(dst + ".tmp", "wb") as fout:
                shutil.copyfileobj(fin, fout)
            os.replace(dst + ".tmp", dst)
            os.remove(src)
            done += 1
        except OSError:
            try:
                os.remove(dst + ".tmp")
            except OSError:
                pass
    return done


def delete_archives_older_than(days, today=None):
    """Sterge arhivele (.log.gz) mai vechi de `days` zile. Fisierele nearhivate raman. Intoarce numarul sters."""
    today = today or date.today()
    limit = today - timedelta(days=max(1, int(days)))
    done = 0
    for f in files():
        if f["archived"] and f["day"] < limit:
            try:
                os.remove(path_of(f["name"]))
                done += 1
            except OSError:
                pass
    return done


def usage():
    """Spatiul ocupat de loguri si spatiul de pe discul cu data/."""
    fl = files()
    logs = sum(f["size"] for f in fl if not f["archived"])
    archives = sum(f["size"] for f in fl if f["archived"])
    try:
        du = shutil.disk_usage(notify.DATA_ROOT)
        total, free = du.total, du.free
    except OSError:
        total = free = None
    return {"logs": logs, "archives": archives, "files": len(fl), "disk_total": total, "disk_free": free,
            "free_pct": (free / total * 100) if total else None}


def problems(u, cfg):
    """Pragurile depasite: lista de texte (RO, pentru email)."""
    out = []
    mb = (u["logs"] + u["archives"]) / 1024 / 1024
    if cfg["alert_logs_mb"] and mb > cfg["alert_logs_mb"]:
        out.append("Logurile ocupă %.0f MB (prag %d MB)." % (mb, cfg["alert_logs_mb"]))
    if cfg["alert_free_pct"] and u["free_pct"] is not None and u["free_pct"] < cfg["alert_free_pct"]:
        out.append("Spațiu liber pe disc: %.1f%% (%.1f GB), sub pragul de %d%%." % (
            u["free_pct"], u["disk_free"] / 1024 ** 3, cfg["alert_free_pct"]))
    return out


def check(now=None, send=True):
    """Arhivarea automata si verificarea spatiului; cel mult o data la CHECK_EVERY (apelat din logwatch)."""
    now = now or time.time()
    if now - _state["last_check"] < CHECK_EVERY:
        return None
    _state["last_check"] = now
    cfg = load_settings()
    archived = archive_older_than(cfg["archive_after_days"]) if cfg["archive_after_days"] else 0
    u = usage()
    bad = problems(u, cfg)
    if bad and send:
        body = "\n".join(bad) + "\n\nArhivare și ștergere: Setări → Log → Arhivă și spațiu pe disc."
        notify.notify("logs", "Spațiu: " + bad[0], body, key="logspace:" + datetime.fromtimestamp(now).strftime("%Y%m%d"),
                      min_hours=24)
    return {"archived": archived, "usage": u, "problems": bad}
