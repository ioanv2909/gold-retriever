import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time

from userctx import DATA_ROOT, USERS_FILE, safe_name

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
_ITER = 200_000
SECRET_FILE = os.path.join(DATA_ROOT, "auth_secret")
# fisiere care raman in data/ (comune sau globale); restul se muta la primul admin
SHARED_FILES = {
    "instruments_cache.json", "justetf_cache.json", "quality_cache.json", "quality_status.json",
    "market_context_cache.json", "market_context_status.json", "manual_metrics.json", "ui_prefs.json", "users.json", "auth_secret",
}


def _load():
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("users"), dict):
            return d
    except Exception:
        pass
    return {"users": {}}


def _save(d):
    os.makedirs(DATA_ROOT, exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, USERS_FILE)


def _hash(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt_hex), _ITER).hex()


def has_users():
    return bool(_load()["users"])


def names():
    return sorted(_load()["users"])


def exists(name):
    return str(name).lower() in _load()["users"]


def role(name):
    return (_load()["users"].get(str(name).lower()) or {}).get("role")


def create_user(name, pw, role_="user"):
    """Returneaza (cheie, None) sau (None, cod_eroare)."""
    name = str(name).strip()
    if not _NAME_RE.match(name):
        return None, "name"
    if len(pw or "") < 8 and name != "demo":
        return None, "pwd_short"
    d = _load()
    key = name.lower()
    if key in d["users"]:
        return None, "exists"
    if not d["users"]:
        role_ = "admin"
    salt = secrets.token_hex(16)
    d["users"][key] = {"name": name, "role": role_, "salt": salt, "hash": _hash(pw, salt), "created": time.time()}
    _save(d)
    return key, None


def verify(name, pw):
    rec = _load()["users"].get(str(name).strip().lower())
    if not rec:
        _hash(pw or "", "00" * 16)  # egalizeaza timpul
        return False
    return hmac.compare_digest(_hash(pw or "", rec["salt"]), rec["hash"])


def set_password(name, pw):
    if len(pw or "") < 8 and name != "demo":
        return "pwd_short"
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return "name"
    rec["salt"] = secrets.token_hex(16)
    rec["hash"] = _hash(pw, rec["salt"])
    _save(d)
    return None


def delete_user(name, me, purge=False):
    key = str(name).lower()
    if key == str(me).lower():
        return "self"
    d = _load()
    rec = d["users"].get(key)
    if not rec:
        return "name"
    if rec.get("role") == "admin" and sum(1 for r in d["users"].values() if r.get("role") == "admin") <= 1:
        return "last_admin"
    del d["users"][key]
    _save(d)
    if purge:
        shutil.rmtree(os.path.join(DATA_ROOT, "users", safe_name(key)), ignore_errors=True)
    return None


def migrate_legacy(user_key):
    """Muta fisierele personale din data/ in data/users/<user>/. Returneaza numarul de fisiere."""
    dest = os.path.join(DATA_ROOT, "users", safe_name(user_key))
    os.makedirs(dest, exist_ok=True)
    n = 0
    for fn in os.listdir(DATA_ROOT):
        src = os.path.join(DATA_ROOT, fn)
        if not os.path.isfile(src) or fn in SHARED_FILES or fn.startswith(".") or fn.endswith(".tmp"):
            continue
        shutil.move(src, os.path.join(dest, fn))
        n += 1
    return n


def _secret():
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    except Exception:
        pass
    s = secrets.token_hex(32)
    os.makedirs(DATA_ROOT, exist_ok=True)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(s)
    os.chmod(SECRET_FILE, 0o600)
    return s


def _sig(key, exp, rec):
    msg = f"{key}.{exp}.{rec['hash'][:16]}".encode()
    return hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()


def make_token(name, days=30):
    key = str(name).lower()
    rec = _load()["users"][key]
    exp = int(time.time() + days * 86400)
    return f"{key}.{exp}.{_sig(key, exp, rec)}"


def check_token(token):
    try:
        key, exp, sig = str(token).split(".", 2)
        rec = _load()["users"].get(key)
        if not rec or int(exp) < time.time():
            return None
        return key if hmac.compare_digest(sig, _sig(key, exp, rec)) else None
    except Exception:
        return None


def records():
    d = _load()["users"]
    return [
        {"key": k, "name": v.get("name", k), "role": v.get("role"), "created": v.get("created"), "email": v.get("email")}
        for k, v in sorted(d.items())
    ]


def set_role(name, new_role):
    if new_role not in ("admin", "user"):
        return "name"
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return "name"
    admins = sum(1 for r in d["users"].values() if r.get("role") == "admin")
    if rec.get("role") == "admin" and new_role != "admin" and admins <= 1:
        return "last_admin"
    rec["role"] = new_role
    _save(d)
    return None


def set_email(name, email):
    email = str(email or "").strip()
    if email and (email.count("@") != 1 or " " in email or email.startswith("@") or "." not in email.split("@")[1]):
        return "email"
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return "name"
    if email:
        rec["email"] = email
    else:
        rec.pop("email", None)
    _save(d)
    return None
