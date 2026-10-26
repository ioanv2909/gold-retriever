"""Setari -> Stare (admin): surse externe, backup, joburi din fundal, watchdog. Indicator + text pe fiecare rand."""
import json
import os
import time

import streamlit as st

import health
from i18n import t

DOTS = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}


def _dot(level, text):
    return "%s %s" % (DOTS[level], text)


def _ago(ts, now=None):
    if not ts:
        return "—"
    s = max(0, (now or time.time()) - ts)
    if s < 90:
        return t("hs.ago_s", n=int(s))
    if s < 5400:
        return t("hs.ago_m", n=int(s // 60))
    if s < 2 * 86400:
        return t("hs.ago_h", n=int(s // 3600))
    return t("hs.ago_d", n=int(s // 86400))


def _sources():
    rows = []
    for src in health.SOURCES:
        s = health.status(src)
        err = ""
        if s["last_fail"]:
            err = "%s · %s" % (_ago(s["last_fail"]), s["error"] or "")
        rows.append({
            t("hs.col.service"): t("hs.src." + src),
            t("hs.col.state"): _dot(s["level"], t("hs.level." + s["level"])),
            t("hs.col.last_ok"): _ago(s["last_ok"]),
            t("hs.col.requests"): t("hs.req", n=s["n_1h"], f=s["fail_1h"]) if s["n_1h"] else "—",
            t("hs.col.ms"): "%.0f ms" % s["avg_ms_1h"] if s["avg_ms_1h"] is not None else "—",
            t("hs.col.last_error"): err or "—",
        })
    rows.append(_backup_row())
    rows.append(_uptime_row())
    return rows


def _uptime_row():
    """Watchdog-ul de pe gazda (cron): daca ruleaza si ce a vazut la ultima verificare."""
    import uptime
    s = uptime.load()
    last = s.get("last_check")
    if not last:
        level, text = "gray", t("up.not_installed")
    elif time.time() - last > 3 * uptime.CHECK_EVERY:
        level, text = "yellow", t("up.not_running")
    elif not s.get("last_ok_check"):
        level, text = "red", t("hs.level.red")
    else:
        level, text = "green", t("hs.level.green")
    return {
        t("hs.col.service"): t("hs.src.uptime"),
        t("hs.col.state"): _dot(level, text),
        t("hs.col.last_ok"): _ago(s.get("last_ok")),
        t("hs.col.requests"): t("up.last_check", ago=_ago(last)) if last else "—",
        t("hs.col.ms"): "—",
        t("hs.col.last_error"): s.get("detail") if last and not s.get("last_ok_check") else "—",
    }


def _backup_row():
    import alerts
    try:
        with open(alerts.BACKUP_STATUS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ts = float(data.get("ts", 0)) or None
        encrypted = data.get("encrypted") is True
    except Exception:
        ts, encrypted = None, False
    note = "—"
    if ts is None:
        level = "gray"
    elif (time.time() - ts) / 3600 > alerts.BACKUP_MAX_AGE_H:
        level, note = "red", t("hs.backup_limit", h=alerts.BACKUP_MAX_AGE_H)
    elif not encrypted:
        level, note = "yellow", t("hs.backup_plain")
    else:
        level = "green"
    return {
        t("hs.col.service"): t("hs.src.backup"),
        t("hs.col.state"): _dot(level, t("hs.backup_plain_short") if level == "yellow" else t("hs.level." + level)),
        t("hs.col.last_ok"): _ago(ts),
        t("hs.col.requests"): "—", t("hs.col.ms"): "—",
        t("hs.col.last_error"): note,
    }


SHARED_JOBS = ("quality", "market", "events", "exposure", "strategies")
USER_JOBS = ("dividends", "ratings", "xtb_prices", "watchlist")


def _job_files():
    import core
    import events
    import exposure
    import strategies
    from background import MARKET_CONTEXT_STATUS_FILE, QUALITY_STATUS_FILE
    return {
        "dividends": (core.DIVIDENDS_STATUS_FILE, core.DIVIDENDS_REFRESH_INTERVAL),
        "ratings": (core.RATINGS_STATUS_FILE, core.RATINGS_REFRESH_INTERVAL),
        "quality": (QUALITY_STATUS_FILE, core.QUALITY_REFRESH_INTERVAL),
        "market": (MARKET_CONTEXT_STATUS_FILE, core.MARKET_CONTEXT_REFRESH_INTERVAL),
        "events": (events.EVENTS_STATUS_FILE, 3600),
        "exposure": (exposure.EXPOSURE_STATUS_FILE, 3600),
        "strategies": (strategies.STRATEGY_STATUS_FILE, 3600),
        "xtb_prices": (core.XTB_PRICES_STATUS_FILE, core.XTB_PRICES_REFRESH_INTERVAL),
        "watchlist": (core.WATCHLIST_STATUS_FILE, core.WATCHLIST_REFRESH_INTERVAL),
    }


def _job_row(key, path, interval, who):
    import core
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    raw = core.load_json_file(path, {}) if mtime else {}
    level, why = health.job_level(raw, core.read_status(path) if mtime else {}, mtime, interval)
    return {
        t("hs.col.job"): t("hs.job." + key),
        t("hs.col.user"): who,
        t("hs.col.state"): _dot(level, t("hs.job_state." + why)),
        t("hs.col.last_run"): _ago(mtime),
        t("hs.col.progress"): "%s/%s" % (raw.get("done", 0), raw.get("total", 0)) if raw.get("total") else "—",
        t("hs.col.interval"): t("hs.every_m", n=interval // 60) if interval < 3600 else t("hs.every_h", n=interval // 3600),
    }


def _jobs():
    """Joburile comune o data; cele per utilizator pentru fiecare utilizator."""
    import users
    from userctx import as_user
    files = _job_files()
    rows = [_job_row(k, *files[k], t("hs.all_users")) for k in SHARED_JOBS]
    for name in users.names():
        with as_user(name):
            # caile se rezolva in interiorul blocului, pentru utilizatorul respectiv
            rows += [_job_row(k, os.fspath(files[k][0]), files[k][1], name) for k in USER_JOBS]
    return rows


def _probes():
    results = []
    for src, fn in (("yahoo", health.probe_yahoo), ("justetf", health.probe_justetf),
                    ("t212", health.probe_t212), ("smtp", health.probe_smtp), ("sec", health.probe_sec)):
        ok, msg = fn()
        level = "gray" if ok is None else ("green" if ok else "red")
        results.append((src, level, msg))
    return results


def render_status(me):
    c1, c2 = st.columns([6, 2], vertical_alignment="center")
    c1.caption(t("hs.caption"))
    if c2.button(t("hs.probe"), key="hs_probe"):
        with st.spinner(t("hs.probing")):
            st.session_state["_hs_probe"] = (time.time(), _probes())
    probe = st.session_state.get("_hs_probe")
    if probe:
        st.markdown("**%s** (%s)" % (t("hs.probe_result"), _ago(probe[0])))
        for src, level, msg in probe[1]:
            st.markdown("%s **%s**: %s" % (DOTS[level], t("hs.src." + src), msg))

    st.markdown("#### " + t("hs.sources"))
    st.dataframe(_sources(), hide_index=True, width="stretch")
    st.caption(t("hs.sources_note"))

    st.markdown("#### " + t("hs.jobs"))
    st.dataframe(_jobs(), hide_index=True, width="stretch")
    st.caption(t("hs.jobs_note"))

    import logwatch
    n = len(logwatch.recent())
    st.markdown("#### " + t("hs.watchdog"))
    st.markdown(_dot("green" if n == 0 else "yellow", t("hs.watchdog_n", n=n)))
