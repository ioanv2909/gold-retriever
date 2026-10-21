import streamlit as st
import alerts
import requests
import pandas as pd
import numpy as np
import base64
import hashlib
import io
import os
import json
import re
import time
import threading
import tempfile
from datetime import datetime
from urllib.parse import quote
import plotly.graph_objects as go
import plotly.express as px

from core import CONFIG_FILE, RECOMMENDATION_LABELS, check_loss_to_profit_alerts, days_held_from_iso, dismiss_alert, load_config, record_portfolio_point, save_config, load_portfolio_history
from t212_api import fetch_account_currency, fetch_and_cache_core, fetch_fx_rate, load_cached_dividends, load_cached_ratings, load_cached_snapshot
from yahoo import fetch_benchmark_return, fetch_yahoo_peg_ratio, resolve_yahoo_symbol
from background import load_dividends_status, load_market_context_cache, load_quality_cache, load_ratings_status, start_background_scheduler, start_dividends_fetch_background, start_quality_fetch_background, start_ratings_fetch_background
from descriptions import COLUMN_HELP
from detail_view import render_detail_view, scroll_page_to_top
from watchlist import add_to_watchlist, load_watchlist, load_watchlist_cache, remove_from_watchlist, start_watchlist_refresh_background
from xtb import accounts_summary, import_xtb, instruments as xtb_instruments, parse_xtb_file, remove_account, save_isin
from xtb_prices import load_xtb_prices, save_symbol_override, start_xtb_prices_refresh_background
from isin_tools import isin_issues, resolve_isin, suggest_isin
from i18n import LANGS, col, install_translation, t, x as _tx

install_translation()

# Păstrează limba aleasă când selectorul nu e randat (ex. pe pagina de detaliu):
# Streamlit șterge starea unui widget nerandat, deci o reatribuim la fiecare rulare.
import json as _json
import os as _os
_PREF_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "ui_prefs.json")


def _pref_file():
    try:
        from userctx import current_user, user_dir
        if current_user():
            return _os.path.join(user_dir(), "ui_prefs.json")
    except Exception:
        pass
    return _PREF_PATH


def _read_prefs():
    for _pth in (_pref_file(), _PREF_PATH):
        try:
            with open(_pth, encoding="utf-8") as _f:
                _d = _json.load(_f)
            if _d.get("lang") or _pth == _PREF_PATH:
                return _d
        except Exception:
            pass
    return {}


if not st.session_state.get("lang") and not st.session_state.get("_lang"):
    _saved_lang = _read_prefs().get("lang")
    if _saved_lang in LANGS:
        st.session_state["lang"] = _saved_lang

if st.session_state.get("lang"):
    st.session_state["_lang"] = st.session_state["lang"]
elif st.session_state.get("_lang"):
    st.session_state["lang"] = st.session_state["_lang"]
if not st.session_state.get("lang"):
    st.session_state["lang"] = "RO"

_cur_lang = st.session_state.get("lang")
if _cur_lang in LANGS:
    _p = _read_prefs()
    if _p.get("lang") != _cur_lang:
        _p["lang"] = _cur_lang
        try:
            _pf = _pref_file()
            _os.makedirs(_os.path.dirname(_pf), exist_ok=True)
            with open(_pf, "w", encoding="utf-8") as _f:
                _json.dump(_p, _f)
        except Exception:
            pass


try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

st.set_page_config(page_title="GoldRetriever", layout="wide", page_icon="assets/icon-192.png" if __import__("os").path.exists("assets/icon-192.png") else "🐕")

os.makedirs("data", exist_ok=True)

import users as _users
from auth import require_login
for _u in _users.names():
    start_background_scheduler(_u)
_me = require_login()
for _u in _users.names():
    start_background_scheduler(_u)
if st.session_state.get("_lang_user") != _me:
    st.session_state["_lang_user"] = _me
    _pl = _read_prefs().get("lang")
    if _pl in LANGS:
        st.session_state["lang"] = _pl
        st.session_state["_lang"] = _pl
if st.session_state.get("_page_users"):
    from auth import render_users_page as _render_users_page
    _render_users_page(_me)
    st.stop()


config_data = load_config()
api_key_id = config_data.get("api_key_id", "")
api_secret = config_data.get("api_secret", "")
interval_minutes = int(config_data.get("interval_minutes", 15))


# ---------------------------------------------------------------------------
# UI principal
# ---------------------------------------------------------------------------
@st.fragment(run_every=5)
def _watch_background_jobs():
    busy = load_dividends_status().get("in_progress") or load_ratings_status().get("in_progress")
    if not busy:
        st.rerun()


from portfolio_model import portfolio_options, default_currency, build_rows
from history_multi import multi_history_records
from xtb import instruments as _xtb_instruments


from portfolio_model import fx as _fx
from xtb import load_xtb as _load_xtb


def _div_score(entry):
    entry = entry or {}
    if entry.get("div_total") is None or (entry.get("div_coverage") or 0) < 50:
        return None
    return round(entry["div_total"], 1)


def _xtb_cash_lines(labels, display_ccy):
    d = _load_xtb()
    lines, total = [], 0.0
    for k, a in sorted(d["accounts"].items(), key=lambda kv: kv[1]["currency"]):
        if a["label"] not in labels:
            continue
        amt = sum(o["amount"] for o in d["cash_ops"].get(k, {}).values())
        total += amt * _fx(a["currency"], display_ccy)
        lines.append(f"{a['label']}: {amt:,.2f} {a['currency']}")
    return lines, total


def _xtb_cash_items(labels, display_ccy):
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


def _render_cash(sel_portfolios, display_ccy, cash, compact=False):
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
        rows.append((t("main.cash_t212"), f"{free:,.2f} {t212_ccy}",
                     "" if t212_ccy == display_ccy else f"≈ {conv:,.2f} {display_ccy}"))
    items, xtot = _xtb_cash_items(sel_portfolios, display_ccy)
    for it in items:
        rows.append((t("main.cash_acct", label=it["label"]), f"{it['amount']:,.2f} {it['ccy']}",
                     "" if it["ccy"] == display_ccy else f"≈ {it['disp']:,.2f} {display_ccy}"))
    tot += xtot
    if not rows:
        return
    label = f"💵 {t('main.cash_total')} · {tot:,.2f} {display_ccy}"
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
            if sub:
                st.caption(sub)


