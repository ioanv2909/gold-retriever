## 0.2.25 — 2026-10-21

- Host watchdog: `tools/uptime_check.py`, run from cron every 5 minutes, checks the app's health endpoint and emails the admins when it fails twice in a row, and once more when it is back (new event "App not responding"). It covers what the in-app log watchdog cannot: the app being down. Its state is a row on the Status page.
- Status page: per-user background jobs (dividends, ratings, XTB prices, watchlist) are listed for every user, not only for the admin looking at the page.

## 0.2.24 — 2026-10-21

- Status page (Settings, Status; admins only) with a green / yellow / red / gray indicator and text on every row:
  - external services: Yahoo Finance, justETF, Trading 212 API and email (SMTP), measured on the app's real requests (last success, last error, requests and errors in the last hour, average time), plus the backup age;
  - background jobs: dividends, ratings, scores, market context, calendar, exposure, XTB prices and watchlist (running, up to date, stale or stuck);
  - the number of error patterns from the log watchdog.
  A "Test now" button makes one real request to each service (SMTP: connection and login only, no email).
- Tests no longer write service state into `data/`.

## 0.2.23 — 2026-10-21

- Log watchdog: errors written to the application log (module errors, Yahoo HTTP errors, Streamlit errors, uncaught exceptions in background threads) are grouped by pattern and listed in Settings, Notifications, "Recent problems in the log". A pattern not seen in the last 24 hours emails the admins (new event "New errors in the log", at most once every 30 minutes). Known harmless messages are ignored. It runs inside the app, so it cannot report the app itself being down.

## 0.2.22 — 2026-10-21

- Fix: when Yahoo answers HTTP 401 (invalid crumb, usually right after a start), requests are retried up to twice with a new crumb. Before, yfinance returned empty data that could be cached as "no data" for hours (calendar, ratings) or a week (exposure).

## 0.2.21 — 2026-10-21

- Fix: after a restart or deploy, background jobs (dividends, ratings, scores, calendar, exposure, prices, watchlist) no longer stay blocked for up to 30 minutes by an "in progress" state left by the previous process.

## 0.2.20 — 2026-10-21

- Fix: the exposure refresh could hang forever on a justETF request (the library sets no timeout), leaving the remaining ETFs in "ETF (no breakdown)". Requests now time out after 20 seconds and the queue moves on; a failed ETF is retried after a day.
- Exposure: stocks without a country on Yahoo take it from the ISIN prefix (issuer country), and instruments Yahoo does not classify are also looked up on justETF.

## 0.2.19 — 2026-10-21

- Exposure: ETFs are now split by country too, using the country breakdown from justETF (by ISIN), instead of a single "ETF (no breakdown)" bucket. Fetched weekly with the other exposure data; if justETF is unavailable, it is retried after a day. ETFs without country data on justETF keep the separate bucket.

## 0.2.18 — 2026-10-21

- Compare: the chosen instruments and period are kept in the address (`?tab=compare&cmp=AAPL&cmp=KO&cmp_period=1A`), so a refresh or a link reopens the same comparison; switching to another tab and back keeps them too.

## 0.2.17 — 2026-10-21

- Compare chart: end-of-line labels that would overlap are spread apart vertically (the point stays at the real value), and the axis makes room for them.
- Main page tabs have their own address too (`?tab=exposure`, `compare`, `calendar`, `watchlist`), so a refresh or a link reopens the same tab in either language; closing a position page returns to the tab you came from. Exposure, Compare and Calendar are rendered only when open.

## 0.2.16 — 2026-10-21

- Compare tab on the main page: up to five instruments (positions, watchlist or any Yahoo symbol) side by side. A chart of the return over the chosen period (YTD by default) with labels at the line ends, and a table with return, annualized volatility, max drawdown, quality, risk and dividend scores, P/E, forward P/E, dividend yield, analyst target upside, beta, market cap, sector, country and currency. Each instrument keeps its color while it stays selected.

## 0.2.15 — 2026-10-21

- Settings: language switch (RO/EN) in the page header, as on the main page; the open tab stays the same.

## 0.2.14 — 2026-10-21

- Settings keep the open tab in the address (`?page=settings&tab=alerts`), so a refresh or a shared link opens the same tab; only the open tab is rendered.

## 0.2.13 — 2026-10-21

- Settings have their own address (`?page=settings`), so a page refresh stays on Settings instead of going back to the main page.

