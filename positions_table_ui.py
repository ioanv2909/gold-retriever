"""Tabelul de pozitii de pe pagina principala; un rand ales deschide pagina pozitiei."""
import pandas as pd
import streamlit as st

import logos
import privacy
from core import RECOMMENDATION_LABELS
from descriptions import COLUMN_HELP
from i18n import col, t, x as _tx
from xtb import instruments as _xtb_instruments

_COL_HELP_I18N = {"Scor div.": lambda: t("help.div_score"), "Țintă %": lambda: t("help.target_upside")}


def render_positions_table(df, df_display, display_ccy, total_portfolio_value, compact):
    """df: toate pozitiile Trading 212 (pentru pagina de detaliu); df_display: randurile afisate (filtrate)."""
    _c = display_ccy
    logos.prefetch(list(zip(df_display["ticker"], df_display["name"])))
    table_df = pd.DataFrame({
        "Logo": [logos.logo_uri(tk, nm) for tk, nm in zip(df_display["ticker"], df_display["name"])],
        "Nume": df_display["name"],
        "Monedă": df_display["currencyCode"],
        "Cant.": pd.to_numeric(df_display["quantity"], errors="coerce"),
        "Preț mediu": pd.to_numeric(df_display["averagePrice"], errors="coerce"),
        "Preț curent": pd.to_numeric(df_display["currentPrice"], errors="coerce"),
        f"Cost achiz. ({_c})": df_display["cost_disp"],
        f"Val. curentă ({_c})": df_display["value_disp"],
        f"P/L ({_c})": df_display["pl_disp"],
        "Randament %": pd.to_numeric(df_display["randament_%"], errors="coerce"),
        f"Div. ({_c})": df_display["div_disp"],
        "Div/Inv %": pd.to_numeric(df_display["div_pe_investit_%"], errors="coerce"),
        "Rand. total %": pd.to_numeric(df_display["randament_total_%"], errors="coerce"),
        "S&P500 %": df_display["sp500_return_%"],
        "Zile": pd.to_numeric(df_display["zile_detinut"], errors="coerce").round().astype("Int64"),
        "PEG": df_display["peg_ratio_display"],
        "vs S&P500 pp": df_display["alpha_%"],
        "Recomandare": df_display["recomandare"].map(lambda v: RECOMMENDATION_LABELS.get(v, v)),
        "Țintă %": pd.to_numeric(df_display["tinta_%"], errors="coerce"),
        "Scor TL": pd.to_numeric(df_display["Scor"], errors="coerce"),
        "Rating": df_display["Rating"].map(lambda v: _tx(str(v).split(" / ")[0]) if isinstance(v, str) else v),
        "Scor risc": pd.to_numeric(df_display["Scor risc"], errors="coerce"),
        "Scor div.": pd.to_numeric(df_display["Scor div."], errors="coerce"),
        "Conturi": df_display["accounts"],
    })
    if privacy.hidden():
        table_df = table_df.drop(columns=["Cant.", f"Cost achiz. ({_c})", f"Val. curentă ({_c})", f"P/L ({_c})", f"Div. ({_c})"])
    if compact:
        table_df = table_df[[c for c in ("Logo", "Nume", f"Val. curentă ({_c})", f"P/L ({_c})", "Randament %") if c in table_df.columns]]

    def colorize(value):
        if value is None or pd.isna(value):
            return ""
        if value > 0:
            return "color: #00d084;"
        if value < 0:
            return "color: #ff6b6b;"
        return "color: #9aa0a6;"

    formats = {
        "Cant.": "{:.4f}",
        "Preț mediu": "{:.2f}",
        "Preț curent": "{:.2f}",
        f"Cost achiz. ({_c})": "{:,.2f}",
        f"Val. curentă ({_c})": "{:,.2f}",
        f"P/L ({_c})": "{:+,.2f}",
        "Randament %": "{:+.2f}%",
        f"Div. ({_c})": "{:,.2f}",
        "Div/Inv %": "{:.2f}%",
        "Rand. total %": "{:+.2f}%",
        "S&P500 %": "{:+.2f}%",
        "PEG": "{:.2f}",
        "vs S&P500 pp": "{:+.2f}",
        "Scor TL": "{:.1f}",
        "Scor risc": "{:.1f}",
        "Scor div.": "{:.1f}",
        "Țintă %": "{:+.1f}%",
    }
    colored = {f"P/L ({_c})", "Randament %", "Rand. total %", "vs S&P500 pp", "Țintă %"}

    _t212_rows = {r["ticker"]: r for r in df.to_dict("records")}
    _detail_rows = []
    _xtb_kinds = {i["ticker"]: ("ETF" if i.get("category") in ("ETF", "ETC") else "STOCK") for i in _xtb_instruments()}
    for _r in df_display.to_dict("records"):
        _tk = _r["ticker"]
        if _tk in _t212_rows:
            _detail_rows.append(_t212_rows[_tk])
        else:
            _detail_rows.append({"ticker": _tk, "name": _r["name"], "currencyCode": '', "currentPrice": _r.get("currentPrice") or 0.0, "isin": _r.get("isin"), "type": _xtb_kinds.get(_tk), "watchlist": True})
    st.session_state["_table_rows"] = _detail_rows
    st.session_state["_table_total"] = total_portfolio_value
    import html_table
    cols = []
    for c in table_df.columns:
        if c == "Logo":
            cols.append({"key": c, "label": "", "width": "30px"})
            continue
        cols.append({"key": c, "label": col(c), "nowrap": c != "Nume",
                     "align": "right" if c in formats or c == "Zile" else None,
                     "help": _COL_HELP_I18N[c]() if c in _COL_HELP_I18N else COLUMN_HELP.get(c)})
    out = []
    for tk, raw in zip(df_display["ticker"], table_df.to_dict("records")):
        row = {}
        for c, v in raw.items():
            if c == "Logo":
                row[c] = {"img": v, "img_title": tk}
            elif c == "Nume":
                row[c] = {"text": v or tk, "title": tk, "tip": tk, "href": html_table.detail_href(tk)}
            else:
                num = pd.to_numeric(v, errors="coerce") if not isinstance(v, str) else None
                if num is None or pd.isna(num):
                    row[c] = "n/a" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
                else:
                    text = formats[c].format(num) if c in formats else str(v)
                    row[c] = {"text": text, "sort": float(num), "style": colorize(num) if c in colored else ""}
        out.append(row)
    html_table.render(cols, out, tid="positions", max_height=720)
