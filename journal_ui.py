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


def render_journal_tab(names=None):
    ops = journal.load_all(names)
    if not ops:
        st.info(t("jr.empty"))
        return

    accounts = sorted({op["account"] for op in ops})
    present = [k for k in journal.TYPES if any(op["type"] == k for op in ops)]
    c1, c2, c3 = st.columns([2, 5, 3], vertical_alignment="bottom")
    period = c1.selectbox(t("jr.period"), PERIODS, index=4, format_func=lambda p: t("jr.period." + p), key="jr_period")
    types = c2.multiselect(t("jr.types"), present, default=present,
                           format_func=lambda k: t("jr.type." + k), key="jr_types")
    chosen = c3.multiselect(t("jr.accounts"), accounts, default=accounts, key="jr_accounts") if len(accounts) > 1 else accounts

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
