## Unreleased

- Analysts section on the position page (Yahoo Finance): mean, median, low and high price targets with upside and a range chart, recommendation distribution over the last four months, EPS and revenue estimates (current/next quarter and year) with growth, EPS estimate revisions (vs 30 and 90 days ago, up/down revisions) and the latest rating changes by firm. Replaces the old single-line target block.
- New "Target %" column in the positions table: upside to the analysts' mean target, refreshed with the ratings every 12 hours.
- Position alerts (Settings, Alerts), checked every 15 minutes in the background:
  - price alerts per position (rises to or above / falls to or below a price, in the instrument currency), firing once and re-armable; also addable from the position page;
  - score alerts when the quality, risk or dividend score falls below a threshold or drops by N points from its last peak;
  - concentration alert when a position exceeds a share of the whole portfolio (Trading 212 and XTB together).
  Fired alerts show as a banner on the main page and are emailed to the user if they have an address and an admin enabled "Position alerts" in Notifications.
- Dividend score (X/100) for stocks, on four pillars: safety (payout from earnings and from free cash flow), growth (5-year dividend CAGR), consistency (consecutive years paid, cuts in 10 years) and yield (a yield above 8% lowers the score as a possible trap). Shown as a new "Div. score" column in the positions table and as a Dividend section on the position page, with pillar scores and indicator details.

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

