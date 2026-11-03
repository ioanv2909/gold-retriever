"""Tab-ul Jurnal din pagina principala: operatiunile de cont filtrate dupa tip, cont si perioada."""
from datetime import date

import pandas as pd
import streamlit as st

import journal
from i18n import t
from privacy import hidden, mask

PERIODS = ("30d", "90d", "ytd", "365d", "all", "custom")


def _fmt(v):
    return mask(f"{float(v):+,.2f}") if v is not None else ""


def _set_all(key, options, value):
    for o in options:
        st.session_state[f"{key}_{o}"] = value


def check_dropdown(container, label, options, key, fmt=str):
    """Lista dropdown cu bife: un popover cu cate o casuta pentru fiecare optiune (toate bifate la inceput)."""
    for o in options:
        st.session_state.setdefault(f"{key}_{o}", True)
    chosen = [o for o in options if st.session_state[f"{key}_{o}"]]
    if len(chosen) == len(options):
        summary = t("jr.all")
    elif len(chosen) == 1:
        summary = fmt(chosen[0])
    else:
        summary = t("jr.n_of", n=len(chosen), m=len(options))
    with container.popover(f"{label}: {summary}", width="stretch"):
        b1, b2 = st.columns(2)
        b1.button(t("jr.check_all"), key=f"{key}__all", on_click=_set_all, args=(key, options, True), type="tertiary")
        b2.button(t("jr.check_none"), key=f"{key}__none", on_click=_set_all, args=(key, options, False), type="tertiary")
        for o in options:
            st.checkbox(fmt(o), key=f"{key}_{o}")
    return [o for o in options if st.session_state[f"{key}_{o}"]]


def _t212_download():
    """Butonul care porneste acum descarcarea tranzactiilor si a ordinelor T212 (cu comisioane)."""
    try:
        from core import load_config
        cfg = load_config()
        if not (cfg.get("api_key_id") and cfg.get("api_secret")):
            return
        import returns_summary
        import t212_history_rebuild
    except Exception:
        return
    busy = returns_summary.running() or t212_history_rebuild.running()
    c1, c2 = st.columns([3, 7], vertical_alignment="center")
    if c1.button(t("jr.t212_now"), key="jr_t212_now", disabled=busy):
        returns_summary.start_refresh()
        t212_history_rebuild.ensure_async(force=True)
        busy = True
    if busy:
        c2.caption(t("jr.t212_busy"))


def render_journal_tab(names=None):
    _t212_download()
    ops = journal.load_all(names)
    if not ops:
        st.info(t("jr.empty"))
        return

    accounts = sorted({op["account"] for op in ops})
    present = [k for k in journal.TYPES if any(op["type"] == k for op in ops)]
    c1, c2, c3 = st.columns([3, 4, 3], vertical_alignment="bottom")
    period = c1.selectbox(t("jr.period"), PERIODS, index=4, format_func=lambda p: t("jr.period." + p), key="jr_period")
    types = check_dropdown(c2, t("jr.types"), present, "jr_types", fmt=lambda k: t("jr.type." + k))
    chosen = check_dropdown(c3, t("jr.accounts"), accounts, "jr_accounts") if len(accounts) > 1 else accounts

    start, end = journal.period_start(period), None
    if period == "custom":
        first = min(op["date"] for op in ops)
        rng = st.date_input(t("jr.range"), (first, date.today()), key="jr_range", format="DD.MM.YYYY")
        start, end = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (rng[0] if rng else None, None)

    rows = journal.filter_ops(ops, set(types), set(chosen), start, end)
    if not rows:
        st.info(t("jr.none"))
        return

    sums = journal.totals(rows)
    st.dataframe(pd.DataFrame([{
        t("jr.col.type"): t("jr.type." + k), t("jr.col.ccy"): ccy, t("jr.col.count"): n, t("jr.col.total"): _fmt(s),
    } for (k, ccy), (n, s) in sorted(sums.items(), key=lambda kv: (journal.TYPES.index(kv[0][0]), kv[0][1]))]),
        hide_index=True, width="content")

    df = pd.DataFrame([{
        t("jr.col.date"): op["date"].strftime("%d.%m.%Y"),
        t("jr.col.account"): op["account"],
        t("jr.col.type"): t("jr.type." + op["type"]) if op["type"] != "other" else (op["raw_type"] or t("jr.type.other")),
        t("jr.col.instrument"): op["instrument"],
        t("jr.col.amount"): _fmt(op["amount"]),
        t("jr.col.ccy"): op["ccy"],
        t("jr.col.comment"): op["comment"],
    } for op in rows])
    st.caption(t("jr.count", n=len(rows)))
    st.dataframe(df, hide_index=True, width="stretch")
    if not hidden():
        csv = pd.DataFrame([{**op, "date": op["date"].isoformat()} for op in rows]).to_csv(index=False)
        st.download_button(t("jr.csv"), csv, file_name="jurnal.csv", mime="text/csv", key="jr_csv")
    st.caption(t("jr.note"))
