from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from etf import get_instrument
from i18n import t
from portfolio_model import fx
from xtb import accounts_summary
from xtb_positions import xtb_holdings, xtb_rows

def _help(key):
    return t("hold.help." + key)


def _hr(strong=False):
    opacity = 0.45 if strong else 0.18
    st.markdown(
        f"<hr style='margin:0.4rem 0 0.6rem 0;border:0;border-top:1px solid rgba(250,250,250,{opacity});'>",
        unsafe_allow_html=True,
    )


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _fmt(v, ccy="", decimals=2, signed=False):
    x = _num(v)
    if x is None:
        return "n/a"
    s = f"{x:+,.{decimals}f}" if signed else f"{x:,.{decimals}f}"
    return f"{s} {ccy}".strip()


def _days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


_W = [3, 0.6, 3, 0.6, 3]


def _op(sign):
    return f"<div style='text-align:center;padding-top:1rem;font-size:1.1rem;opacity:.7'>{sign}</div>"


def _line():
    st.columns(_W)[4].markdown(
        "<hr style='margin:0.1rem 0 0.3rem 0;border:0;border-top:1px solid rgba(250,250,250,0.45);'>",
        unsafe_allow_html=True,
    )


def _render_block(title, acc_ccy, d):
    st.markdown(f"**{title}** ({acc_ccy})")
    qty, avg, px = _num(d["quantity"]), _num(d["avg"]), _num(d["px"])
    ccy = d["instr_ccy"] or ""
    cost, value, pl = _num(d["cost"]), _num(d["value"]), _num(d["pl"])
    div = _num(d["div"]) or 0.0

    pence = ccy in ("GBX", "GBp")
    px_n = px / 100 if (pence and px is not None) else px
    avg_n = avg / 100 if (pence and avg is not None) else avg
    ccy_n = "GBP" if pence else ccy
    diff = bool(ccy_n and acc_ccy and ccy_n != acc_ccy)
    val_i = qty * px_n if (qty is not None and px_n is not None) else None

    # 1) Cantitate x Pret = Valoare (in moneda instrumentului)
    c = st.columns(_W)
    c[0].metric(t("hold.qty"), _fmt(qty, decimals=4), help=_help("qty"))
    c[1].markdown(_op("×"), unsafe_allow_html=True)
    c[2].metric(t("hold.px"), _fmt(px_n, ccy_n), help=_help("px"))
    c[3].markdown(_op("="), unsafe_allow_html=True)
    if diff:
        c[4].metric(t("hold.value"), _fmt(val_i, ccy_n), help=_help("value"))
        # 2) Valoare x Curs = Valoare in moneda contului
        rate = (value / val_i) if (value is not None and val_i) else None
        c2 = st.columns(_W)
        c2[0].metric(t("hold.value"), _fmt(val_i, ccy_n))
        c2[1].markdown(_op("×"), unsafe_allow_html=True)
        c2[2].metric("Curs valutar", "n/a" if rate is None else f"{rate:.4f}",
                     help="Cursul dintre moneda instrumentului și moneda contului, dedus din valoarea curentă a poziției.")
        c2[3].markdown(_op("="), unsafe_allow_html=True)
        c2[4].metric(t("hold.value"), _fmt(value, acc_ccy), help=_help("value"))
    else:
        c[4].metric(t("hold.value"), _fmt(value, acc_ccy), help=_help("value"))

    # 3) Cost (initial), sub valoare
    c3 = st.columns(_W)
    c3[0].metric(t("hold.avg"), _fmt(avg_n, ccy_n), help=_help("avg"))
    c3[4].metric("Cost (inițial)", _fmt(cost, acc_ccy),
                 help="Suma investită, în moneda contului, la cursul de la cumpărare.")
    _line()

    # 4) P/L
    pl_pct = (pl / cost * 100) if (pl is not None and cost) else None
    ret = (px / avg - 1) * 100 if (avg and px) else None
    c4 = st.columns(_W)
    c4[0].metric(t("hold.weight"), "n/a" if d["weight"] is None else f"{d['weight']:.1f}%", help=_help("weight"))
    c4[2].metric("Randament preț (fără curs)", "n/a" if ret is None else f"{ret:+.2f}%",
                 help="Preț curent / preț mediu − 1, în moneda instrumentului, fără efectul cursului valutar.")
    c4[4].metric("= P/L (Valoare − Cost)", _fmt(pl, acc_ccy, signed=True),
                 None if pl_pct is None else f"{pl_pct:+.2f}%",
                 help="Valoare curentă − Cost, în moneda contului. Include și efectul cursului valutar.")

    if diff and ret is not None and pl_pct is not None:
        st.columns(_W)[4].caption(f"din care efect de curs: {pl_pct - ret:+.2f} pp")

    # 5) Dividende si total (doar daca exista dividende)
    if div > 0 and pl is not None:
        yoc = (div / cost * 100) if cost else None
        c5 = st.columns(_W)
        c5[4].metric("+ Dividende încasate", _fmt(div, acc_ccy, signed=True),
                     None if yoc is None else t("hold.of_cost", p=f"{yoc:.2f}"),
                     delta_color="off", help=_help("div"))
        _line()
        tot = pl + div
        c6 = st.columns(_W)
        c6[4].metric("= Total (P/L + dividende)", _fmt(tot, acc_ccy, signed=True),
                     None if not cost else f"{tot / cost * 100:+.2f}%",
                     help="P/L + dividende încasate. Procentul e raportat la cost.")

    parts = [t("hold.days", n=d["days"] if d["days"] is not None else "n/a")]
    parts += d.get("notes", [])
    st.caption(" · ".join(parts))


