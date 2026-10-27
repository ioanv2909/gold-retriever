## 0.3.26 — 2026-10-27

- Weekly email report, per user, off by default (Settings > Weekly report: day and hour, default Saturday after 09:00). It contains the portfolio value now and 7 days ago (all portfolios, from the value history), the result of the week without deposits, net deposits, total unrealized P/L, the 3 biggest gains and losses over 7 days (all T212 and XTB positions, one Yahoo request), Trading 212 dividends received since the last report and the events of the next 7 days. The settings page can preview it and send a test report. It goes to the account's email address, in the user's language, at most once a week.
- Notifications: a notification type added after the admin saved the settings (here "Weekly report") is on by default instead of silently off; the admin can still turn it off.

## 0.3.25 — 2026-10-27

- Watchlist prices every 15 minutes. Between the daily full recalculation (name, scores, risk), a light job fetches only the last price of all watchlist symbols in one Yahoo request and writes it with its own time (`price_updated`); the date of the full recalculation stays unchanged, so scores are still recalculated once a day. It does not run while the full recalculation runs; new symbols keep the full calculation. The page reloads by itself when the prices change.
- Watchlist table: new "Price at" column (time of the last price, or its date if it is not from today) and English column names (they were shown in Romanian).

## 0.3.24 — 2026-10-27

- Automatic page reload now also reacts to new watchlist data (after the daily watchlist refresh, a manual refresh or an added symbol). The watchlist cache is rewritten after every symbol during a refresh, so the page reloads once, when the refresh has finished, not once per symbol.

## 0.3.23 — 2026-10-27

- Backup: the archive is built from a copy of `data/`, not from the live folder. The app keeps writing while the backup runs, and tar on the live folder warned "file changed as we read it" and could store a half-written file. The app replaces files by rename, so the copy reads every file whole; if a temporary file vanishes during the copy, the copy is retried (up to 3 times). Temporary files are left out and tar errors now fail the backup instead of being ignored. After updating, copy the script to `/usr/local/sbin/` again.

## 0.3.22 — 2026-10-27

- The main page no longer hides XTB when Trading 212 has no usable data. Before, three cases showed only a message and nothing from XTB (no sums, no table, no XTB position links): a user with only XTB imports ("no data in cache"), a Trading 212 account with no open positions ("No open positions"), and a first Trading 212 fetch that failed (only the error). Now the Trading 212 message stays on top and the page continues with the XTB positions; "Trading 212" is offered in the portfolio picker only when its data is usable (an account with cash and no positions keeps it). Without XTB accounts the behaviour is unchanged. The Trading 212 value history is not recorded while its data is missing, so the chart does not drop to zero.
- New end-to-end tests run the whole main page (AppTest) for each case in a separate process, with its own `data/` folder and no network.

## 0.3.21 — 2026-10-27

- English UI: texts built directly in the code were shown in Romanian (XTB prices caption, position weight, Yahoo query spinner, price-history corrections, watchlist messages, currency effect, "Multiple holdings", score thresholds and checklist tooltips, disk write error). They are now translated. The trend checklist tooltip was translated only in pieces ("from the highul"); it now has a full translation.
- Wrong Yahoo symbols are fixed automatically. When the symbol guessed from the broker ticker has no prices on Yahoo (for example `IITU` instead of `IITU.L`, or `DJGTEEX.DE` instead of `EXI2.DE`), the background job searches Yahoo by the base symbol and then by ISIN, keeps the first symbol that has prices and logs the change. Results are shared (`data/yahoo_auto_map.json`); each ticker is rechecked after a week. A manual mapping on the position page still wins.
- Less log noise: the user lookup no longer triggers Streamlit's "missing ScriptRunContext" warning outside a page run.

## 0.3.20 — 2026-10-27

- New Settings > Backup tab (admins only): last successful backup (time, encrypted or not, archive name), a "Back up now" button and the restore procedure (testing an encrypted archive, full restore, where the keys must live). The button writes a request into `data/backup_request.json`; a root cron line on the host (`backup-goldretriever.sh --if-requested`, every minute) runs the backup and reports `done` or `failed`, shown live on the page. If the request is not picked up within 3 minutes the page shows the missing cron line.
- Backup script: a lock prevents two backups at the same time; status files in `data/` are written as a new file and renamed, so root never follows a symlink left there. After updating, copy the script to `/usr/local/sbin/` again.

