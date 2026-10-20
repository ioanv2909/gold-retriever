#!/bin/bash
# Backup zilnic pentru data/ (GoldRetriever) pe share-ul Synology montat in /mnt/goldretriever
set -euo pipefail

APP=/DATA/AppData/gold-retriever
SRC=$APP/data
DEST=${DEST:-/mnt/goldretriever}
KEEP=14

alert() {
    python3 "$APP/tools/notify_cli.py" backup "Backup esuat" "$1" backup-fail > /dev/null 2>&1 || true
}

fail() {
    echo "$(date -Is) EROARE: $1" >&2
    alert "$1 ($(hostname), $(date -Is))"
    exit 1
}
trap 'fail "eroare neasteptata la linia $LINENO"' ERR

mountpoint -q "$DEST" || fail "$DEST nu este montat"

umask 077
ts=$(date +%Y-%m-%d_%H%M%S)
out="$DEST/data-$ts.tar.gz"
tmp="$out.part"

# cod 1 = "fisier schimbat in timpul citirii": avertisment, nu eroare
rc=0
tar --exclude='.*.tmp' -czf "$tmp" -C "$(dirname "$SRC")" "$(basename "$SRC")" || rc=$?
if [ "$rc" -gt 1 ]; then
    rm -f "$tmp"
    fail "tar a esuat (cod $rc)"
fi

mv "$tmp" "$out"
tar -tzf "$out" > /dev/null   # verifica ca arhiva se poate citi

# pastreaza ultimele $KEEP arhive
ls -1t "$DEST"/data-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm --

# marcaj pentru detectia "backup lipsa" (verificat de aplicatie in etapa 2)
printf '{"ts": %s, "file": "%s"}\n' "$(date +%s)" "$(basename "$out")" > "$SRC/backup_status.json"
chown --reference="$SRC" "$SRC/backup_status.json" 2>/dev/null || true

echo "$(date -Is) ok $out ($(du -h "$out" | cut -f1))"
