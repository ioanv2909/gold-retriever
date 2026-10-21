# Files in `data/`

Everything is JSON except `auth_secret`. Do not commit this folder:
`config.json` contains Trading 212 keys and `users.json` password hashes.

## Shared (`data/`)

| File | Content |
|---|---|
| `users.json` | Accounts, roles, salted PBKDF2 password hashes |
| `auth_secret` | Secret used by the login session |
| `ui_prefs.json` | Interface preferences |
| `instruments_cache.json` | Trading 212 instrument metadata |
| `justetf_cache.json` | justETF data for ETFs |
| `quality_cache.json`, `quality_status.json` | Quality, risk and dividend scores and job progress |
| `market_context_cache.json`, `market_context_status.json` | Benchmark (S&P 500) data and job progress |
| `log_problems.json` | Log watchdog: error patterns from the last 24 hours with count, last time and an example |
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
| `alert_rules.json`, `alert_rules_state.json`, `alert_log.json` | Position alert rules (price, score, concentration), their state between checks, and the last 200 fired alerts |
| `events_prefs.json`, `events_notified.json` | Calendar email opt-in and days ahead; events already emailed |
| `t212_fills.json` | Executed orders used to rebuild history |
| `t212_first_dates.json` | First purchase dates |
| `t212_flows.json` | Deposits and withdrawals (for XIRR) |
| `t212_history_reconstructed.json` | Rebuilt daily history, Trading 212 |
| `xtb.json` | Imported XTB accounts, positions, cash operations |
| `xtb_prices.json`, `xtb_prices_status.json` | Yahoo prices for XTB positions and progress |
| `xtb_history_reconstructed.json` | Rebuilt daily history, XTB |
| `portfolio_history.json` | Recorded value points |
| `portfolio_history_multi.json` | Value points per portfolio |
| `ticker_map.json` | Mapping to Yahoo symbols |
| `watchlist.json`, `watchlist_cache.json`, `watchlist_status.json` | Watchlist, its data and progress |
| `notes.json` | Per-position notes |
| `alerts.json`, `alert_state.json` | Loss-to-profit alerts and dismissed state |

Temporary files named `.<name>.json.<random>.tmp` are left by an interrupted
write and can be deleted.
