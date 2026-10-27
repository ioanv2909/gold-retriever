#!/bin/bash
# Backup zilnic pentru data/ (GoldRetriever) pe share-ul Synology montat in /mnt/goldretriever.
# Cu o cheie publica GPG in $KEY, arhiva se cripteaza (data-*.tar.gz.gpg) inainte sa ajunga pe share;
# cheia privata nu sta pe server. Fara cheie, arhiva ramane necriptata (data-*.tar.gz) si statusul o marcheaza.
# Cu --if-requested (cron de root, la fiecare minut) ruleaza doar daca un admin a cerut backup din
# Setari -> Backup (data/backup_request.json cu "state": "requested"); altfel iese fara sa scrie nimic.
set -euo pipefail

APP=${APP:-/DATA/AppData/gold-retriever}
SRC=${SRC:-$APP/data}
DEST=${DEST:-/mnt/goldretriever}
KEY=${BACKUP_KEY:-$APP/backup-key.asc}
# eticheta optionala adaugata la numele arhivei (data-<ts>-<tag>.tar.gz[.gpg]): BACKUP_TAG sau fisierul $APP/backup-tag
TAG_FILE=${BACKUP_TAG_FILE:-$APP/backup-tag}
KEEP=14
REQ="$SRC/backup_request.json"
requested=0

alert() {
    [ "${BACKUP_NO_ALERT:-}" = 1 ] && return 0
    python3 "$APP/tools/notify_cli.py" backup "Backup esuat" "$1" backup-fail > /dev/null 2>&1 || true
}

# scrie in data/ printr-un fisier nou + mv: root nu urmeaza un symlink lasat acolo de aplicatie
write_data() {
    local tmp
    tmp=$(mktemp "$SRC/.$1.XXXXXX.tmp")
    printf '%s\n' "$2" > "$tmp"
    chown --reference="$SRC" "$tmp" 2>/dev/null || true
    chmod 600 "$tmp"
    mv -f "$tmp" "$SRC/$1"
}

request_state() {
    [ "$requested" = 1 ] || return 0
    write_data backup_request.json "$(printf '{"state": "%s", "ts": %s, "detail": "%s"}' "$1" "$(date +%s)" "$(tr -d '"\\\n' <<< "$2")")"
}

fail() {
    echo "$(date -Is) EROARE: $1" >&2
    request_state failed "$1" || true
    alert "$1 ($(hostname), $(date -Is))"
    exit 1
}
trap 'fail "eroare neasteptata la linia $LINENO"' ERR

work=""
cleanup() { if [ -n "$work" ]; then rm -rf "$work"; fi; }
trap cleanup EXIT

# un singur backup odata (cron-ul de noapte si cererile din aplicatie); lock pe director, fara fisier nou
exec 9< "$SRC"
if [ "${1:-}" = "--if-requested" ]; then
    grep -qs '"state": *"requested"' "$REQ" || exit 0
    flock -n 9 || exit 0
    requested=1
    request_state running ""
else
    flock 9
fi

if [ "${BACKUP_SKIP_MOUNT_CHECK:-}" != 1 ]; then
    mountpoint -q "$DEST" || fail "$DEST nu este montat"
fi

encrypt=0
if [ -e "$KEY" ]; then
    grep -q "PRIVATE KEY BLOCK" "$KEY" && fail "$KEY contine o cheie privata; pe server trebuie doar cheia publica"
    command -v gpg > /dev/null || fail "gpg nu este instalat, dar exista cheia $KEY"
    encrypt=1
fi

tag=${BACKUP_TAG:-}
if [ -z "$tag" ] && [ -e "$TAG_FILE" ]; then
    tag=$(tr -d '[:space:]' < "$TAG_FILE")
fi
if [ -n "$tag" ]; then
    [[ "$tag" =~ ^[A-Za-z0-9_-]{1,32}$ ]] || fail "eticheta backup invalida (doar litere, cifre, _ si -, max 32)"
    tag="-$tag"
fi

umask 077
ts=$(date +%Y-%m-%d_%H%M%S)
work=$(mktemp -d)
plain="$work/data-$ts$tag.tar.gz"

# arhiva se face dintr-o copie: aplicatia scrie in data/ si in timpul backup-ului, iar tar pe folderul
# activ putea prinde un fisier pe jumatate ("file changed as we read it"). Aplicatia inlocuieste fisierele
# prin rename, deci cp citeste fiecare fisier intreg; daca dispare un fisier temporar in timpul copierii,
# copia se reia.
snap="$work/snap"
copied=0
for attempt in 1 2 3; do
    rm -rf "$snap"
    mkdir "$snap"
    if cp -a "$SRC" "$snap/" 2> "$work/cp.err"; then
        copied=1
        break
    fi
    sleep 2
done
[ "$copied" = 1 ] || fail "copierea $SRC a esuat: $(head -c 300 "$work/cp.err")"
find "$snap" -name '.*.tmp' -type f -delete
tar -czf "$plain" -C "$snap" "$(basename "$SRC")" || fail "tar a esuat"
rm -rf "$snap"
tar -tzf "$plain" > /dev/null   # verifica arhiva inainte de criptare / copiere

if [ "$encrypt" = 1 ]; then
    out="$DEST/data-$ts$tag.tar.gz.gpg"
    mkdir "$work/gnupg"
    gpg --batch --yes --no-tty --quiet --homedir "$work/gnupg" --trust-model always \
        --recipient-file "$KEY" --compress-algo none --output "$out.part" --encrypt "$plain" \
        || fail "criptarea gpg a esuat"
    # fara cheia privata nu se poate decripta aici; se verifica doar ca fisierul e criptat pentru o cheie publica
    # (gpg iese cu eroare cand nu are cheia privata, chiar daca a citit pachetele)
    packets=$(gpg --batch --no-tty --homedir "$work/gnupg" --list-packets "$out.part" 2>/dev/null || true)
    grep -q "pubkey enc packet" <<< "$packets" || fail "arhiva criptata nu se poate citi"
else
    out="$DEST/data-$ts$tag.tar.gz"
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
write_data backup_status.json "$(printf '{"ts": %s, "file": "%s", "encrypted": %s}' "$(date +%s)" "$(basename "$out")" "$enc_json")"
request_state done "$(basename "$out")"

echo "$(date -Is) ok $out ($(du -h "$out" | cut -f1))"
