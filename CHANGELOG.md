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

