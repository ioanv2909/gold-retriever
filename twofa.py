"""Autentificare in doi pasi: coduri TOTP (RFC 6238: 6 cifre, pas de 30 s, HMAC-SHA1), coduri de rezerva
si politica adminului (data/twofa_policy.json). Secretul si codurile se tin in users.json (vezi users.py);
nimic de aici nu ajunge in log sau in emailuri."""
import base64
import hashlib
import hmac
import io
import os
import re
import secrets
import struct
import time
from urllib.parse import quote

from core import load_json_file, save_json_file
from userctx import DATA_ROOT

ISSUER = "GoldRetriever"
STEP = 30
DIGITS = 6
WINDOW = 1                # se accepta si codul pasului anterior / urmator (ceasuri usor decalate)
RECOVERY_COUNT = 10
PENDING_SECONDS = 5 * 60  # cat asteapta pasul doi dupa o parola corecta
POLICY_FILE = os.path.join(DATA_ROOT, "twofa_policy.json")
POLICIES = ("optional", "admins", "all")
EXEMPT = ("demo",)

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # fara 0/o, 1/l/i


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    s = str(secret).upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret, step):
    mac = hmac.new(_key(secret), struct.pack(">Q", int(step)), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return str(n).zfill(DIGITS)


def normalize(code):
    return re.sub(r"[\s-]", "", str(code or "")).lower()


def match_step(secret, code, now=None, last_step=None):
    """Pasul de timp al codului (in fereastra ±WINDOW) sau None. Un pas deja folosit (<= last_step) e refuzat."""
    code = normalize(code)
    if not re.fullmatch(r"\d{%d}" % DIGITS, code):
        return None
    cur = int((time.time() if now is None else now) // STEP)
    for step in range(cur - WINDOW, cur + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, step), code):
            return step if last_step is None or step > int(last_step) else None
    return None


def provisioning_uri(secret, account):
    label = quote("%s:%s" % (ISSUER, account))
    return "otpauth://totp/%s?secret=%s&issuer=%s&digits=%d&period=%d" % (label, secret, quote(ISSUER), DIGITS, STEP)


def qr_png(uri):
    import segno
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="png", scale=6, border=2)
    return buf.getvalue()


def new_recovery_codes():
    return ["%s-%s" % tuple("".join(secrets.choice(_ALPHABET) for _ in range(5)) for _ in range(2))
            for _ in range(RECOVERY_COUNT)]


def hash_recovery(code, salt):
    return hashlib.sha256((salt + ":" + normalize(code)).encode("utf-8")).hexdigest()


def policy():
    d = load_json_file(POLICY_FILE, {})
    p = d.get("policy") if isinstance(d, dict) else None
    return p if p in POLICIES else "optional"


def save_policy(p):
    if p not in POLICIES:
        return "policy"
    save_json_file(POLICY_FILE, {"policy": p}, raise_errors=True)
    return None


def required(name, role, p=None):
    """2FA obligatoriu pentru acest cont dupa politica adminului (contul demo e scutit)."""
    if not name or str(name).lower() in EXEMPT:
        return False
    p = p or policy()
    return p == "all" or (p == "admins" and role == "admin")
