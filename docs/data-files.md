# Files in `data/`

Everything is JSON except `auth_secret`. Do not commit this folder:
`config.json` contains Trading 212 keys and `users.json` password hashes.

## Shared (`data/`)

| File | Content |
|---|---|
| `users.json` | Accounts, roles, salted PBKDF2 password hashes; for accounts with 2FA also the TOTP secret, the last used time step and salted SHA-256 hashes of the recovery codes |
| `twofa_policy.json` | Admin 2FA policy: `optional`, `admins` or `all` (missing file: optional) |
| `auth_secret` | Secret used by the login session |
| `ui_prefs.json` | Interface preferences |
| `instruments_cache.json` | Trading 212 instrument metadata |
| `justetf_cache.json` | justETF data for ETFs |
| `yahoo_auto_map.json` | Yahoo symbols found automatically for tickers whose guessed symbol has no prices (symbol or null, guessed symbol, ISIN, last check) |
| `backup_request.json` | On-demand backup from Settings > Backup: `requested` (by the app), then `running`, `done` or `failed` (by the host script) |
| `quality_cache.json`, `quality_status.json` | Quality, risk and dividend scores and job progress |
| `market_context_cache.json`, `market_context_status.json` | Benchmark (S&P 500) data and job progress |
| `uptime_status.json` | Host watchdog: last health check, consecutive failures, whether the admins were alerted |
| `presence.json` | Online users view (admin): per signed-in browser session a random id, user, first/last seen, User-Agent and IP; entries older than 24 h are removed. No passwords, tokens or cookies |
| `service_status.json` | Status page: the last requests to Yahoo, justETF, Trading 212 and SMTP (time, success, duration) and the last error of each |
| `log_problems.json` | Log watchdog: error patterns from the last 24 hours with count, last time and an example |
| `strategy_cache.json`, `strategy_status.json` | Raw metrics for the strategy lenses per ticker (financial statements, estimates, dividend history, 10-year bond yield, sentiment, event timeline) and the market context (`_market`), daily, and job progress |
| `sec_tickers.json` | SEC ticker to CIK map for EDGAR requests, weekly |
| `exposure_cache.json`, `exposure_status.json` | Sector, country, ETF sector weights (Yahoo Finance) and ETF country weights (justETF) per ticker, weekly, and job progress |
| `events_cache.json`, `events_status.json` | Upcoming earnings and dividend dates per ticker (Yahoo Finance, 12 h) and job progress |
| `manual_metrics.json` | Manually entered metrics, when present |
| `mail.json` | SMTP settings for notifications (password in plain text, mode 600) |
| `notify_state.json` | Times of sent alerts and the last SMTP error |
| `backup_status.json` | Time of the last successful backup (written by the backup script) |

## Per user (`data/users/<name>/`)

| File | Content |
|---|---|
| `config.json` | Trading 212 key and secret, refresh interval |
| `account_info_cache.json` | Account currency |
| `portfolio_cache.json` | Latest Trading 212 snapshot |
| `dividends_cache.json`, `dividends_status.json` | Dividends per ticker and job progress |
| `ratings_cache.json`, `ratings_status.json` | Analyst recommendations, upside to the mean price target, and job progress |
| `alert_rules.json`, `alert_rules_state.json`, `alert_log.json` | Position alert rules (price, score, concentration, events), their state between checks, and the last 200 fired alerts |
| `strategy_profile.json` | Investor profile for the strategy lenses (which lenses count towards convergence) |
| `privacy.json` | Privacy setting: start the session with amounts hidden, separately on the phone and the desktop |
| `events_prefs.json`, `events_notified.json` | Calendar email opt-in and days ahead; events already emailed |
| `weekly_report.json`, `weekly_report_state.json` | Weekly report opt-in, day and hour; last week sent and the dividend totals at that time (for "received since the last report") |
| `t212_fills.json` | Executed orders used to rebuild history |
| `t212_first_dates.json` | First purchase dates |
| `t212_flows.json` | Deposits and withdrawals (for XIRR) |
| `t212_history_reconstructed.json` | Rebuilt daily history, Trading 212 |
| `xtb.json` | Imported XTB accounts, positions, cash operations |
| `xtb_prices.json`, `xtb_prices_status.json` | Yahoo prices for XTB positions and progress |
| `xtb_history_reconstructed.json` | Rebuilt daily history, XTB |
| `portfolio_history.json` | Recorded value points |
| `portfolio_history_multi.json` | Value points per portfolio |
| `ticker_map.json` | Manual mapping to Yahoo symbols (wins over `yahoo_auto_map.json`) |
| `watchlist.json`, `watchlist_cache.json`, `watchlist_status.json` | Watchlist, its data (scores recalculated daily, `updated`; price every 15 min, `price_updated`) and progress |
| `notes.json` | Per-position notes |
| `alerts.json`, `alert_state.json` | Loss-to-profit alerts and dismissed state |

Temporary files named `.<name>.json.<random>.tmp` are left by an interrupted
write and can be deleted.
