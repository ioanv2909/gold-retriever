"""Setari -> Log (admin): ultimele linii scrise de aplicatie pe stdout/stderr, tinute in memorie de logwatch."""
import time

import streamlit as st

import logstore
import logwatch
import users
from i18n import t

SIZES = (100, 300, 1000, 5000)


def render_log(me):
    if users.role(me) != "admin":  # tabul e construit doar pentru admini; a doua verificare, aici
        st.error(t("lg.admin_only"))
        return
    st.caption(t("lg.caption", n=logwatch.TAIL))
    c1, c2, c3, c4, c5 = st.columns([2, 3, 4, 3, 2], vertical_alignment="bottom")
    n = c1.selectbox(t("lg.lines"), SIZES, index=1, key="lg_n")
    order = c2.selectbox(t("lg.order"), ("desc", "asc"), format_func=lambda o: t("lg.order_" + o), key="lg_order")
    query = c3.text_input(t("lg.filter"), key="lg_q")
    hide = c4.checkbox(t("lg.hide_noise"), value=True, key="lg_hide")
    if c5.button(t("lg.refresh"), key="lg_refresh"):
        st.rerun()
    lines = logwatch.tail(n, hide_noise=hide, query=query.strip(), newest_first=order == "desc")
    if not lines:
        st.info(t("lg.empty"))
    else:
        text = "\n".join(lines)
        st.caption(t("lg.shown", n=len(lines)))
        st.code(text, language=None, line_numbers=False, wrap_lines=True, height=600)
        st.download_button(t("lg.download"), text, file_name=time.strftime("goldretriever-log-%Y%m%d-%H%M.txt"),
                           mime="text/plain", key="lg_dl")
    with st.expander(t("lg.store_title")):
        render_store()


def _mb(n):
    return "%.1f MB" % (n / 1024 / 1024)


def render_store():
    """Fisierele de log de pe disc: spatiu, descarcare, arhivare, stergerea arhivelor vechi, praguri de alerta."""
    u = logstore.usage()
    c1, c2, c3 = st.columns(3)
    c1.metric(t("lg.st_logs"), _mb(u["logs"]))
    c2.metric(t("lg.st_archives"), _mb(u["archives"]))
    if u["free_pct"] is not None:
        c3.metric(t("lg.st_free"), "%.1f GB" % (u["disk_free"] / 1024 ** 3), "%.1f%%" % u["free_pct"], delta_color="off")
    fl = logstore.files()
    if fl:
        st.dataframe([{t("lg.st_day"): f["day"].strftime("%d.%m.%Y"), t("lg.st_file"): f["name"],
                       t("lg.st_size"): _mb(f["size"]),
                       t("lg.st_state"): t("lg.st_archived") if f["archived"] else t("lg.st_plain")} for f in fl],
                     hide_index=True, width="stretch", height=min(400, 38 + 35 * len(fl)))
        d1, d2 = st.columns([3, 2], vertical_alignment="bottom")
        name = d1.selectbox(t("lg.st_pick"), [f["name"] for f in fl], key="lg_st_pick")
        if name:
            try:
                d2.download_button(t("lg.st_download"), logstore.read(name), file_name=name,
                                   mime="application/gzip" if name.endswith(".gz") else "text/plain", key="lg_st_dl")
            except OSError as e:
                d2.error(str(e))
    else:
        st.info(t("lg.st_none"))

    cfg = logstore.load_settings()
    st.markdown(t("lg.st_settings"))
    s1, s2, s3 = st.columns(3)
    days = s1.number_input(t("lg.st_auto"), 0, 3650, cfg["archive_after_days"], key="lg_st_auto", help=t("lg.st_auto_help"))
    mb = s2.number_input(t("lg.st_alert_mb"), 0, 100000, cfg["alert_logs_mb"], key="lg_st_mb", help=t("lg.st_zero_off"))
    pct = s3.number_input(t("lg.st_alert_pct"), 0, 90, cfg["alert_free_pct"], key="lg_st_pct", help=t("lg.st_zero_off"))
    if st.button(t("lg.st_save"), key="lg_st_save"):
        logstore.save_settings({"archive_after_days": days, "alert_logs_mb": mb, "alert_free_pct": pct})
        st.success(t("lg.st_saved"))

    st.markdown(t("lg.st_actions"))
    a1, a2 = st.columns(2, vertical_alignment="bottom")
    older = a1.number_input(t("lg.st_older"), 1, 3650, max(1, cfg["archive_after_days"] or 7), key="lg_st_older")
    if a2.button(t("lg.st_archive_now"), key="lg_st_arch"):
        st.success(t("lg.st_archived_n", n=logstore.archive_older_than(older)))
    b1, b2 = st.columns(2, vertical_alignment="bottom")
    keep = b1.number_input(t("lg.st_delete_older"), 1, 3650, 90, key="lg_st_del_days")
    sure = b1.checkbox(t("lg.st_confirm", n=keep), key="lg_st_sure")
    if b2.button(t("lg.st_delete_now"), key="lg_st_del", disabled=not sure, type="primary"):
        st.success(t("lg.st_deleted_n", n=logstore.delete_archives_older_than(keep)))