from background import xtb_tickers as _xtb_tickers


def _xtb_detail_row(ticker):
    for i in _xtb_instruments():
        if i.get("ticker") == ticker:
            return {"ticker": ticker, "name": i.get("name") or ticker, "currencyCode": '', "currentPrice": 0.0, "isin": i.get("isin"), "type": "ETF" if i.get("category") in ("ETF", "ETC") else "STOCK", "watchlist": True}
    return None


def _watch_row(symbol):
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


def _history_dialog(fig):
    st.dialog(_tx("Valoare de piață în timp"), width="large")(_history_dialog_inner)(fig)


def _history_dialog_inner(fig):
    big = go.Figure(fig)
    big.update_layout(height=560)
    st.plotly_chart(big, width="stretch", key="portfolio_history_chart_big")


def _section_updates():
    """Settings > Updates: refresh buttons (moved out of the sidebar)."""
    if api_key_id and api_secret:
        st.caption(t("side.auto_on", n=interval_minutes))
    else:
        st.caption(t("side.auto_off"))
    div_status = load_dividends_status()
    rat_status = load_ratings_status()
    if st.button(t("btn.refresh_now"), key="upd_now"):
        disk_cfg = load_config()
        fetch_and_cache_core(disk_cfg.get("api_key_id"), disk_cfg.get("api_secret"))
        st.rerun()
    if div_status.get("in_progress"):
        st.button(t("btn.refresh_div_busy"), disabled=True, key="div_btn_busy")
    elif st.button(t("btn.refresh_div"), key="upd_div"):
        disk_cfg = load_config()
        snap_now = load_cached_snapshot()
        tickers_now = [x.get("ticker") for x in (snap_now.get("positions") or [])] if snap_now else []
        if start_dividends_fetch_background(disk_cfg.get("api_key_id"), disk_cfg.get("api_secret"), tickers_now):
            st.rerun()
    if rat_status.get("in_progress"):
        st.button(t("btn.refresh_rat_busy"), disabled=True, key="rat_btn_busy")
    elif st.button(t("btn.refresh_rat"), key="upd_rat"):
        snap_now = load_cached_snapshot()
        tickers_now = [x.get("ticker") for x in (snap_now.get("positions") or [])] if snap_now else []
        _all_now = list(tickers_now) + [x for x in _xtb_tickers() if x not in tickers_now]
        start_quality_fetch_background(_all_now)
        if start_ratings_fetch_background(_all_now):
            st.rerun()