## 0.2.12 — 2026-10-21

- Release notes: features from 0.2.7 to 0.2.11 are listed under their versions instead of "Unreleased".

## 0.2.11 — 2026-10-21

- Exposure tab on the main page: breakdown of the selected portfolios by sector, country and currency, in the display currency, as bar charts with tables. ETFs are split by their sector weights (look-through); Yahoo has no country breakdown for ETFs, so they show as a separate country bucket. Sector and country data come from Yahoo Finance and are refreshed weekly in the background.

## 0.2.10 — 2026-10-21

- Analysts section on the position page (Yahoo Finance): mean, median, low and high price targets with upside and a range chart, recommendation distribution over the last four months, EPS and revenue estimates (current/next quarter and year) with growth, EPS estimate revisions (vs 30 and 90 days ago, up/down revisions) and the latest rating changes by firm. Replaces the old single-line target block.
- New "Target %" column in the positions table: upside to the analysts' mean target, refreshed with the ratings every 12 hours.

## 0.2.9 — 2026-10-21

- Position alerts (Settings, Alerts), checked every 15 minutes in the background:
  - price alerts per position (rises to or above / falls to or below a price, in the instrument currency), firing once and re-armable; also addable from the position page;
  - score alerts when the quality, risk or dividend score falls below a threshold or drops by N points from its last peak;
  - concentration alert when a position exceeds a share of the whole portfolio (Trading 212 and XTB together).
  Fired alerts show as a banner on the main page and are emailed to the user if they have an address and an admin enabled "Position alerts" in Notifications.

## 0.2.8 — 2026-10-21

- Dividend score (X/100) for stocks, on four pillars: safety (payout from earnings and from free cash flow), growth (5-year dividend CAGR), consistency (consecutive years paid, cuts in 10 years) and yield (a yield above 8% lowers the score as a possible trap). Shown as a new "Div. score" column in the positions table and as a Dividend section on the position page, with pillar scores and indicator details.

## 0.2.7 — 2026-10-21

- Documentation: README, data flow and release notes cover the events calendar and admin notifications.

## 0.2.6 — 2026-10-21

- Calendar: new tab with upcoming earnings, ex-dividend and dividend payment dates for held positions (Yahoo Finance, refreshed every 12 hours), filterable by range and event type.
- Calendar emails: each user can opt in (Settings, Calendar) to a digest of new events N days ahead, sent to their own address; each event is emailed once.

## 0.2.1 – 0.2.5 — 2026-10-21

- Quality and risk scores are shown as `X/100` (Romanian and English).
- Version number is derived automatically from git tags (last `v*` tag plus commits since) and shown in Settings, About.
- Charts open on the YTD period by default, and the period chosen on the main chart carries over to position charts.
- Position chart period labels are translated in English (1D/1W/1M/3M/1Y/5Y).
- Unit tests for the quality/risk checklist; project notes for contributors (`CLAUDE.md`).

## 0.2.0 — 2026-10-20

- Notifications: email alerts to admins (SMTP) for failed backups, failed refreshes, XTB imports with problems and security events (Settings, Notifications).
- Backup: daily backup script for `data/` with retention, status file and failure alert; restore steps documented.
- Security: alert when an account is locked after failed logins and on every user change.
- Fix: importing an XTB report no longer shares default state between users in the same process.
- Container runs as a non-root user; dependency versions are pinned.
- Unit tests for XIRR, currency conversion, XTB parsing and import, and notifications; CI runs them.
- Documentation rewritten (architecture, data flow, data files, backup and notifications).

## 0.1.0 — 2026-10-20

First public version.

- **Accounts:** multiple users with separate data, admin page for creating and managing accounts, signed login cookie, lock after repeated failed attempts.
- **Sources:** Trading 212 (API) and XTB (xlsx report import, several accounts) in one view.
- **Currencies:** display in any currency, chosen per user.
- **Languages:** Romanian and English interface, language saved per user.
- **Returns:** market value over time, return summary with XIRR, comparison with the S&P 500 over the holding period.
- **Speed:** faster instrument detail page (cached justETF data, parallel Yahoo Finance requests).
- **Demo:** a fictional demo account (real tickers and prices, invented purchases) and scripts to create it.
- **Interface:** new name and logo, user menu at the top right, settings page (Trading 212 keys, users, about and release notes), filters moved next to the table.
- **Project:** README with screenshots, continuous integration (compile and import checks), MIT license.

