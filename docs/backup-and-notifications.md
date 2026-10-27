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
the local disk), builds `data-YYYY-MM-DD_HHMMSS.tar.gz` in a private temporary folder,
verifies that it can be read, encrypts it (see below) and copies it to the share, keeps the
last 14 archives and writes `data/backup_status.json` with the time of the last success
and whether it was encrypted. Archives contain API keys, the SMTP password, password
hashes and 2FA secrets.

3. Encrypt the archives (recommended). Create a GPG key pair **on your own computer, not on
   the server**, and keep the private key (and its passphrase) somewhere safe, for example in
   a password manager: without it the backups cannot be restored.

       gpg --quick-gen-key "GoldRetriever backup" future-default default never
       gpg --armor --export "GoldRetriever backup" > backup-key.asc
       gpg --armor --export-secret-keys "GoldRetriever backup" > goldretriever-backup-PRIVATE.asc   # keep offline

   Copy only `backup-key.asc` (the public key) to the server as
   `/DATA/AppData/gold-retriever/backup-key.asc` (git-ignored; another path can be given with
   `BACKUP_KEY=`). From the next run the archives are `data-*.tar.gz.gpg`. The script refuses
   a private key in that file. Without the file the archive stays unencrypted and Settings >
   Status shows the backup as "Not encrypted". Older unencrypted archives on the share are
   removed by the 14-archive rotation.

Optional tag in the archive name: put a short label (letters, digits, `_`, `-`, at most 32) in
`/DATA/AppData/gold-retriever/backup-tag` (git-ignored) or set `BACKUP_TAG=`; archives are then named
`data-YYYY-MM-DD_HHMMSS-<tag>.tar.gz[.gpg]`. Rotation and the status page work with or without it.
The name is visible on the share and in the log, so do not put secrets in it.

Test a failure without touching anything: `DEST=/mnt/does-not-exist /usr/local/sbin/backup-goldretriever.sh`

### Restore

    cd /DATA/AppData/gold-retriever
    docker compose down
    mv data data.broken
    # encrypted archive: on a machine with the private key (or import it temporarily)
    gpg --decrypt /mnt/goldretriever/data-YYYY-MM-DD_HHMMSS.tar.gz.gpg | tar -xz -C .
    # unencrypted archive
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
| App not responding | The host watchdog's health check failed twice in a row (and once when the app is back) |
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

### Host watchdog

`tools/uptime_check.py` (standard library only) checks `http://localhost:8501/_stcore/health`. Two
failed checks in a row send one "App not responding" email to the admins; the first good check after
that sends "App is responding again". Enable the "App not responding" event in Notifications. Install it
in the crontab of the user that owns `data/` (uid 1000):

```
*/5 * * * * /usr/bin/python3 /DATA/AppData/gold-retriever/tools/uptime_check.py >> /home/ioanv/uptime-goldretriever.log 2>&1
```

Its last result is in `data/uptime_status.json` and on the Status page ("Host watchdog"), which turns
yellow if the cron job stops running.

Settings, tab Status (admin) shows the state of Yahoo Finance, justETF, Trading 212, SMTP and the
backup, and of every background job, with a green / yellow / red / gray indicator. "Test now" makes one
real request to each service; for SMTP it only connects and logs in.

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
