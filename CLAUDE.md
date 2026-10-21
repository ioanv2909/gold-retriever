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
- Run tests before committing: `.venv/bin/python -m pytest -q` (76 tests, also run in CI).
- Ask before `git push`, `./tools/deploy.sh`, anything with `docker` or `rm`.

## Deploy
`./tools/deploy.sh` rebuilds and restarts the container and writes `build_info.json`
(version = last `v*` tag patch + commits since the tag).

## Layout
- `app.py` main view; `detail_view.py` per-position page; `settings_page.py` settings;
  `core.py` shared logic and `CHART_PERIODS`; `xtb.py`, `xtb_prices.py` XTB import;
  `notify.py`, `notify_ui.py`, `alerts.py` email notifications; `events.py`, `events_ui.py` events calendar; `background.py` refresh loop;
  `auth.py`, `users.py`, `userctx.py` multi-user; `checklist.py` quality/risk scoring; `dividend_score.py` dividend score; `i18n.py` strings.
- Per-user data: `data/users/<name>/`; shared files in `data/`.
- Docs: `docs/` (architecture, data-flow, data-files, backup-and-notifications). `CHANGELOG.md`.
- Backup: `tools/backup-goldretriever.sh` (cron, Synology share), status in `data/backup_status.json`.

## Planned work (in order)
1. Events calendar for held positions (earnings, ex-dividend, payments) with email notice. Done.
2. Dividend score (safety, growth, consistency, yield). Done.
3. Alerts on price/score/concentration using the existing notify system.
4. Analyst targets and estimates from yfinance.
5. Later: exposure by sector/country/currency, ticker comparison, new broker connector.
