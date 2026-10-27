"""Setari -> Backup (admin): ultimul backup, backup la cerere si procedura de restaurare.
Containerul nu poate rula scriptul de backup (fara root, fara acces la share), deci butonul scrie o cerere
in data/backup_request.json; cron-ul de root de pe host (--if-requested, la fiecare minut) o preia
si scrie inapoi starea: running, apoi done sau failed."""
import json
import os
import time
from datetime import datetime

import streamlit as st

import alerts
import notify
import users
from core import save_json_file
from i18n import t

REQUEST_FILE = os.path.join(notify.DATA_ROOT, "backup_request.json")
STALE_S = 180       # cererea nepreluata dupa 3 minute: cron-ul --if-requested lipseste
RUNNING_MAX_S = 1800  # "running" mai vechi de atat: scriptul s-a oprit fara sa scrie rezultatul

CRON_LINE = "* * * * * /usr/local/sbin/backup-goldretriever.sh --if-requested >> /var/log/backup-goldretriever.log 2>&1"
TEST_CMD = "gpg --decrypt data-YYYY-MM-DD_HHMMSS-TAG.tar.gz.gpg | tar -tz | head"
RESTORE_CMD = """cd /DATA/AppData/gold-retriever
docker compose down
mv data data.broken
# arhiva criptata: pe un calculator cu cheia privata (sau importata temporar)
gpg --decrypt /mnt/goldretriever/data-YYYY-MM-DD_HHMMSS-TAG.tar.gz.gpg | tar -xz -C .
# arhiva necriptata (veche)
tar -xzf /mnt/goldretriever/data-YYYY-MM-DD_HHMMSS.tar.gz -C .
chown -R 1000:1000 data
docker compose up -d"""


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_request():
    return _read(REQUEST_FILE)


def pending(req=None, now=None):
    """O cerere care inca asteapta sau ruleaza (cele blocate prea mult nu mai conteaza)."""
    req = load_request() if req is None else req
    age = (now or time.time()) - float(req.get("ts") or 0)
    return (req.get("state") == "requested" and age < 3600) or (req.get("state") == "running" and age < RUNNING_MAX_S)


def request_backup(me, now=None):
    if pending(now=now):
        return False
    save_json_file(REQUEST_FILE, {"state": "requested", "ts": now or time.time(), "by": me})
    print(f"[backup] on-demand backup requested user={me}", flush=True)
    return True


def _fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S") if ts else "—"


def _last_backup():
    from health_ui import _ago
    data = _read(alerts.BACKUP_STATUS_FILE)
    ts = float(data.get("ts") or 0) or None
    if not ts:
        st.info(t("bk.none"))
        return
    c1, c2 = st.columns(2)
    c1.metric(t("bk.last"), _fmt(ts), _ago(ts), delta_color="off")
    c2.metric(t("bk.encrypted"), t("bk.yes") if data.get("encrypted") is True else t("bk.no"))
    st.caption(t("bk.file", file=data.get("file") or "—"))
    if data.get("encrypted") is not True:
        st.warning(t("hs.backup_plain"))
    if (time.time() - ts) / 3600 > alerts.BACKUP_MAX_AGE_H:
        st.error(t("bk.too_old", h=alerts.BACKUP_MAX_AGE_H))


@st.fragment(run_every=5)
def _live(me):
    _last_backup()
    req = load_request()
    state, age = req.get("state"), time.time() - float(req.get("ts") or 0)
    if state == "requested":
        if age > STALE_S:
            st.warning(t("bk.stale", m=int(age // 60)))
            st.code(CRON_LINE, language=None)
        else:
            st.info(t("bk.waiting"))
    elif state == "running" and age < RUNNING_MAX_S:
        st.info(t("bk.running"))
    elif state == "done":
        st.success(t("bk.done", ts=_fmt(req.get("ts")), file=req.get("detail") or "—"))
    elif state == "failed":
        st.error(t("bk.failed", ts=_fmt(req.get("ts")), err=req.get("detail") or "—"))
    if st.button(t("bk.now"), key="bk_now", disabled=pending(req), type="primary"):
        if request_backup(me):
            st.rerun(scope="fragment")
    st.caption(t("bk.now_help"))


def render_backup(me):
    if users.role(me) != "admin":  # tabul e construit doar pentru admini; a doua verificare, aici
        st.error(t("lg.admin_only"))
        return
    _live(me)
    st.divider()
    st.markdown("**" + t("bk.restore_title") + "**")
    st.markdown(t("bk.test_help"))
    st.code(TEST_CMD, language="bash")
    st.markdown(t("bk.restore_help"))
    st.code(RESTORE_CMD, language="bash")
    st.caption(t("bk.keys_note"))
    with st.expander(t("bk.setup_title")):
        st.markdown(t("bk.setup_help"))
        st.code(CRON_LINE, language=None)
