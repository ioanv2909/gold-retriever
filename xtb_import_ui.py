"""Settings > Brokers > XTB: import de rapoarte, simboluri Yahoo, ISIN-uri si stergerea unui cont."""
import hashlib
import io
import re
from datetime import datetime

import pandas as pd
import streamlit as st

import alerts
from i18n import t, x as _tx
from isin_tools import isin_issues, resolve_isin, suggest_isin
from upload_guard import MAX_UPLOAD_MB, check_xlsx
from xtb import accounts_summary, import_xtb, instruments as xtb_instruments, parse_xtb_file, remove_account, save_isin
from xtb_prices import load_xtb_prices, save_symbol_override, start_xtb_prices_refresh_background


def render_xtb_import(me):
    """Settings > XTB import (moved out of the sidebar)."""
    uploaded_xtb_files = st.file_uploader(
        _tx("Fișiere XTB (.xlsx, câte unul pentru fiecare cont)"),
        type=["xlsx"],
        accept_multiple_files=True,
        key=f"xtb_upload_{st.session_state.get('xtb_nonce', 0)}",
        max_upload_size=MAX_UPLOAD_MB,
    )

    if st.button(t("xtb.import"), key="xtb_import_btn"):
        reports = []
        errors = []

        for uploaded_file in uploaded_xtb_files or []:
            safe_name = re.sub(r"\d{6,}", "#####", uploaded_file.name)
            try:
                raw = uploaded_file.getvalue()
                rejected = check_xlsx(raw)
                if rejected:
                    errors.append(f"{safe_name}: {t('upload.' + rejected, mb=MAX_UPLOAD_MB)}")
                    continue
                file_hash = hashlib.sha256(raw).hexdigest()
                parsed = parse_xtb_file(io.BytesIO(raw))
                reports.append(import_xtb(parsed, file_hash))
            except ValueError as exc:
                errors.append(f"{safe_name}: {exc}")
            except Exception as exc:
                errors.append(f"{safe_name}: {exc}")

        try:
            alerts.record_xtb_import(reports, errors, me)
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
