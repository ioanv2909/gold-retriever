## 0.2.36 — 2026-10-22

- Privacy mode: the "start the session with amounts hidden" setting is separate for the phone and the desktop (Settings > 🔒 Privacy). The old common setting applies to both until one is changed. Switching between the phone and full versions from the user menu applies that version's setting.

## 0.2.35 — 2026-10-22

- Privacy mode: Settings > 🔒 Privacy has an option to start the session with amounts hidden. Hidden amounts show as •••••: the summary totals (the market value then shows the return % instead of the P/L), the history chart's Y axis and hover, the profit change of the period, cash, the returns over period, the amount columns of the positions table (quantity, cost, value, P/L, dividends), the exposure amounts and, on the position page, quantity, value, cost, P/L, dividends and the XTB purchase tables. Percentages, prices and charts stay.
- A 👁 Show amounts / 🙈 Hide amounts button next to the Summary heading switches them for the rest of the session, with or without the setting.

## 0.2.34 — 2026-10-22

- Phone version: the price chart offers only 1M, 3M, 1Y, 5Y and Max, so the buttons fit on one row. A period not offered on the phone (1D, 1W, YTD) opens as the nearest one (1M or 1Y).

## 0.2.33 — 2026-10-22

- Phone version: the period choice of the price chart (position page) and of the portfolio history chart is a row of large buttons spanning the screen width instead of small radio dots. The price chart's Enlarge button and buy-marker note are hidden on the phone.

## 0.2.32 — 2026-10-22

- Phone version: touching and dragging a chart no longer selects a region and zooms; the page scrolls instead. Tapping a point still shows its values. The chart toolbar is hidden on the phone.

## 0.2.31 — 2026-10-22

- Phone version: on a phone (detected from the browser) the same app shows less. Main page: the positions table keeps only name, current value, P/L and return; the Strategies, Exposure and Compare tabs, the filters, the table notes and the history chart's captions and Enlarge button are hidden; the header and the summary metrics are laid out for a narrow screen. Position page: chart, holdings, scores, dividend score, analysts, signals and notes stay; orders, benchmark comparison, valuation, extra indicators, growth, ownership, technical, historical performance, strategy lenses and the buy checklist are hidden. Settings are not available on the phone.
- The user menu switches between the phone and full versions (`?view=compact` / `?view=full`, kept for the session).

## 0.2.30 — 2026-10-21

- New strategy lens "Trend & momentum" (the data-driven layer, from prices only): 12-1 momentum, 6-month return versus the S&P 500, distance from the 200-day average in standard deviations and RSI (14 days; 45–65 scores best, both extremes score low). A price more than 2.5 standard deviations above the 200-day average is flagged as stretched. It also applies to ETFs, which now show this lens on the position page and in the matrix.
- Investor profile (Strategies tab, saved per user): Balanced (all lenses), Value, Growth, Dividend income, Momentum or Custom (pick the lenses). Convergence counts only the profile's lenses; the other columns stay visible in grey and the position page shows the profile's cards first, marked with ★. Still no combined score.
- The lenses are recomputed once after the update (new metrics).

## 0.2.29 — 2026-10-21

- Exposure tab: a selector between Composition (the sector, country and currency charts), Sector rotation and Factors, kept in the URL (`?ex_view=`). The new views download prices only when opened.
- Sector rotation: a Relative Rotation Graph of the 11 SPDR sector ETFs versus SPY (weekly prices, 5-week tails), with the four phases (Leading, Weakening, Lagging, Improving), the share of your portfolio in each phase (ETFs split by sector), bigger dots for the sectors you hold, and a table of each sector's return versus the S&P 500 over 1, 3, 6 and 12 months.
- Factors: a regression of the current portfolio's weekly returns over two years on the market (SPY) and on factor ETFs minus the market (small caps IWM, value VLUE, momentum MTUM, quality QUAL, low volatility USMV, dividend SCHD). It shows the market beta, R², the coverage and the tilt on each factor, with statistically weak tilts faded.

## 0.2.28 — 2026-10-21

- Two new strategy lenses, in the Strategies tab and on the position page:
  - Sentiment: analyst upgrades minus downgrades and raised versus lowered targets (90 days), EPS revisions, mean recommendation, short interest and its change, insider buying minus selling as a share of market cap (6 months, open-market trades only), change in large institutions' holdings, and the tone of the last 30 days of news headlines (keywords);
  - Event-driven: how often earnings beat the estimate (last 8 quarters), the average surprise and the average price reaction the day after, and the balance of positive and negative events in the last 90 days. A 6-month timeline lists analyst rating changes, insider trades, earnings, SEC 8-K filings (US companies: acquisitions, management changes, restructurings, impairments, restatements, auditor changes, bankruptcy) and news classified by keywords (M&A, management, regulation, patents, dividends and buybacks, legal), with links. The next earnings date is shown as the next catalyst.
- Market context line (VIX and the S&P 500 versus its 200-day average) above the lenses; it does not enter the scores.
- SEC EDGAR requests carry the first admin's email as contact, as SEC requires; without an admin email EDGAR is not used. SEC is a new row on the Status page, with a "Test now" probe.
- Position alerts: new "Event alerts" rule (Settings, Alerts): an email and banner for each new 8-K of the types above, analyst downgrade or insider purchase on a held position. Events already present when the rule is turned on are not announced.
- Convergence now counts six lenses. The lenses are recomputed once after the update (new metrics).

## 0.2.27 — 2026-10-21

- Strategies tab: lens scores are shown as cells shaded in one green hue, darker for higher scores (steps at 35, 50, 65 and 80), instead of bars in the theme's red, which read as negative. Every column has a tooltip explaining what it measures and how to read it.

## 0.2.26 — 2026-10-21

- Strategy lenses: four views of every stock, each with a score X/100, a one-line verdict and the signals behind it (value, target, red flag, why it matters):
  - Value: P/E versus the company's own history, free cash flow yield, earnings yield versus the 10-year bond, Graham number, Piotroski F-score, EV/EBITDA; a cheap stock with a weak quality score is flagged as a possible value trap;
  - Growth: revenue and EPS growth (historical and estimated), EPS revisions over 90 days, PEG, Rule of 40;
  - DDM: two-stage dividend discount model, required return by CAPM (10-year bond + beta × 5% risk premium), growth = the lower of the 5-year dividend CAGR and ROE × (1 − payout); value, margin of safety and a sensitivity table (required return and growth ± 1 pp). Not applied to ETFs, yields under 1%, dividend histories under 5 years or dividends cut twice in 10 years;
  - Dividend growth: consecutive years of increases, dividend growth over 3, 5 and 10 years, Chowder rule, payout trend, and the yield on your purchase price.
- Convergence: how many lenses are positive and how many negative, instead of one combined score.
- New main tab "Strategies" (`?tab=strategies`): positions × lenses matrix, sorted by convergence, with a "mostly positive / mostly negative" filter; a click opens the position. The position page has a new "Strategies" section with the cards and the details of each lens.
- The lenses are recomputed daily in the background (`strategy_cache.json`, shared); the job is listed on the Status page.

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

