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
- `app.py` - entry point, login gate, header, main view (summary, chart, positions, watchlist).
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
- `exposure.py`, `exposure_ui.py` - portfolio exposure by sector (with ETF look-through), country and currency, and the Exposure tab.
- `analysts.py`, `analysts_ui.py` - analyst price targets, recommendations, estimates, revisions and rating changes from Yahoo Finance, and the Analysts section on the position page.
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
first account is an admin who can create users from Settings.

## Background work

Slow jobs (dividends, ratings, quality scores, XTB prices, history rebuilds)
run in threads and write their progress to `*_status.json`. The UI reads the
cache and reruns while a job is in progress, so the page never blocks on
network calls.

## Quality

`tests/` holds unit tests (XIRR, FX conversion, number parsing). CI
(GitHub Actions) compiles every module, checks that all imports resolve and
runs the tests.