## 0.3.19 — 2026-10-27

- Backup: optional tag in the archive name, before the extension (`data-YYYY-MM-DD_HHMMSS-<tag>.tar.gz.gpg`), read from `BACKUP_TAG` or the git-ignored file `backup-tag` next to `backup-key.asc`. Only letters, digits, `_` and `-` (at most 32); an invalid tag fails the backup with an alert. After updating, copy the script to `/usr/local/sbin/` again.

## 0.3.18 — 2026-10-27

- Times were shown in UTC (for example "Positions/cash updated" two hours behind in Romania): the container had no time zone. `docker-compose.yml` now sets `TZ`, `Europe/Bucharest` by default; another zone can be set with `TZ=...` in `.env`. Affects the times on the page, in the log and in emails.

## 0.3.17 — 2026-10-27

- Automatic page reload: when the background refresh writes new data (Trading 212 portfolio, XTB prices, dividends), the open main page and the position page reload by themselves, so the sums are up to date without a click. A check runs every 30 seconds and reads a cache file only when its modification time changed; a reload happens only on a new `fetched_at`. On the position page the row is rebuilt from the fresh data without jumping to the top. Automatic reloads do not count as activity for session expiry. Per-user switch in Settings > Updates, on by default.

## 0.3.16 — 2026-10-26

- Fix (tests): the test suite read the real SMTP settings and could send real security emails (for example "2FA dezactivat" for the test account `ana`) and write `data/notify_state.json`. Tests now use temporary notification files, a real SMTP connection fails the test instead of sending, and any write into `data/` fails the test.

## 0.3.15 — 2026-10-26

- Sign-in throttling by IP, not only by account. 5 failures for the same account from the same IP lock that pair for 5 minutes, so the owner signing in from another IP is not locked out. 20 failures from one IP within 15 minutes, on any accounts, block that IP for 15 minutes. 50 failures on one account within an hour, from any IPs (distributed attack), lock the account for 15 minutes. Each block is logged as an `[auth]` line and sends a security email. Old failures are forgotten after 15 minutes and the counters are pruned, so memory stays bounded.
- The client IP is the address of the connection. `X-Forwarded-For` is sent by the client and can be forged, so it is used only when the connection comes from a trusted proxy listed in `GR_TRUSTED_PROXIES` (IPs or networks, comma-separated).
- `.streamlit/config.toml`: uncaught errors are no longer shown in the browser (traceback, paths, code); users see a generic message and the details stay in the log. Upload limit 10 MB, as in the XTB upload checks. XSRF protection and CORS stay on, no file watching, no usage statistics.
- Backup encryption: with a GPG public key in `backup-key.asc`, `tools/backup-goldretriever.sh` encrypts the archive (`data-*.tar.gz.gpg`) before it reaches the share; the private key stays off the server. The plain archive is built in a private temporary folder and removed. Without the key the archive stays unencrypted and Settings > Status shows the backup as "Not encrypted". Rotation keeps the last 14 archives of both kinds. Setup and restore in `docs/backup-and-notifications.md`.

## 0.3.14 — 2026-10-26

- Two-step sign-in (2FA) with codes from an authenticator app (TOTP, RFC 6238: 6 digits, 30 seconds, one step of clock drift allowed). Each user turns it on in Settings > 🔐 Security (the former Password tab): QR code generated on the server (segno) or the key by hand, confirmed with a code before it is saved, then 10 single-use recovery codes shown once, with a download. The code is asked only at sign-in with the password; a device that is already signed in keeps its cookie under the existing session rules.
- At sign-in, after a correct password, the app asks for the app code or a recovery code; the step expires after 5 minutes. Wrong codes count towards the same lockout as wrong passwords (5 failures, 5 minutes). A code cannot be used twice. Using a recovery code sends a security email with the number of codes left.
- Turning 2FA off and new recovery codes need the current password and a code. Turning 2FA on or off signs out the other open sessions of the account.
- Admins: a 2FA column in the users list, "Reset 2FA" for an account that lost its phone, and a policy in Users > Sessions: optional (default), required for administrators, or required for everyone (the demo account is exempt). An account that must have 2FA turns it on right after the password.
- Every 2FA event is written to the log as an `[auth]` line and sends a security email. Secrets and codes are never logged or emailed. New dependency: `segno` 1.6.6 (pure Python, BSD).