def _render_total(blocks, disp_ccy):
    qty = cost = val = pl = div = 0.0
    for acc_ccy, d in blocks:
        f = fx(acc_ccy, disp_ccy)
        qty += _num(d["quantity"]) or 0.0
        cost += (_num(d["cost"]) or 0.0) * f
        val += (_num(d["value"]) or 0.0) * f
        pl += (_num(d["pl"]) or 0.0) * f
        div += (_num(d["div"]) or 0.0) * f
    st.markdown("**Dețineri multiple**")
    st.markdown(t("hold.total_title", ccy=disp_ccy))
    c = st.columns(_W)
    c[0].metric(t("hold.total_qty"), f"{qty:,.4f}")
    c[2].metric("Cost (inițial)", _fmt(cost, disp_ccy),
                help="Suma investită, în moneda contului, la cursul de la cumpărare.")
    c[4].metric(t("hold.value"), _fmt(val, disp_ccy), help=_help("value"))
    _line()
    c2 = st.columns(_W)
    c2[4].metric("= P/L (Valoare − Cost)", _fmt(pl, disp_ccy, signed=True),
                 f"{pl / cost * 100:+.2f}%" if cost else None,
                 help="Valoare curentă − Cost, în moneda contului. Include și efectul cursului valutar.")
    if div > 0:
        c3 = st.columns(_W)
        c3[4].metric("+ Dividende încasate", _fmt(div, disp_ccy, signed=True),
                     t("hold.of_cost", p=f"{div / cost * 100:.2f}") if cost else None,
                     delta_color="off", help=_help("div"))
        _line()
        tot = pl + div
        c4 = st.columns(_W)
        c4[4].metric("= Total (P/L + dividende)", _fmt(tot, disp_ccy, signed=True),
                     f"{tot / cost * 100:+.2f}%" if cost else None,
                     help="P/L + dividende încasate. Procentul e raportat la cost.")


def _render_xtb_tables(title, h, boxed=True):
    purchases = h.get("purchases") or []
    events = h.get("dividend_events") or []
    if not purchases and not events:
        return
    with (st.expander(t("hold.expander", title=title)) if boxed else st.container()):
        if not boxed:
            st.caption(t("hold.expander", title=title))
        if purchases:
            st.dataframe(
                pd.DataFrame([
                    {
                        t("hold.col.date"): str(p.get("time") or "")[:16].replace("T", " "),
                        t("hold.col.qty"): p.get("volume"),
                        t("hold.col.price"): p.get("price"),
                        t("hold.col.amount"): abs(_num(p.get("amount")) or 0.0),
                    }
                    for p in purchases
                ]),
                hide_index=True, width="stretch",
            )
        if events:
            st.dataframe(
                pd.DataFrame([
                    {
                        t("hold.col.date"): str(e.get("time") or "")[:16].replace("T", " "),
                        t("hold.col.type"): e.get("type"),
                        t("hold.col.amount"): e.get("amount"),
                    }
                    for e in events
                ]),
                hide_index=True, width="stretch",
            )