def _section_xtb_import():
    """Settings > XTB import (moved out of the sidebar)."""
    uploaded_xtb_files = st.file_uploader(
        _tx("Fișiere XTB (.xlsx, câte unul pentru fiecare cont)"),
        type=["xlsx"],
        accept_multiple_files=True,
        key=f"xtb_upload_{st.session_state.get('xtb_nonce', 0)}",
    )

    if st.button(t("xtb.import"), key="xtb_import_btn"):
        reports = []
        errors = []

        for uploaded_file in uploaded_xtb_files or []:
            safe_name = re.sub(r"\d{6,}", "#####", uploaded_file.name)
            try:
                raw = uploaded_file.getvalue()
                file_hash = hashlib.sha256(raw).hexdigest()
                parsed = parse_xtb_file(io.BytesIO(raw))
                reports.append(import_xtb(parsed, file_hash))
            except ValueError as exc:
                errors.append(f"{safe_name}: {exc}")
            except Exception as exc:
                errors.append(f"{safe_name}: {exc}")

        try:
            alerts.record_xtb_import(reports, errors, _me)
        except Exception:
            pass
        st.session_state["xtb_last_report"] = reports
        st.session_state["xtb_last_errors"] = errors
        st.session_state["xtb_nonce"] = st.session_state.get("xtb_nonce", 0) + 1
        st.rerun()

    for error in st.session_state.get("xtb_last_errors", []):
        st.error(error)

    xtb_last_report = st.session_state.get("xtb_last_report")
    if xtb_last_report:
        report_rows = []
        for report in xtb_last_report:
            verification_issues = []
            if not report.get("cash_ok"):
                verification_issues.append("✗ cash")
            if not report.get("positions_ok"):
                verification_issues.append("✗ poziții")

            report_rows.append(
                {
                    "Cont": report.get("label"),
                    "Raport din": report.get("report_time"),
                    "Operațiuni noi": report.get("new_cash_ops", 0) + report.get("new_closed", 0),
                    "Duplicate sărite": report.get("duplicate_cash_ops", 0) + report.get("duplicate_closed", 0),
                    "Snapshot": "fișier deja încărcat" if report.get("already_imported") else report.get("snapshot_status"),
                    "Verificări": "✓" if not verification_issues else " / ".join(verification_issues),
                    "Tipuri necunoscute": ", ".join(report.get("unknown_types") or []) or "—",
                }
            )

        st.dataframe(pd.DataFrame(report_rows), width="stretch", hide_index=True)
        if st.button(t("xtb.hide_report"), key="xtb_hide_report"):
            st.session_state.pop("xtb_last_report", None)
            st.session_state.pop("xtb_last_errors", None)
            st.rerun()

    xtb_accounts = accounts_summary()
    if xtb_accounts:
        st.dataframe(
            pd.DataFrame(
                {
                    "Cont": [account.get("label") for account in xtb_accounts],
                    "Monedă": [account.get("currency") for account in xtb_accounts],
                    "Raport din": [account.get("report_time") for account in xtb_accounts],
                    "Poziții": [account.get("positions") for account in xtb_accounts],
                    "Operațiuni": [account.get("cash_ops") for account in xtb_accounts],
                    "Valoare la raport": [account.get("value") for account in xtb_accounts],
                    "Profit la raport": [account.get("profit") for account in xtb_accounts],
                }
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption(t("xtb.no_data"))

    st.markdown(t("xtb.symbols_title"))
    xtb_prices_cache = load_xtb_prices()
    xtb_prices_data = xtb_prices_cache.get("data") or {}
    xtb_symbol_rows = []
    xtb_symbol_originals = {}

    for ticker, price_info in xtb_prices_data.items():
        symbol = price_info.get("symbol") or ""
        status = price_info.get("status")
        currency_ok = price_info.get("currency_ok")
        ratio = price_info.get("ratio")

        if status == "ok" and currency_ok in (True, None):
            status_label = "✅ ok"
            has_problem = False
        elif status == "mismatch" or currency_ok is False:
            status_label = "⚠️ verifică"
            has_problem = True
        else:
            status_label = "❌ fără date"
            has_problem = True

        xtb_symbol_originals[str(ticker)] = symbol
        xtb_symbol_rows.append(
            {
                "_problem": has_problem,
                "Ticker": str(ticker),
                "Simbol Yahoo": symbol,
                "Preț Yahoo": price_info.get("price"),
                "Monedă": price_info.get("currency") or "",
                "Preț XTB": price_info.get("xtb_ref"),
                "Raport": round(ratio, 3) if ratio is not None else None,
                "Stare": status_label,
            }
        )

    xtb_symbols_df = pd.DataFrame(
        xtb_symbol_rows,
        columns=["_problem", "Ticker", "Simbol Yahoo", "Preț Yahoo", "Monedă", "Preț XTB", "Raport", "Stare"],
    )
    if not xtb_symbols_df.empty:
        xtb_symbols_df = xtb_symbols_df.sort_values(["_problem", "Ticker"], ascending=[False, True]).reset_index(drop=True)
    xtb_symbols_editor_df = xtb_symbols_df.drop(columns=["_problem"], errors="ignore")

    edited_xtb_symbols_df = st.data_editor(
        xtb_symbols_editor_df,
        width="stretch",
        hide_index=True,
        key="xtb_symbols_editor",
        disabled=["Ticker", "Preț Yahoo", "Monedă", "Preț XTB", "Raport", "Stare"],
        column_config={
            "Simbol Yahoo": st.column_config.TextColumn("Simbol Yahoo"),
        },
    )

    xtb_symbols_save_col, xtb_prices_refresh_col = st.columns([1, 1])
    with xtb_symbols_save_col:
        if st.button(t("xtb.save_symbols"), key="xtb_symbols_save"):
            saved_any = False

            for _, row in edited_xtb_symbols_df.iterrows():
                ticker = str(row["Ticker"])
                new_symbol = "" if pd.isna(row.get("Simbol Yahoo")) else str(row.get("Simbol Yahoo") or "").strip()
                old_symbol = xtb_symbol_originals.get(ticker, "")

                if new_symbol == old_symbol:
                    continue

                ok, msg = save_symbol_override(ticker, new_symbol)
                if ok:
                    saved_any = True
                    st.success(f"{ticker}: {msg}")
                else:
                    st.error(f"{ticker}: {msg}")

            if saved_any:
                st.rerun()

    with xtb_prices_refresh_col:
        if st.button(t("xtb.refresh_prices"), key="xtb_prices_refresh"):
            if start_xtb_prices_refresh_background():
                st.info(t("xtb.prices_started"))
            else:
                st.warning(t("xtb.prices_busy"))

    fetched_at = xtb_prices_cache.get("fetched_at")
    if fetched_at:
        xtb_prices_updated = datetime.fromtimestamp(fetched_at).strftime("%d.%m.%Y %H:%M:%S")
    else:
        xtb_prices_updated = "neactualizat încă"

    xtb_prices_total = len(xtb_prices_data)
    xtb_prices_ok = sum(
        1
        for price_info in xtb_prices_data.values()
        if price_info.get("status") == "ok" and price_info.get("currency_ok") in (True, None)
    )
    st.caption(
        f"Ultima actualizare: {xtb_prices_updated} · {xtb_prices_ok}/{xtb_prices_total} tickere ok. "
        "Prețul XTB e luat din export; un raport în jur de 1,00–1,03 e normal "
        "(probabil XTB evaluează la prețul de vânzare). Sub 0,9 sau peste 1,1 indică simbol sau monedă greșite."
    )

    xtb_instrument_rows = xtb_instruments()
    if xtb_instrument_rows:
        xtb_isin_suggestions = {}
        xtb_isin_categories = {}
        xtb_isin_rows = []

        for instrument in xtb_instrument_rows:
            ticker = instrument.get("ticker")
            current_isin = str(instrument.get("isin") or "").strip().upper()
            category = instrument.get("category")
            xtb_isin_categories[str(ticker)] = category

            resolved_name = "—"
            if current_isin:
                resolved = resolve_isin(current_isin)
                resolved_name = resolved.get("name") or "—"

            suggestion = None if current_isin else suggest_isin(ticker, category)
            xtb_isin_suggestions[str(ticker)] = suggestion
            suggestion_text = (
                f"{suggestion.get('isin')} — {suggestion.get('name')} [{suggestion.get('source')}]"
                if suggestion
                else "—"
            )

            xtb_isin_rows.append(
                {
                    "Ticker": ticker,
                    "Nume": instrument.get("name"),
                    "Categorie": category,
                    "Conturi": ", ".join(instrument.get("accounts") or []),
                    "ISIN": current_isin,
                    "Rezolvat": resolved_name,
                    "Sugestie": suggestion_text,
                    "Aplică sugestia": False,
                }
            )

        xtb_isin_df = pd.DataFrame(xtb_isin_rows)
        edited_xtb_isin_df = st.data_editor(
            xtb_isin_df,
            width="stretch",
            hide_index=True,
            key="xtb_isin_editor",
            disabled=["Ticker", "Nume", "Categorie", "Conturi", "Rezolvat", "Sugestie"],
            column_config={
                "ISIN": st.column_config.TextColumn("ISIN"),
                "Aplică sugestia": st.column_config.CheckboxColumn("Aplică sugestia"),
            },
        )

        if st.button(t("xtb.save_isin"), key="xtb_isin_save"):
            original_isins = {
                str(row["Ticker"]): str(row.get("ISIN") or "").strip().upper()
                for _, row in xtb_isin_df.iterrows()
            }
            changed_isins = {}

            for _, row in edited_xtb_isin_df.iterrows():
                ticker = str(row["Ticker"])
                new_isin = "" if pd.isna(row.get("ISIN")) else str(row.get("ISIN") or "").strip().upper()
                suggestion = xtb_isin_suggestions.get(ticker)
                apply_suggestion = bool(row.get("Aplică sugestia"))

                if apply_suggestion and not new_isin and suggestion:
                    new_isin = str(suggestion.get("isin") or "").strip().upper()

                if new_isin != original_isins.get(ticker, ""):
                    changed_isins[ticker] = new_isin

            if not changed_isins:
                st.info(t("xtb.no_isin_changes"))
            else:
                saved_count = 0
                post_save_messages = []

                for ticker, new_isin in changed_isins.items():
                    issues = isin_issues(ticker, new_isin, xtb_isin_categories.get(ticker), changed_isins) if new_isin else []
                    error_issues = [message for level, message in issues if level == "error"]

                    if error_issues:
                        for message in error_issues:
                            st.error(f"{ticker}: {message}")
                        continue

                    ok, msg = save_isin(ticker, new_isin)
                    if not ok:
                        st.error(f"{ticker}: {msg}")
                        continue

                    saved_count += 1
                    post_save_messages.extend(
                        (ticker, level, message)
                        for level, message in issues
                        if level in {"warning", "info"}
                    )

                for ticker, level, message in post_save_messages:
                    if level == "warning":
                        st.warning(f"{ticker}: {message}")
                    else:
                        st.info(f"{ticker}: {message}")

                if saved_count:
                    st.success(t("xtb.isin_saved", n=saved_count))

        if st.button(t("xtb.check_isin"), key="xtb_isin_check"):
            issue_rows = []

            for _, row in xtb_isin_df.iterrows():
                ticker = str(row["Ticker"])
                isin = str(row.get("ISIN") or "").strip().upper()
                if not isin:
                    continue

                for level, message in isin_issues(ticker, isin, row.get("Categorie")):
                    issue_rows.append(
                        {
                            "Ticker": ticker,
                            "ISIN": isin,
                            "Nivel": level,
                            "Mesaj": message,
                        }
                    )

            if issue_rows:
                st.dataframe(pd.DataFrame(issue_rows), width="stretch", hide_index=True)
            else:
                st.success(t("xtb.no_issues"))

    st.checkbox(t("xtb.allow_delete"), key="xtb_del_unlock")
    if st.session_state.get("xtb_del_unlock") and xtb_accounts:
        selected_xtb_account = st.selectbox(
            "Cont XTB de șters",
            xtb_accounts,
            format_func=lambda account: account.get("label") or account.get("account_key"),
            key="xtb_del_account",
        )
        if st.button(t("xtb.delete_account"), key="xtb_delete_account"):
            remove_account(selected_xtb_account["account_key"])
            st.rerun()

    st.caption(
        "XTB nu are API: datele sunt un instantaneu din ultimul export. "
        "Cumpărările și vânzările noi apar doar după un export nou; "
        "reîncărcarea aceluiași export este sigură, duplicatele sunt ignorate."
    )


def render_main_view():
    _cash_done = False
    detail_loading = bool(st.query_params.get("detail"))
    if st.session_state.pop("scroll_to_top_main", False):
        scroll_page_to_top()
    try:
        import userctx as _uc
        _uname = _uc.current_user() or ""
    except Exception:
        _uname = ""
    if _uname == "demo":
        _ro = str(st.session_state.get("lang", "")).upper().startswith("RO")
        st.info(
            "Cont demo: toate datele sunt fictive (tickere și prețuri reale, achiziții inventate). Nu reprezintă sfaturi financiare."
            if _ro else
            "Demo account: all data is fictional (real tickers and prices, invented purchases). This is not financial advice.",
            icon="🧪",
        )
    from auth import user_menu as _user_menu
    _c_logo, _c_title, _c_lang, _c_user = st.columns([1, 13, 3, 3], vertical_alignment="center")
    with _c_logo:
        if os.path.exists("assets/icon-192.png"):
            import base64 as _b64
            with open("assets/icon-192.png", "rb") as _f:
                st.markdown(
                    '<img src="data:image/png;base64,%s" width="64">' % _b64.b64encode(_f.read()).decode(),
                    unsafe_allow_html=True,
                )
    with _c_title:
        st.title(t("app.title"))
    with _c_lang:
        st.segmented_control("Language", LANGS, key="lang", label_visibility="collapsed")
    with _c_user:
        _user_menu(_me)

    snapshot = load_cached_snapshot()
    if snapshot and snapshot.get("positions"):
        instruments_by_ticker = {}
        if snapshot.get("instruments"):
            instruments_by_ticker = {i.get("ticker"): i.get("name", i.get("ticker")) for i in snapshot["instruments"]}
        active_alerts = [a for a in check_loss_to_profit_alerts(snapshot["positions"], instruments_by_ticker) if not a.get("dismissed")]
        for a in active_alerts:
            st.warning(t("alert.loss_to_profit", name=a["name"], ticker=a["ticker"], days=a["zile_detinut"], pct=f"{a['randament_%']:.2f}"))
            ac1, ac2 = st.columns([1, 6])
            with ac1:
                if st.button(t("alert.seen"), key=f"dismiss_{a['ticker']}_{a['triggered_at']}"):
                    dismiss_alert(a["ticker"], a["triggered_at"])
                    st.rerun()

    if not detail_loading:
        st.subheader(t("app.summary"))


    div_status = load_dividends_status()
    rat_status = load_ratings_status()
    snapshot = load_cached_snapshot()  # re-citit după eventualele butoane de update de mai sus

    if snapshot:
        ts = datetime.fromtimestamp(snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
        st.caption(t("main.updated_at", ts=ts))

    if not snapshot:
        st.info(t("main.no_cache"))
        return

    errs = snapshot.get("errors", {})
    if errs.get("cash"):
        st.error(errs["cash"])
        return
    elif errs.get("portfolio"):
        st.error(errs["portfolio"])
        return

    cash = snapshot["cash"]
    invested = cash.get("invested", 0.0)
    ppl = cash.get("ppl", 0.0)
    market_value = invested + ppl
    record_portfolio_point(market_value, invested, ppl)
    yield_pct = (ppl / invested * 100.0) if invested else 0.0

    positions = snapshot.get("positions") or []
    if not positions:
        st.info(t("main.no_positions"))
        return

    df = pd.DataFrame(positions)

    instruments = snapshot.get("instruments")
    if errs.get("instruments") or not instruments:
        df["name"] = df["ticker"]
        df["currencyCode"] = ""
    else:
        meta = pd.DataFrame(instruments)[["ticker", "name", "currencyCode"]]
        df = df.merge(meta, on="ticker", how="left")
        df["name"] = df["name"].fillna(df["ticker"])
        df["currencyCode"] = df["currencyCode"].fillna("")

    # GBX (penny sterling, LSE) nu e o monedă reală — o transformăm în GBP peste tot (1 GBP = 100 GBX)
    # înainte de orice alt calcul, ca prețurile/costurile afișate să fie mereu într-o monedă reală.
    gbx_mask = df["currencyCode"] == "GBX"
    df.loc[gbx_mask, "averagePrice"] = df.loc[gbx_mask, "averagePrice"] / 100
    df.loc[gbx_mask, "currentPrice"] = df.loc[gbx_mask, "currentPrice"] / 100
    df.loc[gbx_mask, "currencyCode"] = "GBP"

    df["valoare_curenta"] = df["quantity"] * df["currentPrice"]
    df["cost_achizitie"] = df["quantity"] * df["averagePrice"]

    # Randament = (Preț curent / Preț mediu − 1) × 100 — pur din preț, în moneda instrumentului,
    # fără nicio conversie valutară (nu depinde de moneda contului).
    df["randament_%"] = ((df["currentPrice"] / df["averagePrice"] - 1) * 100).round(2)

    account_currency, acc_curr_err = fetch_account_currency(api_key_id, api_secret)
    account_currency = account_currency or "?"

    # Pentru "Dividende / bani investiți" tot avem nevoie de costul de achiziție convertit în
    # moneda contului, pentru că dividendele vin în moneda contului, nu în cea a instrumentului.
    fx_errors = []
    unique_ccys = [c for c in df["currencyCode"].unique() if c]
    fx_rates = {}
    for ccy in unique_ccys:
        rate, fx_err = fetch_fx_rate(ccy, account_currency)
        fx_rates[ccy] = rate
        if fx_err:
            fx_errors.append(fx_err)
    df["fx_rate"] = df["currencyCode"].map(fx_rates).fillna(1.0)
    total_portfolio_value = (df["valoare_curenta"] * df["fx_rate"]).sum()
    df["cost_achizitie_cont"] = df["cost_achizitie"] * df["fx_rate"]

    div_snapshot = load_cached_dividends()
    dividends = (div_snapshot or {}).get("dividends", {})
    df["dividende_incasate"] = df["ticker"].map(lambda t: dividends.get(t, {}).get("total", 0.0))
    df["div_pe_investit_%"] = (df["dividende_incasate"] / df["cost_achizitie_cont"] * 100).round(2)
    df["randament_total_%"] = (df["randament_%"] + df["div_pe_investit_%"]).round(2)
    total_dividende = df["dividende_incasate"].sum()

    rat_snapshot = load_cached_ratings()
    ratings = (rat_snapshot or {}).get("ratings", {})
    df["recomandare"] = df["ticker"].map(lambda t: ratings.get(t, "none"))

    quality_snapshot = load_quality_cache()
    quality_data = quality_snapshot or {}
    df["Scor"] = df["ticker"].map(lambda t: round(quality_data.get(t, {}).get("total"), 1) if quality_data.get(t, {}).get("total") is not None else None)
    df["Rating"] = df["ticker"].map(lambda t: quality_data.get(t, {}).get("rating"))
    df["Scor risc"] = df["ticker"].map(lambda t: round(quality_data.get(t, {}).get("risk_total"), 1) if quality_data.get(t, {}).get("risk_total") is not None else None)
    df["Scor div."] = df["ticker"].map(lambda t: _div_score(quality_data.get(t)))

    _ui = st.session_state.setdefault("_ui_prefs", {})
    _opts = portfolio_options()
    _ccy_opts = ["EUR", "USD", "GBP", "CHF", "RON", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK",
                 "ISK", "BGN", "TRY", "UAH", "RSD", "CAD", "AUD", "NZD", "JPY", "CNY", "HKD", "SGD",
                 "KRW", "INR", "ILS", "ZAR", "BRL", "MXN"]
    for _c in [account_currency] + [a["currency"] for a in accounts_summary()]:
        if _c and _c != "?" and _c not in _ccy_opts:
            _ccy_opts.insert(0, _c)
    if detail_loading:
        sel_portfolios = [x for x in _ui.get("portfolios", _opts) if x in _opts] or list(_opts)
        display_ccy = _ui.get("ccy") or account_currency
    else:
        _cur = [x for x in st.session_state.get("portfolio_sel", _ui.get("portfolios", _opts)) if x in _opts]
        st.session_state["portfolio_sel"] = _cur or list(_opts)
        _col_p, _col_c = st.columns([3, 2])
        with _col_p:
            if len(_opts) > 1:
                _picked = st.pills(t("main.portfolios"), _opts, selection_mode="multi", key="portfolio_sel")
            else:
                _picked = list(_opts)
        sel_portfolios = list(_picked or []) or list(_opts)
        _dflt_ccy = default_currency(sel_portfolios, account_currency)
        if _dflt_ccy not in _ccy_opts:
            _dflt_ccy = "EUR"
        _sel_key = tuple(sorted(sel_portfolios))
        if st.session_state.get("_last_portfolio_sel") != _sel_key:
            st.session_state["_last_portfolio_sel"] = _sel_key
            st.session_state["display_ccy"] = _dflt_ccy
        elif "display_ccy" not in st.session_state:
            st.session_state["display_ccy"] = _ui.get("ccy") if _ui.get("ccy") in _ccy_opts else _dflt_ccy
        with _col_c:
            st.markdown("<style>.st-key-display_ccy{max-width:7rem;}</style>", unsafe_allow_html=True)
            _picked_ccy = st.selectbox(t("main.display_ccy"), _ccy_opts, key="display_ccy")
        display_ccy = _picked_ccy or _dflt_ccy
        _ui["portfolios"] = sel_portfolios
        _ui["ccy"] = display_ccy
    _native = set(sel_portfolios) == {"Trading 212"} and display_ccy == account_currency
    vdf = build_rows(df, display_ccy, sel_portfolios, account_currency)

    if not detail_loading:
        col1, col2, col3, col4 = st.columns(4)
        if _native:
            col1.metric("💰 Total Investit", f"{invested:,.2f}")
            col2.metric("📊 Valoare de Piață (Nerealizat)", f"{market_value:,.2f}", f"{ppl:,.2f}")
            col3.metric("📈 Randament", f"{yield_pct:.2f}%")
            col4.metric("💵 Total Dividende Încasate", f"{total_dividende:,.2f}")
        else:
            _m_inv = float(vdf["cost_disp"].sum())
            _m_val = float(vdf["value_disp"].sum())
            _m_pl = float(vdf["pl_disp"].sum())
            _m_div = float(vdf["div_disp"].sum())
            _m_yield = (_m_pl / _m_inv * 100.0) if _m_inv else 0.0
            col1.metric(f"💰 Total Investit ({display_ccy})", f"{_m_inv:,.2f}")
            col2.metric(f"📊 Valoare de Piață ({display_ccy})", f"{_m_val:,.2f}", f"{_m_pl:,.2f}")
            col3.metric("📈 Randament", f"{_m_yield:.2f}%")
            col4.metric(f"💵 Total Dividende Încasate ({display_ccy})", f"{_m_div:,.2f}")

        portfolio_history = multi_history_records(sel_portfolios, display_ccy)
        if _native and len(portfolio_history) < 2:
            portfolio_history = load_portfolio_history()
        if len(portfolio_history) < 2:
            st.caption(t("hist.accumulating"))
        else:
            history_df = pd.DataFrame(portfolio_history)
            history_df["x"] = history_df["ts"].fillna(history_df["date"]) if "ts" in history_df.columns else history_df["date"]
            history_df["x"] = pd.to_datetime(history_df["x"], format="ISO8601")
            history_df = history_df.sort_values("x")
            _thr = 40.0 * float(_fx("EUR", display_ccy) or 1.0)
            if st.session_state.get("hist_hide_small", True):
                _f = history_df[history_df["invested"] >= _thr]
                if len(_f) >= 2:
                    history_df = _f
            _first_all = history_df["x"].min()
            if st.session_state.get("history_range") not in ("3H", "1D", "1W", "1M", "1Y", "YTD", "Max"):
                _pref = st.session_state.get("_hist_range_pref")
                st.session_state["history_range"] = _pref if _pref in ("3H", "1D", "1W", "1M", "1Y", "YTD", "Max") else "YTD"
            st.checkbox(t("hist.hide_small", thr=f"{_thr:,.0f} {display_ccy}"), value=True, key="hist_hide_small")
            _hc_left, _hc_right = st.columns(2)
            with _hc_left:
                range_choice = st.radio(
                    "Perioadă", ["3H", "1D", "1W", "1M", "1Y", "YTD", "Max"],
                    horizontal=True, key="history_range", label_visibility="collapsed",
                )
            st.session_state["_hist_range_pref"] = range_choice
            _now = pd.Timestamp(datetime.now())
            _deltas = {
                "3H": pd.Timedelta(hours=3), "1D": pd.Timedelta(days=1), "1W": pd.Timedelta(weeks=1),
                "1M": pd.Timedelta(days=30), "1Y": pd.Timedelta(days=365),
            }
            if range_choice == "YTD":
                _start = pd.Timestamp(_now.year, 1, 1)
            elif range_choice == "Max":
                _start = None
            else:
                _start = _now - _deltas[range_choice]
            if _start is not None:
                _sel = history_df[history_df["x"] >= _start]
                history_df = _sel if len(_sel) >= 2 else history_df.tail(2)
            history_df = history_df.copy()
            try:
                history_df["x"] = history_df["x"].dt.tz_localize("UTC").dt.tz_convert("Europe/Bucharest").dt.tz_localize(None)
            except Exception:
                pass
            _show_inv = range_choice in ("1M", "1Y", "YTD", "Max")
            _v0 = float(history_df["market_value"].iloc[0])
            _v1 = float(history_df["market_value"].iloc[-1])
            _nowl = pd.Timestamp.now(tz="Europe/Bucharest").tz_localize(None)
            _first_local = pd.Timestamp(_first_all).tz_localize("UTC").tz_convert("Europe/Bucharest").tz_localize(None)
            if range_choice == "YTD":
                _ps = pd.Timestamp(_nowl.year, 1, 1)
            elif range_choice == "Max":
                _ps = None
            else:
                _ps = _nowl - _deltas[range_choice]
            with _hc_right:
                _pl_ser = history_df["market_value"] - history_df["invested"]
                _pl_d = float(_pl_ser.iloc[-1] - _pl_ser.iloc[0])
                _inv_avg = float(history_df["invested"].mean())
                st.metric(
                    t("hist.variation", rng=range_choice), f"{_pl_d:+,.2f} {display_ccy}",
                    f"{_pl_d / _inv_avg * 100:+.2f}%" if _inv_avg else None,
                )
                st.caption(t("hist.variation_help"))
                st.caption(t("hist.points", n=len(history_df), a=f"{history_df['x'].iloc[0]:%d.%m %H:%M}", b=f"{history_df['x'].iloc[-1]:%d.%m %H:%M}"))
                if _ps is not None and _first_local > _ps + pd.Timedelta(minutes=30):
                    st.caption(t("hist.incomplete", d=f"{_first_local:%d.%m.%Y %H:%M}"))
                _render_cash(sel_portfolios, display_ccy, cash, compact=True)
                _cash_done = True
            history_fig = go.Figure()
            history_fig.add_trace(
                go.Scatter(
                    x=history_df["x"],
                    y=history_df["market_value"],
                    name=_tx("Valoare de piață"),
                    mode="lines",
                    line=dict(color="#4da3ff", width=2.5),
                )
            )
            if _show_inv:
                history_fig.add_trace(
                    go.Scatter(
                        x=history_df["x"],
                        y=history_df["invested"],
                        name=_tx("Investit"),
                        mode="lines",
                        line=dict(dash="dot", color="#ff9f43", width=2.5),
                    )
                )
            history_fig.update_layout(
                title=f"{_tx('Valoare de piață în timp')} ({display_ccy})",
                height=300,
                margin=dict(l=10, r=10, t=60, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            if _show_inv:
                _lo = float(min(history_df["market_value"].min(), history_df["invested"].min()))
                _hi = float(max(history_df["market_value"].max(), history_df["invested"].max()))
                _pad = max((_hi - _lo) * 0.15, _hi * 0.01)
                history_fig.update_yaxes(range=[_lo - _pad, _hi + _pad])
            else:
                _lo = float(history_df["market_value"].min())
                _hi = float(history_df["market_value"].max())
                _pad = max((_hi - _lo) * 0.25, _hi * 0.0005)
                history_fig.update_yaxes(range=[_lo - _pad, _hi + _pad], tickformat=",.0f")
            history_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
            history_fig.update_layout(hovermode="x unified")
            history_fig.update_traces(hovertemplate="%{y:,.2f}")
            _x1 = pd.Timestamp.now(tz="Europe/Bucharest").tz_localize(None)
            if range_choice == "YTD":
                _x0 = pd.Timestamp(_x1.year, 1, 1)
            elif range_choice == "Max":
                _x0 = history_df["x"].min()
            else:
                _x0 = _x1 - _deltas[range_choice]
            _x0 = min(_x0, history_df["x"].min())
            history_fig.update_xaxes(range=[_x0, _x1])
            if len(history_df) <= 40:
                history_fig.update_traces(mode="lines+markers", marker=dict(size=5))
            with _hc_left:
                st.plotly_chart(history_fig, width="stretch", key="portfolio_history_chart")
                _enlarge = st.button(t("hist.enlarge"), key="history_enlarge")
            if _enlarge:
                _history_dialog(history_fig)

    if not _cash_done:
        _render_cash(sel_portfolios, display_ccy, cash)

    try:
        from returns_summary import render_returns_summary
        render_returns_summary("Trading 212" in sel_portfolios, any(str(x).startswith("XTB") for x in sel_portfolios))
    except Exception as _e:
        st.caption(t("ret.unavailable", e=_e))

    df = df.sort_values("name", key=lambda c: c.astype(str).str.casefold(), ascending=True).reset_index(drop=True)
    df["zile_detinut"] = df["initialFillDate"].apply(days_held_from_iso) if "initialFillDate" in df.columns else None


    account_currency_note = t("main.fx_error", e="; ".join(fx_errors)) if fx_errors else ""
    if not detail_loading:
        st.subheader(t("main.open_positions"))
    st.caption(t("main.table_note", ccy=display_ccy) + account_currency_note)
    st.caption(t("main.alpha_note"))

    mc = load_market_context_cache()
    df["sp500_return_%"] = df["ticker"].map(lambda t: mc.get(t, {}).get("sp500_return_%"))
    df["peg_ratio_display"] = df["ticker"].map(lambda t: mc.get(t, {}).get("peg"))
    df["sp500_return_%"] = pd.to_numeric(df["sp500_return_%"], errors="coerce")
    df["alpha_%"] = pd.to_numeric(df["randament_total_%"], errors="coerce") - df["sp500_return_%"]

    detail_ticker = st.query_params.get("detail")
    if detail_ticker and "selected_ticker" not in st.session_state:
        match = df[df["ticker"] == detail_ticker]
        if not match.empty:
            st.session_state["selected_ticker"] = match.iloc[0]["ticker"]
            st.session_state["selected_row"] = match.iloc[0].to_dict()
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = True
            st.rerun()
        wrow = _watch_row(detail_ticker)
        if wrow:
            st.session_state["selected_ticker"] = wrow["ticker"]
            st.session_state["selected_row"] = wrow
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = True
            st.rerun()
        xrow = _xtb_detail_row(detail_ticker)
        if xrow:
            st.session_state["selected_ticker"] = xrow["ticker"]
            st.session_state["selected_row"] = xrow
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = True
            st.rerun()
        st.query_params.clear()
        st.rerun()

    vdf = vdf.copy()
    vdf["recomandare"] = vdf["ticker"].map(lambda t: ratings.get(t, "none"))
    vdf["Scor"] = vdf["ticker"].map(lambda t: round(quality_data.get(t, {}).get("total"), 1) if quality_data.get(t, {}).get("total") is not None and (quality_data.get(t, {}).get("coverage") or 0) >= 50 else None)
    vdf["Rating"] = vdf["ticker"].map(lambda t: quality_data.get(t, {}).get("rating"))
    vdf["Scor risc"] = vdf["ticker"].map(lambda t: round(quality_data.get(t, {}).get("risk_total"), 1) if quality_data.get(t, {}).get("risk_total") is not None and (quality_data.get(t, {}).get("risk_coverage") or 0) >= 50 else None)
    vdf["Scor div."] = vdf["ticker"].map(lambda t: _div_score(quality_data.get(t)))
    vdf["sp500_return_%"] = pd.to_numeric(vdf["ticker"].map(lambda t: mc.get(t, {}).get("sp500_return_%")), errors="coerce")
    vdf["peg_ratio_display"] = vdf["ticker"].map(lambda t: mc.get(t, {}).get("peg"))
    vdf["alpha_%"] = pd.to_numeric(vdf["randament_total_%"], errors="coerce") - vdf["sp500_return_%"]
    vdf["zile_detinut"] = vdf["initialFillDate"].apply(days_held_from_iso) if "initialFillDate" in vdf.columns else None

    filter_options = ["Toate"] + list(RECOMMENDATION_LABELS.values())
    col_sort_info = st.container()
    with st.expander(t("side.filters"), expanded=False):
        filter_choice = st.selectbox(t("filter.rating"), filter_options, index=0, key="rec_filter", format_func=_tx)
    if filter_choice != "Toate":
        st.caption(t("filter.active", f=_tx(filter_choice)))
    if "positions_sort_label" not in st.session_state:
        st.session_state["positions_sort_label"] = "Val. curentă"
    if "positions_sort_desc" not in st.session_state:
        st.session_state["positions_sort_desc"] = True
    if filter_choice != "Toate":
        reverse_map = {v: k for k, v in RECOMMENDATION_LABELS.items()}
        target_key = reverse_map.get(filter_choice)
        df_display = vdf[vdf["recomandare"] == target_key].reset_index(drop=True)
    else:
        df_display = vdf

    if df_display.empty:
        st.info(t("filter.none"))
        return

    with col_sort_info:
        pass

    if div_snapshot and div_snapshot.get("error"):
        st.caption(t("div.partial_err", e=div_snapshot["error"]))

    _c = display_ccy
    table_df = pd.DataFrame({
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
        "Scor TL": pd.to_numeric(df_display["Scor"], errors="coerce"),
        "Rating": df_display["Rating"].map(lambda v: _tx(str(v).split(" / ")[0]) if isinstance(v, str) else v),
        "Scor risc": pd.to_numeric(df_display["Scor risc"], errors="coerce"),
        "Scor div.": pd.to_numeric(df_display["Scor div."], errors="coerce"),
        "Conturi": df_display["accounts"],
    })

    def colorize(value):
        if value is None or pd.isna(value):
            return ""
        if value > 0:
            return "color: #00d084;"
        if value < 0:
            return "color: #ff6b6b;"
        return "color: #9aa0a6;"

    tab_pos, tab_ev, tab_wl = st.tabs([t("tab.positions"), t("tab.events"), t("tab.watchlist")])
    with tab_pos:
        styled_table = table_df.style.format(
            {
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
            },
            na_rep="n/a",
        )
        styled_table = styled_table.map(
            colorize,
            subset=[f"P/L ({_c})", "Randament %", "Rand. total %", "vs S&P500 pp"],
        )

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
        table_event = st.dataframe(
            styled_table,
            width="stretch",
            hide_index=True,
            column_config={c: st.column_config.Column(col(c), help=t("help.div_score") if c == "Scor div." else COLUMN_HELP.get(c)) for c in table_df.columns},
            on_select="rerun",
            selection_mode="single-row",
            key=f"positions_table_{st.session_state.get('table_nonce', 0)}",
        )
        sel_rows = table_event.selection.rows if table_event and table_event.selection else []
        if sel_rows:
            _sel_row = _detail_rows[sel_rows[0]]
            st.session_state["selected_ticker"] = _sel_row["ticker"]
            st.session_state["selected_row"] = _sel_row
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = True
            st.rerun()

    with tab_ev:
        from events_ui import render_calendar_tab
        render_calendar_tab(dict(zip(df_display["ticker"], df_display["name"])))

    if not detail_loading:
        with tab_wl:
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
                    })

                watchlist_df = pd.DataFrame(watchlist_rows)

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
                st.dataframe(
                    watchlist_df,
                    width="stretch",
                    hide_index=True,
                    column_config={nume: st.column_config.Column(nume, help=text) for nume, text in COLUMN_HELP.items() if nume in watchlist_df.columns},
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"watchlist_table_{st.session_state.get('table_nonce', 0)}",
                )

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


    if "Trading 212" in sel_portfolios:
        _notes = []
        if div_status.get("in_progress"):
            _notes.append(t("div.running", done=div_status.get("done", 0), tot=div_status.get("total", 0)))
        elif div_snapshot and div_snapshot.get("fetched_at"):
            _ts_div = datetime.fromtimestamp(div_snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
            _notes.append(t("div.updated", ts=_ts_div) + (f" · ⚠️ {div_snapshot['error']}" if div_snapshot.get("error") else ""))
        else:
            _notes.append(t("div.none"))
        if rat_status.get("in_progress"):
            _notes.append(t("rat.running", done=rat_status.get("done", 0), tot=rat_status.get("total", 0)))
        elif rat_snapshot and rat_snapshot.get("fetched_at"):
            _ts_rat = datetime.fromtimestamp(rat_snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
            _notes.append(t("rat.updated", ts=_ts_rat))
        else:
            _notes.append(t("rat.none"))
        st.caption(" · ".join(_notes))

    if div_status.get("in_progress") or rat_status.get("in_progress"):
        _watch_background_jobs()


_tbl_state = st.session_state.get(f"positions_table_{st.session_state.get('table_nonce', 0)}")
_tbl_rows = []
if _tbl_state:
    try:
        _tbl_rows = list(_tbl_state["selection"]["rows"])
    except Exception:
        _tbl_rows = []
_cached_rows = st.session_state.get("_table_rows")
if _tbl_rows and _cached_rows and "selected_ticker" not in st.session_state and _tbl_rows[0] < len(_cached_rows):
    _row = _cached_rows[_tbl_rows[0]]
    st.session_state["selected_ticker"] = _row["ticker"]
    st.session_state["selected_row"] = _row
    st.session_state["total_portfolio_value"] = st.session_state.get("_table_total", 0)
    st.session_state["scroll_to_top_detail"] = True

_wl_state = st.session_state.get(f"watchlist_table_{st.session_state.get('table_nonce', 0)}")
_wl_rows = []
if _wl_state:
    try:
        _wl_rows = list(_wl_state["selection"]["rows"])
    except Exception:
        _wl_rows = []
_wl_cached = st.session_state.get("_watch_rows")
if _wl_rows and _wl_cached and "selected_ticker" not in st.session_state and _wl_rows[0] < len(_wl_cached):
    _wrow = _wl_cached[_wl_rows[0]]
    st.session_state["selected_ticker"] = _wrow["ticker"]
    st.session_state["selected_row"] = _wrow
    st.session_state["total_portfolio_value"] = st.session_state.get("_table_total", 0)
    st.session_state["scroll_to_top_detail"] = True

_url_detail = st.query_params.get("detail")
_sel = st.session_state.get("selected_ticker")
_synced = st.session_state.get("_url_ticker")
if _sel is not None:
    if _synced != _sel:
        st.query_params["detail"] = str(_sel)
        st.session_state["_url_ticker"] = _sel
    elif _url_detail != str(_sel):
        for _k in ("selected_ticker", "selected_row", "_url_ticker"):
            st.session_state.pop(_k, None)
        st.session_state["scroll_to_top_main"] = True
        st.session_state["table_nonce"] = st.session_state.get("table_nonce", 0) + 1
elif _synced is not None:
    st.session_state.pop("_url_ticker", None)
    if _url_detail is not None:
        st.query_params.clear()

if "selected_ticker" in st.session_state and "selected_row" in st.session_state:
    render_detail_view(st.session_state["selected_row"], st.session_state.get("total_portfolio_value", 0), api_key_id, api_secret)
else:
    if st.session_state.get("_page") == "settings":
        from settings_page import render_settings
        from events_ui import render_settings_section as _events_settings
        render_settings(_me, [(t("side.updates"), _section_updates), (t("side.xtb_import"), _section_xtb_import),
                              (t("set.events"), lambda: _events_settings(_me))])
        st.stop()
    render_main_view()