## 0.3.13 — 2026-10-26

- Settings > Log checks the admin role itself before showing anything, in addition to the tab being built only for admins.

## 0.3.12 — 2026-10-26

- Fix: Settings > About showed "CHANGELOG.md not found". The file was left out of the Docker image (`.dockerignore` excludes `*.md`); it is now copied, so the full release notes are shown again.
- The build is no longer labelled "uncommitted" because of untracked files; only changes to tracked files count.

## 0.3.11 — 2026-10-26

- Settings > Log shows the newest lines first by default, with a choice between newest first and oldest first. The download follows the chosen order.

## 0.3.10 — 2026-10-26

- Sign-in events are written to the log (Settings > Log) as `[auth]` lines with the account and the IP: sign-in by password, session resumed from the cookie, failed sign-in, account locked after 5 failures, sign-in refused while locked, cookie rejected (invalid, expired or idle), session ended (expired, signed out by an admin, account deleted), sign-out, password change and the first admin account. Passwords and tokens are never logged; a user name that does not look like an account name is logged as `<invalid>`, so a password typed in the wrong field does not reach the log. These lines are not reported as log problems.

## 0.3.9 — 2026-10-26

- New admin tab Settings > Log: the last 1000 lines the app wrote to the log (stdout/stderr), with a choice of 100, 300 or 1000 lines, a text search, an option to hide known noise and a download as .txt. The lines are kept in memory, so the list starts empty after each container restart.

## 0.3.8 — 2026-10-26

- Trading 212 API errors (cash, positions, instruments, orders, dividends, history) now show a clear message in Romanian or English based on the HTTP code: 401 (key or secret not accepted, or missing permissions), 403 (missing permissions), 429 (too many requests); other codes point to the container log.
- The container log gets one line per failed request with the user, the endpoint, the HTTP code and the first 200 characters of the response body. The API key, the secret and the Authorization header are removed from the log and from the messages shown in the app.

## 0.3.7 — 2026-10-26

- Fix: the portfolio chart jumped to about 3.3 times its value for single points. The Trading 212 account currency is cached; when the cache expired and the request to Trading 212 failed (rate limit of 1 request per 30 seconds, or network), the currency was unknown and the history point labelled the Trading 212 value as EUR instead of the account currency (RON). Now the last known currency is kept when the request fails, and no history point is written while the currency is unknown.
- The jumps confirmed with `tools/fix_history_rates.py --max-ratio 2` (three points on 2026-10-26) can be removed with `--apply`.

## 0.3.6 — 2026-10-26

- `tools/fix_history_rates.py`: older history points use RON as the base currency (RON=1.0), and the script marked them as made-up rates. A made-up rate is now a second currency at 1.0 next to the base one. For points with a jump (more than 1.5 times off the median) it also shows, per portfolio, the currency and the change from the previous point, without amounts.

## 0.3.5 — 2026-10-26

- Fix: when Yahoo did not answer, an exchange rate fell back to 1.0 and stayed cached (up to an hour, `fetch_fx_rate` had two `st.cache_data` layers). History points written meanwhile counted, for example, RON amounts as euro, so the portfolio chart jumped to several times its real value and the older history looked flat. This happened more often after container restarts, which empty the cache.
- A failed rate now falls back to the last good rate (at most 7 days old, kept in `data/fx_last_good.json` so it survives a restart). Without one, the 1.0 fallback is kept for display only, is cached for a minute instead of up to an hour, and no history point is written: a missing point instead of a wrong one.
- `tools/fix_history_rates.py`: shows, without amounts, the history points saved with a made-up rate (and their ratio to the median of the previous points); with `--apply` it removes them after a `.bak` copy, and with `--max-ratio X` also points more than X times off.

## 0.3.4 — 2026-10-26

- Tests: the check that `auth.py` no longer uses `components.html` looks for the import and the call, not for the name in a comment (it failed in 0.3.3; the app itself was not affected).

## 0.3.3 — 2026-10-26

- The sign-in cookie is written by a script run directly in the page (`st.html` with JavaScript, the same helper used for printing) instead of `st.components.v1.html`, which Streamlit deprecated and will remove. Sign-in, sign-out and session expiry behave as before.

## 0.3.2 — 2026-10-26

