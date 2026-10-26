import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time

import session_policy
import twofa
from userctx import DATA_ROOT, USERS_FILE, contained_path, safe_name

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
_ITER = 200_000
SECRET_FILE = os.path.join(DATA_ROOT, "auth_secret")
# fisiere care raman in data/ (comune sau globale); restul se muta la primul admin
SHARED_FILES = {
    "instruments_cache.json", "justetf_cache.json", "quality_cache.json", "quality_status.json",
    "market_context_cache.json", "market_context_status.json", "manual_metrics.json", "ui_prefs.json", "users.json", "auth_secret", "presence.json",
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


def create_user(name, pw, role_="user", must_change=False):
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
    if must_change and key != "demo":
        d["users"][key]["must_change"] = True
    _save(d)
    return key, None


def verify(name, pw):
    rec = _load()["users"].get(str(name).strip().lower())
    if not rec:
        _hash(pw or "", "00" * 16)  # egalizeaza timpul
        return False
    return hmac.compare_digest(_hash(pw or "", rec["salt"]), rec["hash"])


def set_password(name, pw, must_change=False):
    """must_change=True cere schimbarea parolei la urmatoarea autentificare (parola data de admin)."""
    if len(pw or "") < 8 and name != "demo":
        return "pwd_short"
    d = _load()
    key = str(name).lower()
    rec = d["users"].get(key)
    if not rec:
        return "name"
    rec["salt"] = secrets.token_hex(16)
    rec["hash"] = _hash(pw, rec["salt"])
    if must_change and key != "demo":
        rec["must_change"] = True
    else:
        rec.pop("must_change", None)
    _save(d)
    return None


def change_password(name, current, new):
    """Schimbarea parolei de catre utilizator: verifica parola curenta, apoi aceleasi reguli ca set_password.
    Returneaza None sau cod_eroare ("bad_current", "pwd_short")."""
    if not verify(name, current):
        return "bad_current"
    return set_password(name, new)


def must_change(name):
    return bool((_load()["users"].get(str(name).lower()) or {}).get("must_change"))


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
        shutil.rmtree(contained_path(os.path.join(DATA_ROOT, "users"), safe_name(key)), ignore_errors=True)
    return None


def migrate_legacy(user_key):
    """Muta fisierele personale din data/ in data/users/<user>/. Returneaza numarul de fisiere."""
    dest = contained_path(os.path.join(DATA_ROOT, "users"), safe_name(user_key))
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
    msg = f"{key}.{exp}.{rec['hash'][:16]}"
    # versiunea intra in semnatura doar dupa prima deconectare fortata, ca token-urile vechi sa ramana valide
    if rec.get("sess_ver"):
        msg += f".{int(rec['sess_ver'])}"
    msg = msg.encode()
    return hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()


def make_token(name, now=None):
    """Cookie de autentificare valabil limita absoluta curenta (session_policy)."""
    key = str(name).lower()
    rec = _load()["users"][key]
    exp = int((now if now is not None else time.time()) + session_policy.max_seconds())
    return f"{key}.{exp}.{_sig(key, exp, rec)}"


def token_exp(token):
    try:
        return int(str(token).split(".", 2)[1])
    except Exception:
        return None


def check_token(token, now=None):
    try:
        key, exp, sig = str(token).split(".", 2)
        rec = _load()["users"].get(key)
        if not rec or session_policy.token_expired(int(exp), now):
            return None
        return key if hmac.compare_digest(sig, _sig(key, exp, rec)) else None
    except Exception:
        return None


def session_version(name):
    return int((_load()["users"].get(str(name).lower()) or {}).get("sess_ver") or 0)


def bump_session(name):
    """Deconectare fortata: token-urile emise pana acum devin invalide, sesiunile deschise ies."""
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return "name"
    rec["sess_ver"] = int(rec.get("sess_ver") or 0) + 1
    _save(d)
    return None


def records():
    d = _load()["users"]
    return [
        {"key": k, "name": v.get("name", k), "role": v.get("role"), "created": v.get("created"), "email": v.get("email"),
         "twofa": bool(v.get("totp_secret"))}
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


def email(name):
    return (_load()["users"].get(str(name).lower()) or {}).get("email")


# --- autentificare in doi pasi (TOTP + coduri de rezerva; vezi twofa.py) ---
_TFA_KEYS = ("totp_secret", "totp_last_step", "recovery", "recovery_salt")


def has_2fa(name):
    return bool((_load()["users"].get(str(name).lower()) or {}).get("totp_secret"))


def recovery_left(name):
    return len((_load()["users"].get(str(name).lower()) or {}).get("recovery") or [])


def _set_recovery(rec):
    codes = twofa.new_recovery_codes()
    rec["recovery_salt"] = secrets.token_hex(16)
    rec["recovery"] = [twofa.hash_recovery(c, rec["recovery_salt"]) for c in codes]
    return codes


def enable_2fa(name, secret, code, now=None):
    """Activeaza 2FA doar daca `code` e corect pentru `secret`. Returneaza (coduri de rezerva, None) sau
    (None, cod_eroare). Token-urile emise pana acum devin invalide (sess_ver)."""
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return None, "name"
    step = twofa.match_step(secret, code, now)
    if step is None:
        return None, "bad_code"
    rec["totp_secret"], rec["totp_last_step"] = secret, step
    codes = _set_recovery(rec)
    rec["sess_ver"] = int(rec.get("sess_ver") or 0) + 1
    _save(d)
    return codes, None


def verify_2fa(name, code, now=None):
    """"totp", "recovery" (codul de rezerva se consuma) sau None. Un cod TOTP nu merge de doua ori."""
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec or not rec.get("totp_secret"):
        return None
    step = twofa.match_step(rec["totp_secret"], code, now, rec.get("totp_last_step"))
    if step is not None:
        rec["totp_last_step"] = step
        _save(d)
        return "totp"
    h = twofa.hash_recovery(code, rec.get("recovery_salt") or "")
    left = rec.get("recovery") or []
    hit = next((x for x in left if hmac.compare_digest(x, h)), None)
    if hit is None:
        return None
    left.remove(hit)
    _save(d)
    return "recovery"


def new_recovery_codes(name):
    """Coduri de rezerva noi (cele vechi nu mai merg). Apelantul verifica inainte parola si un cod."""
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec or not rec.get("totp_secret"):
        return None
    codes = _set_recovery(rec)
    _save(d)
    return codes


def disable_2fa(name):
    """Scoate 2FA (si din terminal, pentru un admin fara alt admin). Sesiunile deschise ies."""
    d = _load()
    rec = d["users"].get(str(name).lower())
    if not rec:
        return "name"
    for k in _TFA_KEYS:
        rec.pop(k, None)
    rec["sess_ver"] = int(rec.get("sess_ver") or 0) + 1
    _save(d)
    return None
