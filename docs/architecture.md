# Architecture

GoldRetriever is a self-hosted Streamlit app that analyses a portfolio held at
Trading 212 (API) and XTB (xlsx report import). It is multi-user, converts
everything to a display currency of your choice and speaks Romanian and English.

## Runtime

One Streamlit process (`app.py`) in one container. State lives in JSON files
under `data/` (mounted as a volume). There is no database and no external
service of its own; it only calls the Trading 212 API and public market data
(Yahoo Finance via yfinance, justETF).

    browser -> Streamlit (app.py) -> data/*.json
                    |
                    +-> Trading 212 API, Yahoo Finance, justETF

## Startup and routing

1. `app.py` calls `require_login()` (`auth.py`). Nothing else renders before login.
2. The header shows the logo, language switch and the user menu (Settings, Log out).
3. If the session flag `_page == "settings"`, `settings_page.render_settings()`
   is shown and the script stops. Otherwise the main view is rendered, or the
   detail view when a position is selected.

## Modules

UI
- `app.py` - entry point: language, login gate, routing (main page, position page, settings).
- `main_view.py` - main page: header, summary metrics, portfolio/currency choice, tabs.
- `history_ui.py`, `cash_ui.py` - value-over-time chart with the profit change chart; cash button.
- `positions_data.py` (no UI), `positions_table_ui.py` - computed position columns; positions table.
- `watchlist_ui.py` - Watchlist tab. `navigation.py` - open position from table selection, `?detail=`, `?page=`.
- `updates_ui.py`, `xtb_import_ui.py` - Settings > Updates and XTB import. `lang_prefs.py` - saved language.
- `auth.py` - login form, user menu, user management page.
- `settings_page.py` - Settings tabs: Trading 212 keys, Updates, XTB import, Users (admin), About.
- `detail_view.py` - per-position analysis page.
- `holdings_ui.py`, `watchlist.py`, `gauges.py` - positions table, watchlist, gauge charts.
- `i18n.py`, `descriptions.py` - RO/EN texts and tooltips.

Data sources
- `t212_api.py` - Trading 212 API calls, FX rates, cached snapshot loaders.
- `xtb.py` - parses and imports XTB xlsx reports (positions, cash operations, closed positions).
- `xtb_positions.py`, `xtb_prices.py` - XTB rows for display and their Yahoo prices.
- `yahoo.py`, `yf_compat.py`, `price_clean.py` - Yahoo access, price cleaning, benchmark return, PEG.
- `justetf_data.py`, `isin_tools.py` - ETF data from justETF and ISIN validation/resolution.

Calculations
- `portfolio_model.py` - currency conversion (`fx`) and portfolio rows across sources.
- `returns_summary.py`, `t212_history.py` - XIRR returns from deposits and withdrawals.
- `t212_history_rebuild.py`, `xtb_history_rebuild.py`, `history_multi.py` - daily value history rebuilt from fills/purchases and Yahoo closes.
- `scoring.py`, `risk.py`, `valuation.py`, `etf.py`, `checklist.py` - quality, risk and valuation indicators and thresholds.
- `position_alerts.py`, `position_alerts_ui.py` - price, score and concentration alerts: rules, background evaluation, email, settings tab, banner and the quick price alert on the position page.
- `uptime.py`, `tools/uptime_check.py` - host watchdog run from cron: health check, state, email on down/up transitions.
- `health.py`, `health_ui.py` - service status: records every request to Yahoo (yfinance hook), justETF, Trading 212 and SMTP, job freshness from the status files, live probes; the Settings > Status tab (admin).
- `logwatch.py` - log watchdog: tees stdout/stderr, groups error lines by pattern, emails admins on new patterns; list in Settings, Notifications.
- `url_tabs.py` - tabs bound to the `?tab=` URL parameter with stable ids (main page and settings), so refresh and links keep the open tab.
- `compare.py`, `compare_ui.py` - side-by-side comparison of up to five instruments: normalized return chart and a table of period stats, scores and valuation.
- `rotation.py`, `factors.py`, `portfolio_lenses_ui.py` - sector rotation (RRG of SPDR sector ETFs versus SPY) and factor exposure (regression on factor ETFs), the Rotation and Factors views of the Exposure tab; prices downloaded on demand (cached 15 minutes).
- `exposure.py`, `exposure_ui.py` - portfolio exposure by sector and country (ETFs split by their sector weights from Yahoo and country weights from justETF) and currency, and the Exposure tab.
- `analysts.py`, `analysts_ui.py` - analyst price targets, recommendations, estimates, revisions and rating changes from Yahoo Finance, and the Analysts section on the position page.
- `signals.py` - data for the Sentiment and Event-driven lenses: rating changes, insider trades, institutions, short interest, news headlines classified by keywords, earnings surprises and price reactions, SEC EDGAR 8-K filings, market context (VIX, S&P 500 vs SMA200).
- `strategies.py`, `strategies_ui.py` - strategy lenses (value, growth, DDM with CAPM, dividend growth, sentiment, event-driven, trend & momentum), the per-user investor profile: metrics from Yahoo Finance, scoring, convergence, the daily background job, the Strategies tab and the section on the position page.
- `dividend_score.py` - dividend score (safety, growth, consistency, yield) from Yahoo Finance dividend history, payout and cash flow.

Infrastructure
- `core.py` - file locations, JSON read/write with file locks, config, alerts.
- `userctx.py` - `UPath`: resolves a file name to the current user's folder, or to the shared folder.
- `users.py` - accounts, roles, PBKDF2 password hashing, migration of legacy single-user data.
- `background.py` - background refresh threads and their status files.
- `notify.py`, `alerts.py`, `notify_ui.py` - email notifications: SMTP sending with throttling, alert rules (consecutive failures, backup age, XTB import, security) and the Settings tab.
- `events.py`, `events_ui.py` - events calendar: fetches earnings and dividend dates from Yahoo Finance, the Calendar tab, per-user settings and the email digest.

## Users

Accounts are stored in `data/users.json` (salted PBKDF2 hashes, roles). Each
user has an isolated folder `data/users/<name>/`. Files that do not depend on a
user (instrument metadata, quality scores, market context) are shared. The
first account is an admin who can create users from Settings. Any user can change their own
password in Settings > Password (same lockout as sign-in); a password set by an
admin carries a `must_change` flag and has to be changed at the next sign-in.

Sign-in is stateless (a signed cookie), so `presence.py` keeps a small registry
of open sessions in `data/presence.json` for the admin view Settings > Users >
Online now: each signed-in browser session gets a random id and a heartbeat
fragment (`st.fragment(run_every=60)`) updates it, at most one write per 45 s.
Forced sign-out bumps a per-user `sess_ver` in `users.json`; once it is above 0
it is part of the cookie signature, and the heartbeat compares it with the
version the session started with, so open sessions end within a minute.

## Background work

Slow jobs (dividends, ratings, quality scores, XTB prices, history rebuilds)
run in threads and write their progress to `*_status.json`. The UI reads the
cache and reruns while a job is in progress, so the page never blocks on
network calls.

## Quality

`tests/` holds unit tests (XIRR, FX conversion, number parsing). CI
(GitHub Actions) compiles every module, checks that all imports resolve and
runs the tests.