- Python 3.11 in the Docker image (`python:3.11-slim`) and in CI, needed by Streamlit 1.66 (it requires Python 3.11 or newer). In 0.3.1 the image build failed on Python 3.10 and the server kept running 0.3.0; the tests already ran on Python 3.11 locally.

## 0.3.1 — 2026-10-26

- Streamlit 1.66.1 (was 1.65.0) and Pillow 13.0.0 (was 12.3.0, installed by Streamlit), pinned in `requirements.txt`. This fixes the known Pillow vulnerabilities listed under 0.2.47; `pip-audit` now finds none, so the CI audit step blocks the workflow again on known vulnerabilities.
- The docker-compose override used on the server no longer mounts the project folder into the container, so the read-only filesystem from 0.3.0 also covers the app code; code changes reach the app only through `./tools/deploy.sh`.

## 0.3.0 — 2026-10-26

Security release: together with 0.2.47–0.2.50 (dependency scanning, upload limits and path checks, session expiry, new device alerts) it starts the 0.3 series.

- Container hardening in `docker-compose.yml` (the Dockerfile is unchanged): the image filesystem is read-only, the only writable places are `data/` (the existing volume) and a 64 MB tmpfs on `/tmp` (HOME and the yfinance cache); all Linux capabilities are dropped, `no-new-privileges` is set, at most 256 processes/threads and 1 GB of memory. `PYTHONDONTWRITEBYTECODE=1` stops Python from trying to write `__pycache__` into the image. Every file the app writes was checked: all go to `data/`; `build_info.json` is written on the host before the build; Streamlit caches and uploads stay in memory.

## 0.2.50 — 2026-10-26

- New device alert: at sign-in (password, or a session reopened from the cookie; once per browser session, not on every page run) the device is compared with the ones seen for that account. The device is the browser and system from the User-Agent ("Chrome / Windows"), without versions, so a browser update does not count as new; the IP is not part of it. A new device sends a security email to the admin with the device, time and a shortened IP (`192.168.x.x`, or the first three IPv6 groups), never passwords, tokens or cookies.
- The list is kept in `data/known_devices.json`: up to 10 devices per user (the one used least recently drops out), with only a hash, the short label and times, no full User-Agent and no IP. The first sign-in of an account, and of each existing account after this update, records the device without an alert. At most 3 alerts per user per hour.

## 0.2.49 — 2026-10-26

- Session expiry: a session ends after 8 hours without activity or 30 days after sign-in (the sign-in cookie lifetime). Both limits are defaults that an admin can change in Settings > 👥 Users > ⏱️ Sessions (1–720 hours, 1–365 days, with a "Restore defaults" button); a change sends a security email. A lower limit applies at once to every open session and every existing cookie; a higher maximum duration applies only to new sign-ins.
- Activity means a page run asked for by the user; the one-minute heartbeat and automatic reloads after background jobs do not count, so a tab left open expires too, within a minute of the limit. Activity is kept on the server in `data/session_activity.json`, keyed by a short hash of the cookie signature (no token, user name or IP), written at most every 5 minutes per cookie, and pruned after the maximum duration.
- On expiry the session is removed, the cookie is cleared and the sign-in page shows "Your session has expired" (RO/EN). Signing out also marks the cookie as revoked on the server, so a copy left in the browser cannot reopen the session.
- No one is signed out by the update: cookies issued before this version have no activity record and count as active from the first visit; their 30-day limit stays as issued.

## 0.2.48 — 2026-10-26

- XTB import: an uploaded report is checked in memory before it is parsed, and nothing is written before the check. Rejected with a clear RO/EN message: files over 10 MB (also refused by the uploader itself), files that are not zip archives, zip files without the xlsx structure (`[Content_Types].xml`, `xl/workbook.xml`), more than 2,000 internal parts, more than 100 MB once unpacked or a part compressed more than 200 times (zip bomb), and internal names that are absolute or contain `..`. The check reads only the zip directory and unpacks nothing. Limits are constants in `upload_guard.py`.
- File paths: a user name that reaches a path is no longer rewritten (`a.b` and `a_b` used to map to the same folder) but refused unless it is `[a-z0-9_-]`, 1–32 characters. Every per-user and shared data file, and the user folder removed or filled by the user admin, now goes through `userctx.contained_path`, which allows only plain file names and checks with `realpath` that the result stays inside `data/users/<name>/` or `data/`, symlinks included. Existing accounts already use valid names and keep their folders. Tickers, portfolio names and uploaded file names never reach a path.

