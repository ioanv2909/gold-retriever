# Backup and notifications

## Backup

A daily job archives `data/` (users, settings, caches, imported XTB reports) to a
network share. It runs on the host, outside the container, so a container problem
never affects it.

1. Create a shared folder and a dedicated user on the NAS (read/write on that
   folder only) and mount it on the host, for example in `/mnt/goldretriever`:

       //NAS_IP/share /mnt/goldretriever cifs credentials=/etc/.smbcred,iocharset=utf8,uid=1000,gid=1000,file_mode=0600,dir_mode=0700,vers=3.0,_netdev,nofail 0 0

   `/etc/.smbcred` holds `username=...` and `password=...` and must be `chmod 600`, owned by root.

2. Install the script and schedule it as root:

       cp tools/backup-goldretriever.sh /usr/local/sbin/
       chmod 750 /usr/local/sbin/backup-goldretriever.sh
       (crontab -l 2>/dev/null; echo '30 3 * * * /usr/local/sbin/backup-goldretriever.sh >> /var/log/backup-goldretriever.log 2>&1') | crontab -

   Adjust `APP` and `DEST` at the top of the script if your paths differ.

What it does: refuses to run if the share is not mounted (so nothing is written to
the local disk), writes a `.tar.gz` named `data-YYYY-MM-DD_HHMMSS.tar.gz`, verifies
that it can be read, keeps the last 14 archives and writes `data/backup_status.json`
with the time of the last success. Archives contain API keys and password hashes:
keep the share restricted.

Test a failure without touching anything: `DEST=/mnt/does-not-exist /usr/local/sbin/backup-goldretriever.sh`

### Restore

    cd /DATA/AppData/gold-retriever
    docker compose down
    mv data data.broken
    tar -xzf /mnt/goldretriever/data-YYYY-MM-DD_HHMMSS.tar.gz -C .
    chown -R 1000:1000 data
    docker compose up -d

## Notifications

Admins can receive emails when something fails. Configure in Settings, tab
Notifications (admin only): SMTP server, port, security (`starttls`, `ssl`, `none`),
username, an **app password** (not the account password), sender address, which
events are active, and an email address for each admin. Use **Send test email** to
verify. The SMTP password is stored in plain text in `data/mail.json` (file mode 600),
like the Trading 212 keys.

| Event | When |
|---|---|
| Backup | The backup script fails, or the last successful backup is older than 26 hours (only if the status file ever existed) |
| Refresh | Trading 212 or dividends refresh failed 3 times in a row (checked every refresh cycle / 10 minutes) |
| XTB import | A report fails the cash or positions check, has unknown operation types, or cannot be parsed |
| Security | An account is locked after repeated failed logins; a user is created, deleted, gets a new password or role |
| Log errors | A new error pattern appears in the application log (not seen in the last 24 hours); at most one email every 30 minutes |
| Position alerts | A price alert, score alert or concentration alert set by the user fires (sent to the user, not the admins) |
| Calendar | Earnings, ex-dividend or dividend payment dates for held positions within the next N days (sent to the user, not the admins) |

The same alert is not resent more often than the configured interval (6 hours by
default; 24 hours for refresh and backup-missing alerts). User changes are always sent.
Emails never contain keys, passwords or amounts.

Calendar emails go to each user's own address, set in Settings, tab Calendar, together with
the opt-in and how many days ahead (1-30, default 7). The scheduler checks once an hour and
sends one digest with the events not sent before; `events_notified.json` remembers them. The
admin must also enable the Calendar event in Notifications.

The log watchdog (`logwatch.py`) runs inside the app: it reads everything the process writes to
stdout/stderr (including Python logging from Streamlit and yfinance), skips known noise (Yahoo cookie
warnings, HTTP 404 for ETFs without fundamentals, Streamlit context warnings), groups the rest by pattern
and keeps the last 24 hours in `log_problems.json`. Admins see the list in Settings, Notifications. It
cannot report a crashed or stopped container; check `docker ps` / the health endpoint for that.

Position alerts are set per user in Settings, tab Alerts, and checked every 15 minutes:

- **Price:** rises to or above / falls to or below a price, in the instrument currency (GBX shown
  as GBP). Fires once, then waits until re-armed. Can also be added from the position page.
- **Score:** the quality, risk or dividend score of a held position falls below a threshold
  (again only after it rose 5 points above it) or drops by N points from its last peak. The
  first value seen is only a baseline.
- **Concentration:** a position exceeds the maximum share of the portfolio, all accounts
  together; again only after it fell 2 points below the limit.

Fired alerts go to `alert_log.json` (banner on the main page until marked seen) and, if the user
has an address and the admin enabled the Position alerts event, one email per check. `notify_state.json` keeps the send
times and the last SMTP error.

The backup script sends its alert through `tools/notify_cli.py`, which reads the same
settings: `python3 tools/notify_cli.py EVENT "Subject" "Message" [key]`.
