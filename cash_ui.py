"""Butonul de numerar de pe pagina principala (Trading 212 si conturile XTB, convertit in moneda afisata)."""
import streamlit as st

import privacy
from i18n import t
from portfolio_model import fx as _fx
from privacy import mask as _mask
from t212_api import fetch_account_currency
from xtb import load_xtb as _load_xtb


def xtb_cash_items(labels, display_ccy):
    d = _load_xtb()
    items, total = [], 0.0
    for k, a in sorted(d["accounts"].items(), key=lambda kv: kv[1]["currency"]):
        if a["label"] not in labels:
            continue
        amt = sum(o["amount"] for o in d["cash_ops"].get(k, {}).values())
        disp = amt * _fx(a["currency"], display_ccy)
        total += disp
        items.append({"label": a["label"], "amount": amt, "ccy": a["currency"], "disp": disp})
    return items, total


def render_cash(sel_portfolios, display_ccy, cash, api_key_id, api_secret, compact=False):
    rows = []
    tot = 0.0
    sub = None
    if "Trading 212" in sel_portfolios:
        try:
            t212_ccy = fetch_account_currency(api_key_id, api_secret)[0] or display_ccy
        except Exception:
            t212_ccy = display_ccy
        free = float(cash.get("free", 0.0) or 0.0)
        conv = free * _fx(t212_ccy, display_ccy)
        tot += conv
        sub = t("main.cash_sub", blocked=f"{cash.get('blocked', 0.0):,.2f}", result=f"{cash.get('result', 0.0):,.2f}")
        rows.append((t("main.cash_t212"), _mask(f"{free:,.2f} {t212_ccy}"),
                     "" if t212_ccy == display_ccy else _mask(f"≈ {conv:,.2f} {display_ccy}")))
    items, xtot = xtb_cash_items(sel_portfolios, display_ccy)
    for it in items:
        rows.append((t("main.cash_acct", label=it["label"]), _mask(f"{it['amount']:,.2f} {it['ccy']}"),
                     "" if it["ccy"] == display_ccy else _mask(f"≈ {it['disp']:,.2f} {display_ccy}")))
    tot += xtot
    if not rows:
        return
    label = f"💵 {t('main.cash_total')} · " + _mask(f"{tot:,.2f} {display_ccy}")
    with st.container(key="cash_row_c"):
        st.markdown(
            "<style>.st-key-cash_row_c button p {font-size:1.15rem; font-weight:600;}"
            ".st-key-cash_row_c button {min-height:3.2rem;}</style>",
            unsafe_allow_html=True,
        )
        try:
            pop = st.popover(label, width="stretch")
        except TypeError:
            pop = st.popover(label, use_container_width=True)
        with pop:
            for lb, val, eq in rows:
                st.markdown(f"**{lb}:** {val}" + (f" · {eq}" if eq else ""))
            if sub and not privacy.hidden():
                st.caption(sub)