## 0.2.47 — 2026-10-26

- Dependency scanning: `.github/dependabot.yml` checks pip (`requirements.txt`), the Docker base image and GitHub Actions every Monday; minor and patch updates come grouped in one PR per ecosystem, major ones separately. Python version bumps of the `python` base image are ignored (changed deliberately). `justetf-scraping` is installed from a GitHub zip URL and is not tracked by Dependabot; its commit hash is updated by hand.
- CI: new `pip-audit` step on the installed dependencies (from `pip freeze`, so indirect dependencies are included). `justetf-scraping` is not on PyPI and is left out of the audit; its own dependencies are still audited. Known vulnerabilities are listed as errors in the log; a report that cannot be produced (network error) only gives a warning.

### Known issues

- Pillow 12.3.0 (installed by Streamlit) has known vulnerabilities, fixed in 13.0.0. Streamlit 1.65.0 requires `pillow<13`; the upgrade to `streamlit==1.66.1` and `pillow>=13` is postponed until it is tested. Until then the `pip-audit` CI step is informational (`continue-on-error`) and does not block the workflow.

## 0.2.46 — 2026-10-26

- Settings > 👥 Users > 🟢 Online now (admins only): the users seen in the last 5 minutes, sorted by last activity, with role, first seen, device/browser, IP and the number of open sessions, plus a Refresh button. Each signed-in browser session gets a random id and a heartbeat every minute while the tab is open; the record is written to `data/presence.json` at most every 45 seconds per session, and entries older than 24 hours are removed. No passwords, tokens or cookies are stored.
- "Sign the user out" button in the same view: all sessions of that user end within a minute and their saved sign-in stops working. Cookies issued before this version stay valid until an admin uses the button. A security email is sent.

## 0.2.45 — 2026-10-26

- Settings > 🔐 Password: every user, not only admins, can change their own password (current password, new password, confirmation). The account always comes from the signed-in session. The rules are the same as for accounts created by an admin (minimum 8 characters), and wrong attempts count toward the same lockout as sign-in (5 attempts, 5 minutes). A successful change sends a security email (without the password) and signs out the other open sessions.
- A password set by an admin (new account or reset) must be changed at the next sign-in before the app opens.
- Security emails about accounts now say "De catre" (by) instead of "Admin", since the user can make the change themselves.

## 0.2.44 — 2026-10-24

- Position alerts (banner and email) show the instrument name instead of the symbol. When the broker gives only the symbol (often the case for XTB), the name comes from Yahoo Finance; the score refresh now keeps it, so every instrument is refreshed once.

## 0.2.43 — 2026-10-24

- GitHub Pages: Google Search Console verification tag in `docs/index.html`.

## 0.2.42 — 2026-10-24

- Static project page for GitHub Pages in `docs/` (`index.html` with no external libraries, title, description, Open Graph and structured data, light and dark theme), plus `robots.txt` and `sitemap.xml` for https://ioanv2909.github.io/gold-retriever/.

## 0.2.41 — 2026-10-24

- README: the first sentence now says what the app is (self-hosted portfolio tracker for Trading 212 and XTB, Interactive Brokers planned), features as a table, Docker Compose quick start with the compose file, placeholders for more screenshots, separate Support (Ko-fi) and License sections. The security note now says the container runs as uid 1000.

## 0.2.40 — 2026-10-22

- The Streamlit top bar (activity indicator and the three-dot menu) is gone on every page, including the login page; the page starts right at the top.
- Theme (same as system, light, dark) moved to Settings > 🎨 Appearance. It is kept in the browser, separately on each device, and the page reloads when it changes. On the phone, Settings opens with this section only.
- 🖨️ Print page moved to the user menu 👤 (it closes the menu, then opens the browser's print dialog).

## 0.2.39 — 2026-10-22

- The login page shows only "GoldRetriever" next to the logo, so it fits on one line on a phone.

## 0.2.38 — 2026-10-22

- The login page shows the app name (GoldRetriever — Portfolio Analyzer) next to the logo, above the sign-in form.

## 0.2.37 — 2026-10-22

- The language selector is a single 🌐 button with the language you switch to (🌐 EN in Romanian, 🌐 RO in English), on the main page and in Settings.
- The login page shows the logo above the title.
- Phone version: the main page header has no logo and no title, only the language button and the user menu.

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

