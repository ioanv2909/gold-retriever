#!/usr/bin/env python3
"""Copia de noapte pe share-ul GoldRetriever de pe NAS (/mnt/goldretriever), separat de Kopia si de GitHub:
- RESTORE-CASAOS.md: procedura de restaurare (sursa: RESTORE-CASAOS.local.md, git-ignored);
- code/gold-retriever.bundle: tot istoricul git, cu tag-urile (versiunea se calculeaza din ele);
- config/: docker-compose.override.yml, backup-key.asc (cheia PUBLICA), backup-tag (fisierele git-ignored);
- LAST_COPY.json: cand si ce s-a copiat.
Arhivele data-*.tar.gz[.gpg] le face scriptul de backup (root); aici nu se ating.
Ruleaza ca ioanv (uid 1000), din crontab:
    0 4 * * * /usr/bin/python3 /DATA/AppData/gold-retriever/tools/nas_copy.py >> /home/ioanv/goldretriever-nas-copy.log 2>&1
Starea ultimei rulari: data/nas_copy_status.json (Setari -> Stare -> "Copie NAS"). Doar biblioteca standard."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

APP = os.environ.get("APP", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.environ.get("DEST", "/mnt/goldretriever")
STATUS_FILE = os.path.join(APP, "data", "nas_copy_status.json")
RESTORE_SRC = "RESTORE-CASAOS.local.md"
CONFIG_FILES = ("docker-compose.override.yml", "backup-key.asc", "backup-tag")


def _write_json(path, data, mode=0o600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="." + os.path.basename(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass  # share CIFS: drepturile vin din optiunile de montare (file_mode=0600)
    os.replace(tmp, path)


def _copy(src, dst):
    """Copiaza doar daca difera (marime sau continut); intoarce numarul de octeti copiati."""
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        with open(src, "rb") as a, open(dst, "rb") as b:
            if a.read() == b.read():
                return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst + ".part")
    os.replace(dst + ".part", dst)
    return os.path.getsize(dst)


def _git(*args):
    return subprocess.run(["git", "-C", APP, *args], check=True, capture_output=True, text=True, timeout=300).stdout.strip()


def run(check_mount=True):
    t0 = time.time()
    if check_mount and not os.path.ismount(DEST):
        raise RuntimeError(f"{DEST} is not mounted")
    src = os.path.join(APP, RESTORE_SRC)
    if not os.path.exists(src):
        raise RuntimeError(f"{src} is missing")
    if os.path.exists(os.path.join(APP, "backup-key.asc")):
        with open(os.path.join(APP, "backup-key.asc"), encoding="utf-8", errors="replace") as f:
            if "PRIVATE KEY BLOCK" in f.read():
                raise RuntimeError("backup-key.asc contains a private key; it must not leave the server")
    copied = _copy(src, os.path.join(DEST, "RESTORE-CASAOS.md"))
    files = 1 if copied else 0
    for name in CONFIG_FILES:
        p = os.path.join(APP, name)
        if os.path.exists(p):
            n = _copy(p, os.path.join(DEST, "config", name))
            copied += n
            files += 1 if n else 0
    os.makedirs(os.path.join(DEST, "code"), exist_ok=True)
    bundle = os.path.join(DEST, "code", "gold-retriever.bundle")
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, "gold-retriever.bundle")
        _git("bundle", "create", local, "--all")
        _git("bundle", "verify", local)
        n = _copy(local, bundle)
        copied += n
        files += 1 if n else 0
    code = _git("log", "-1", "--format=%h %s")
    out = {"ok_ts": time.time(), "dest": DEST, "code": code, "copied_files": files,
           "copied_mb": round(copied / 1024 / 1024, 2), "seconds": round(time.time() - t0, 1), "error": None}
    _write_json(os.path.join(DEST, "LAST_COPY.json"), out)
    return out


def main():
    try:
        out = run(check_mount=os.environ.get("NAS_COPY_SKIP_MOUNT_CHECK") != "1")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
        prev = {}
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            pass
        _write_json(STATUS_FILE, {"ok_ts": prev.get("ok_ts"), "fail_ts": time.time(), "error": err})
        print(time.strftime("%Y-%m-%dT%H:%M:%S"), "ERROR", err, flush=True)
        return 1
    _write_json(STATUS_FILE, dict(out, fail_ts=None))
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), "ok", json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
