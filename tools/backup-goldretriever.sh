#!/bin/bash
# Backup zilnic pentru data/ (GoldRetriever) pe share-ul Synology montat in /mnt/goldretriever.
# Cu o cheie publica GPG in $KEY, arhiva se cripteaza (data-*.tar.gz.gpg) inainte sa ajunga pe share;
# cheia privata nu sta pe server. Fara cheie, arhiva ramane necriptata (data-*.tar.gz) si statusul o marcheaza.
set -euo pipefail

APP=${APP:-/DATA/AppData/gold-retriever}
SRC=${SRC:-$APP/data}
DEST=${DEST:-/mnt/goldretriever}
KEY=${BACKUP_KEY:-$APP/backup-key.asc}
KEEP=14

alert() {
    [ "${BACKUP_NO_ALERT:-}" = 1 ] && return 0
    python3 "$APP/tools/notify_cli.py" backup "Backup esuat" "$1" backup-fail > /dev/null 2>&1 || true
}

fail() {
    echo "$(date -Is) EROARE: $1" >&2
    alert "$1 ($(hostname), $(date -Is))"
    exit 1
}
trap 'fail "eroare neasteptata la linia $LINENO"' ERR

work=""
cleanup() { [ -n "$work" ] && rm -rf "$work"; }
trap cleanup EXIT

if [ "${BACKUP_SKIP_MOUNT_CHECK:-}" != 1 ]; then
    mountpoint -q "$DEST" || fail "$DEST nu este montat"
fi

encrypt=0
if [ -e "$KEY" ]; then
    grep -q "PRIVATE KEY BLOCK" "$KEY" && fail "$KEY contine o cheie privata; pe server trebuie doar cheia publica"
    command -v gpg > /dev/null || fail "gpg nu este instalat, dar exista cheia $KEY"
    encrypt=1
fi

umask 077
ts=$(date +%Y-%m-%d_%H%M%S)
work=$(mktemp -d)
plain="$work/data-$ts.tar.gz"

# cod 1 = "fisier schimbat in timpul citirii": avertisment, nu eroare
rc=0
tar --exclude='.*.tmp' -czf "$plain" -C "$(dirname "$SRC")" "$(basename "$SRC")" || rc=$?
[ "$rc" -gt 1 ] && fail "tar a esuat (cod $rc)"
tar -tzf "$plain" > /dev/null   # verifica arhiva inainte de criptare / copiere

if [ "$encrypt" = 1 ]; then
    out="$DEST/data-$ts.tar.gz.gpg"
    mkdir "$work/gnupg"
    gpg --batch --yes --no-tty --quiet --homedir "$work/gnupg" --trust-model always \
        --recipient-file "$KEY" --compress-algo none --output "$out.part" --encrypt "$plain" \
        || fail "criptarea gpg a esuat"
    # fara cheia privata nu se poate decripta aici; se verifica doar ca fisierul e criptat pentru o cheie publica
    # (gpg iese cu eroare cand nu are cheia privata, chiar daca a citit pachetele)
    packets=$(gpg --batch --no-tty --homedir "$work/gnupg" --list-packets "$out.part" 2>/dev/null || true)
    grep -q "pubkey enc packet" <<< "$packets" || fail "arhiva criptata nu se poate citi"
else
    out="$DEST/data-$ts.tar.gz"
    cp "$plain" "$out.part"
    echo "$(date -Is) ATENTIE: backup necriptat (lipseste $KEY)" >&2
fi
mv "$out.part" "$out"
rm -f "$plain"

# pastreaza ultimele $KEEP arhive (criptate sau nu)
find "$DEST" -maxdepth 1 -type f \( -name 'data-*.tar.gz' -o -name 'data-*.tar.gz.gpg' \) -printf '%T@ %p\n' \
    | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- | xargs -r -d '\n' rm --

# marcaj pentru detectia "backup lipsa" si "backup necriptat" (Setari -> Stare)
enc_json=false
[ "$encrypt" = 1 ] && enc_json=true
printf '{"ts": %s, "file": "%s", "encrypted": %s}\n' "$(date +%s)" "$(basename "$out")" "$enc_json" > "$SRC/backup_status.json"
chown --reference="$SRC" "$SRC/backup_status.json" 2>/dev/null || true

echo "$(date -Is) ok $out ($(du -h "$out" | cut -f1))"
