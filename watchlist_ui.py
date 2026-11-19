"""Tabul Watchlist de pe pagina principala: adaugare, tabel cu scoruri, stergere si actualizare."""
from datetime import datetime

import pandas as pd
import streamlit as st

from descriptions import COLUMN_HELP
from i18n import col, t, x as _tx
from watchlist import add_to_watchlist, load_watchlist, load_watchlist_cache, remove_from_watchlist, start_watchlist_refresh_background


def watch_row(symbol):
    for item in load_watchlist():
        if isinstance(item, dict) and item.get("symbol") == symbol:
            entry = load_watchlist_cache().get(symbol, {})
            return {
                "ticker": symbol,
                "name": entry.get("name") or symbol,
                "currencyCode": entry.get("currency") or "",
                "currentPrice": entry.get("price") or 0.0,
                "isin": item.get("isin"),
                "watchlist": True,
            }
    return None


def render_watchlist_tab(vdf=None):
    from value_quality_ui import render_value_quality, watchlist_results, status_label, tr, retain_controls
    retain_controls()
    labels = {'list': tr('Listă', 'List'), 'value_quality': 'Value + Quality'}
    view = st.segmented_control('Watchlist', list(labels), default='list',
                                format_func=labels.get, key='wl_view')
    if view == 'value_quality':
        render_value_quality(vdf)
        return
    wl_symbol_col, wl_isin_col, wl_add_col = st.columns([3, 3, 1])
    with wl_symbol_col:
        st.text_input(t("wl.symbol"), key="wl_symbol")
    with wl_isin_col:
        st.text_input(t("wl.isin"), key="wl_isin")
    with wl_add_col:
        st.write("")
        if st.button(t("wl.add"), key="wl_add"):
            with st.spinner(_tx("Calculez indicatorii...")):
                ok, msg = add_to_watchlist(st.session_state["wl_symbol"], st.session_state.get("wl_isin"))
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    watchlist_items = load_watchlist()
    watchlist_cache = load_watchlist_cache()
    watchlist_items_by_symbol = {
        item.get("symbol"): item
        for item in watchlist_items
        if isinstance(item, dict) and item.get("symbol")
    }
    watchlist_symbols = list(watchlist_items_by_symbol.keys())

    if watchlist_symbols:
        quality = watchlist_results()
        from yahoo import resolve_yahoo_symbol
        def format_watch_score(entry, total_key, coverage_key):
            coverage = entry.get(coverage_key)
            total = entry.get(total_key)
            if coverage is None or coverage < 50 or total is None:
                return "n/a"
            return f"{total:.1f}"

        watchlist_rows = []
        for symbol in watchlist_symbols:
            item = watchlist_items_by_symbol.get(symbol, {})
            entry = watchlist_cache.get(symbol, {})
            updated = entry.get("updated") or ""
            price_at = max(filter(None, (entry.get("updated"), entry.get("price_updated"))), default="")
            watchlist_rows.append({
                "Simbol": symbol,
                "ISIN": item.get("isin") or "—",
                "Nume": entry.get("name") or "n/a",
                "Preț": entry.get("price") if entry.get("price") is not None else "n/a",
                "Monedă": entry.get("currency") or "n/a",
                "Scor TL": format_watch_score(entry, "quality_total", "quality_coverage"),
                "Rating TL": "ETF: adaugă ISIN" if entry.get("kind") == "etf_no_isin" else entry.get("quality_rating") or "n/a",
                "Scor risc": format_watch_score(entry, "risk_total", "risk_coverage"),
                "Rating risc": entry.get("risk_rating") or "n/a",
                "Actualizat": updated[:10] if updated else "n/a",
                "Preț la": price_at[11:16] if price_at[:10] == datetime.now().strftime("%Y-%m-%d") else (price_at[:10] or "n/a"),
            })

        if quality:
            for row in watchlist_rows:
                symbol = resolve_yahoo_symbol(row['Simbol']).strip().upper()
                result = quality.get(symbol)
                row['Value + Quality'] = status_label(result['status']) if result else tr('Neanalizat', 'Not analyzed')
            st.caption(tr('Coloana Value + Quality folosește ultima analiză și pragurile alese în vizualizarea Value + Quality.',
                          'The Value + Quality column uses the last analysis and thresholds selected in the Value + Quality view.'))
        watchlist_df = pd.DataFrame(watchlist_rows)
        _wl_help = {col(nume): text for nume, text in COLUMN_HELP.items() if nume in watchlist_df.columns}
        _wl_help.update({col("Actualizat"): t("wl.help_updated"), col("Preț la"): t("wl.help_price_at")})
        watchlist_df = watchlist_df.rename(columns=col)

        st.session_state["_watch_rows"] = [
            {
                "ticker": r["Simbol"],
                "isin": watchlist_items_by_symbol.get(r["Simbol"], {}).get("isin") or None,
                "name": watchlist_cache.get(r["Simbol"], {}).get("name") or r["Simbol"],
                "currencyCode": watchlist_cache.get(r["Simbol"], {}).get("currency") or "",
                "currentPrice": watchlist_cache.get(r["Simbol"], {}).get("price") or 0.0,
                "watchlist": True,
            }
            for r in watchlist_rows
        ]
        import html_table
        import logos
        logos.prefetch([(r["Simbol"], r["Nume"] if r["Nume"] != "n/a" else "") for r in watchlist_rows])
        sym_col, name_col = col("Simbol"), col("Nume")
        cols = [{"key": "_logo", "label": "", "width": "30px"},
                {"key": name_col, "label": name_col, "help": _wl_help.get(name_col)}]
        cols += [{"key": c, "label": c, "help": _wl_help.get(c), "nowrap": True}
                 for c in watchlist_df.columns if c not in (sym_col, name_col)]
        out = []
        for raw, row in zip(watchlist_rows, watchlist_df.to_dict("records")):
            sym = raw["Simbol"]
            name = raw["Nume"] if raw["Nume"] != "n/a" else sym
            cells = {c: ({"text": "{:,.2f}".format(v), "sort": v} if isinstance(v, float) else v) for c, v in row.items()}
            cells["_logo"] = {"img": logos.logo_uri(sym, name), "img_title": sym}
            cells[name_col] = {"text": name, "title": sym, "href": html_table.detail_href(sym)}
            out.append(cells)
        html_table.render(cols, out, tid="watchlist")
        st.caption(t("wl.table_hint"))

        wl_remove_col, wl_delete_col, wl_refresh_col = st.columns([3, 1, 1])
        with wl_remove_col:
            selected_watch_symbol = st.selectbox(t("wl.remove_label"), watchlist_symbols, key="wl_remove")
        with wl_delete_col:
            st.write("")
            if st.button(t("wl.remove"), key="wl_del"):
                remove_from_watchlist(selected_watch_symbol)
                st.rerun()
        with wl_refresh_col:
            st.write("")
            if st.button(t("wl.refresh"), key="wl_refresh"):
                start_watchlist_refresh_background(force=True)
                st.info(t("wl.started"))
    else:
        st.caption(t("wl.empty"))