def render_holdings_section(ticker, position_row, yahoo_symbol, total_portfolio_value, zile_detinut, account_currency, is_watch):
    isin = position_row.get("isin")
    if not isin:
        try:
            ins = get_instrument(ticker)
            isin = ins.get("isin") if ins else None
        except Exception:
            isin = None
    holdings = sorted(xtb_holdings(ticker, isin, yahoo_symbol), key=lambda h: str(h.get("account")))

    acct_totals = {}
    for r in xtb_rows():
        acct_totals[r["account_key"]] = acct_totals.get(r["account_key"], 0.0) + (_num(r["value_account"]) or 0.0)

    blocks = []
    if not is_watch:
        fxr = _num(position_row.get("fx_rate")) or 1.0
        value_acc = (_num(position_row.get("valoare_curenta")) or 0.0) * fxr
        blocks.append((
            "Trading 212", account_currency or "?", None,
            {
                "quantity": position_row.get("quantity"), "avg": position_row.get("averagePrice"),
                "px": position_row.get("currentPrice"), "instr_ccy": position_row.get("currencyCode") or "",
                "cost": value_acc - (_num(position_row.get("ppl")) or 0.0), "value": value_acc, "pl": position_row.get("ppl"),
                "div": position_row.get("dividende_incasate") or 0.0,
                "weight": (value_acc / total_portfolio_value * 100) if total_portfolio_value else None,
                "days": zile_detinut, "notes": [t("hold.note_t212")],
            },
        ))
    for h in holdings:
        purchases = h.get("purchases") or []
        report = str(h.get("report_time") or "")[:16].replace("T", " ")
        notes = [t("hold.note_xtb", report=report)]
        if h.get("price_ok") is False:
            notes.append(t("hold.note_price"))
        total = acct_totals.get(h.get("account_key")) or 0.0
        value = _num(h.get("value_account"))
        blocks.append((
            h.get("account") or "XTB", h.get("account_currency") or "", h,
            {
                "quantity": h.get("quantity"), "avg": h.get("averagePrice"), "px": h.get("currentPrice"),
                "instr_ccy": h.get("currencyCode") or "", "cost": h.get("cost_account"), "value": h.get("value_account"),
                "pl": h.get("pl_account"), "div": h.get("dividends_account") or 0.0,
                "weight": (value / total * 100) if (value is not None and total) else None,
                "days": _days_since(purchases[0].get("time")) if purchases else None, "notes": notes,
            },
        ))
    if not blocks:
        return

    if len(blocks) == 1:
        title, acc_ccy, h, d = blocks[0]
        _render_block(title, acc_ccy, d)
        if h is not None:
            _render_xtb_tables(title, h)
        return
    disp = (st.session_state.get("_ui_prefs") or {}).get("ccy") or account_currency
    if not disp or disp == "?":
        disp = "EUR"
    _render_total([(acc_ccy, d) for _, acc_ccy, _, d in blocks], disp)
    for title, acc_ccy, h, d in blocks:
        _pl = _num(d["pl"])
        label = f"{title} ({acc_ccy})" + ("" if _pl is None else f" · P/L {_fmt(_pl, acc_ccy, signed=True)}")
        with st.expander(label, expanded=False):
            _render_block(title, acc_ccy, d)
            if h is not None:
                _render_xtb_tables(title, h, boxed=False)


def target_portfolios(ticker, position_row, yahoo_symbol, total_portfolio_value, account_currency, is_watch):
    isin = position_row.get("isin")
    if not isin:
        try:
            ins = get_instrument(ticker)
            isin = ins.get("isin") if ins else None
        except Exception:
            isin = None
    held = {}
    if not is_watch:
        fxr = _num(position_row.get("fx_rate")) or 1.0
        held["Trading 212"] = (_num(position_row.get("valoare_curenta")) or 0.0) * fxr
    for h in xtb_holdings(ticker, isin, yahoo_symbol):
        held[h.get("account")] = held.get(h.get("account"), 0.0) + (_num(h.get("value_account")) or 0.0)
    totals = {}
    for r in xtb_rows():
        totals[r["account"]] = totals.get(r["account"], 0.0) + (_num(r["value_account"]) or 0.0)
    t212_ccy = account_currency if account_currency and account_currency != "?" else "EUR"
    out = [{
        "label": "Trading 212", "currency": t212_ccy,
        "current_value": held.get("Trading 212", 0.0), "total_value": _num(total_portfolio_value) or 0.0,
        "holds": "Trading 212" in held, "value_ref": held.get("Trading 212", 0.0) * fx(t212_ccy, "EUR"),
    }]
    for a in sorted(accounts_summary(), key=lambda x: x["currency"]):
        cur = held.get(a["label"], 0.0)
        out.append({
            "label": a["label"], "currency": a["currency"], "current_value": cur,
            "total_value": totals.get(a["label"], 0.0), "holds": a["label"] in held,
            "value_ref": cur * fx(a["currency"], "EUR"),
        })
    return out
