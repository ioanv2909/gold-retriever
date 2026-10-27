# GoldRetriever

Self-hosted Streamlit portfolio analyzer (Trading 212 API, XTB xlsx import, yfinance/justETF).
Multi-user, any display currency, RO/EN UI. Runs in Docker (service/container `gold-retriever`,
port 8501, uid 1000). Public repo: ioanv2909/gold-retriever, branch main.

## Working rules
- Commit messages in English. No Co-Authored-By or Claude-Session lines. A hook adds the version prefix.
- Show only changed lines/diffs, not whole files, to save tokens.
- The user speaks Romanian; reply in Romanian unless asked otherwise.
- Never read, print or edit `data/` (user data, passwords, API keys, SMTP settings).
- Never paste tokens or secrets in output. Ask the user to set them via UI or env.
- Default dicts must be copied with `copy.deepcopy`, never `dict(...)` (past cross-user leak bug).
- Score values are displayed as `X/100`.
- New UI strings go in `i18n.py` with both RO and EN entries.
- CHANGELOG: never leave an "Unreleased" section (Settings > About shows the file as is). Put the entry under
  `## X.Y.Z — date` for the version the commit will get: last `v*` tag patch + commits since the tag + 1.
- Run tests before committing: `.venv/bin/python -m pytest -q` (494 tests, also run in CI).
- Commit, `git push` and `./tools/deploy.sh` are pre-approved once the tests pass: do them without asking,
  then report the result (version, health check, log errors). Still ask before anything that deletes or
  changes data (`rm`, `data/`, git history rewrites) and before other `docker` commands.

## Deploy
`./tools/deploy.sh` rebuilds and restarts the container and writes `build_info.json`
(version = last `v*` tag patch + commits since the tag; the 0.3 series starts at tag `v0.3.0`).
The container is hardened (read-only filesystem, no capabilities, pids/memory limits): the app may write only
in `data/` or `/tmp` (tmpfs, 64 MB, also HOME). New code that writes elsewhere fails in production.

## Layout
- `app.py` main view; `detail_view.py` per-position page; `settings_page.py` settings;
  `core.py` shared logic and `CHART_PERIODS`; `xtb.py`, `xtb_prices.py` XTB import;
  `notify.py`, `notify_ui.py`, `alerts.py` email notifications; `logwatch.py` log watchdog (also keeps the last 1000 log lines in memory); `log_ui.py` Settings > Log tab (admin); `health.py`, `health_ui.py` status page; `backup_ui.py` Settings > Backup tab (admin: on-demand backup via a request file + root cron, restore steps); `uptime.py` + `tools/uptime_check.py` host watchdog (cron of user ioanv, every 5 min); `events.py`, `events_ui.py` events calendar; `position_alerts.py`, `position_alerts_ui.py` price/score/concentration alerts; `background.py` refresh loop;
  `auth.py`, `users.py`, `userctx.py` multi-user; `presence.py`, `presence_ui.py` online users (admin) and forced sign-out; `known_devices.py` new device alert at sign-in; `twofa.py`, `twofa_ui.py` two-step sign-in (TOTP, recovery codes, admin policy; storage in `users.py`); `session_policy.py`, `session_policy_ui.py` session expiry (idle/absolute limits, admin setting, activity registry); `checklist.py` quality/risk scoring; `dividend_score.py` dividend score; `analysts.py`, `analysts_ui.py` analyst data; `strategies.py`, `strategies_ui.py` strategy lenses (Strategies tab + section on the position page); `signals.py` sentiment/event data (ratings, insiders, news keywords, earnings, SEC EDGAR 8-K, market context); `exposure.py`, `exposure_ui.py` sector/country/currency exposure; `rotation.py`, `factors.py`, `portfolio_lenses_ui.py` sector rotation (RRG) and factor exposure, views of the Exposure tab; `compare.py`, `compare_ui.py` ticker comparison; `symbol_resolver.py` automatic fix of Yahoo symbols with no data (search by base symbol, then ISIN; shared `yahoo_auto_map.json`); `mobile.py` phone version (compact mode); `privacy.py` hidden amounts; `autorefresh.py` page reload on new data (per-user switch); `upload_guard.py` checks on uploaded files (size, xlsx structure, zip bomb); `appearance.py` hidden Streamlit top bar, theme (Settings), print (user menu); `i18n.py` strings; `url_tabs.py` tabs bound to `?tab=` (main page and settings).
- Per-user data: `data/users/<name>/`; shared files in `data/`.
- Docs: `docs/` (architecture, data-flow, data-files, backup-and-notifications). `CHANGELOG.md`.
- Backup: `tools/backup-goldretriever.sh` (cron, Synology share), status in `data/backup_status.json`.

## Done (v0.2.6 – v0.2.25, see CHANGELOG.md)
Events calendar with email digest, dividend score, position alerts (price/score/concentration), analyst data,
exposure by sector/country/currency (ETF look-through via Yahoo and justETF), ticker comparison, URL-bound
tabs, log watchdog, admin status page, Yahoo 401 retry, host uptime watchdog (cron).

## Planned work
1. Strategy lenses (stage 1 done in v0.2.26: value, growth, DDM, dividend growth; stage 2 done in v0.2.28:
   sentiment, event-driven, event alerts; stage 3 done in v0.2.29: sector rotation, factor exposure; stage 4 done
   in v0.2.30: trend & momentum lens, per-user investor profile for convergence).
   Decisions taken with the user:
   DDM required return by CAPM (overridable later), SEC EDGAR allowed (User-Agent with the admin email),
   news sentiment by keywords only (no LLM), no combined score: show convergence (N positive / M negative).
2. New broker connector. Waiting for the user: which broker, API or file export, a sample export.

## Notes for future work
- `tests/main_page_driver.py` runs the whole `app.py` (AppTest) in a temporary folder with symlinked code, its own `data/` and no network; `tests/test_main_page_sources.py` shows how to use it for end-to-end checks of the main page.
- Tests must never write into `data/`: modules that persist state get an autouse fixture in
  `tests/conftest.py` pointing them to `tmp_path` (see `health`).
- `rm` on `data/` is blocked by the Claude Code permission settings even when the user approves; do not
  work around it (no Python `os.remove`), ask the user to run it on the host.
- External HTTP calls need a timeout (the justETF library has none; `exposure._TimeoutSession` adds it).
