"""Autentificare prin Tailscale: cine deschide GoldRetriever la adresa Tailscale e recunoscut dupa contul
Tailscale, fara parola (la fel ca in AstroLibrary).

Cum: `tailscale serve` (containerul tailscale, retea host) trimite https://<masina>.<tailnet>.ts.net:8443/ la
http://127.0.0.1:8501/ts-<secret>/ si adauga antetele Tailscale-User-Login / Tailscale-User-Name pentru persoane
(nu pentru dispozitive cu tag). Prefixul secret dovedeste ca cererea a trecut prin `tailscale serve`: proxy-ul
docker arata toti clientii cu aceeasi adresa, deci adresa nu poate dovedi nimic. Middleware-ul ASGI (server.py)
taie prefixul si marcheaza cererea cu un antet intern; pe toate celelalte cereri antetele Tailscale-* si cel intern
se sterg, ca nimeni din reteaua locala sa nu poata pretinde o identitate. Secretul sta in data/ts_secret (600).

Fiecare cont GoldRetriever poate fi legat de un login Tailscale (users.ts_login): de un admin in Setari ->
Utilizatori, sau de persoana in Setari -> Cont, dupa o autentificare cu parola la adresa Tailscale. Deconectarea
la adresa Tailscale pune un cookie care opreste autentificarea automata in acel browser pana la urmatoarea
autentificare cu parola."""
import hmac
import os
import secrets
import time

from userctx import DATA_ROOT

SECRET_FILE = os.path.join(DATA_ROOT, "ts_secret")
HTTPS_PORT = int(os.environ.get("GR_TS_HTTPS_PORT", "8443"))  # 443 e luat de AstroLibrary
LOCAL_PORT = int(os.environ.get("GR_PORT", "8501"))
MARK = b"x-goldretriever-ts"
_TOKEN = secrets.token_hex(16)  # valoarea antetului intern: o stie doar procesul acesta
_DROP = (b"tailscale-user-login", b"tailscale-user-name", b"tailscale-user-profile-pic", MARK)
NO_AUTO_COOKIE = "gr_no_ts"
_cache = {"secret": None, "checked": 0.0}


def secret(create=False):
    try:
        with open(SECRET_FILE, encoding="ascii") as f:
            s = f.read().strip()
        if len(s) >= 24:
            return s
    except OSError:
        pass
    if not create:
        return None
    s = secrets.token_urlsafe(24)
    os.makedirs(DATA_ROOT, exist_ok=True)
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(s)
    _cache.update(secret=s, checked=time.time())
    return s


def rotate_secret():
    """Un secret nou in locul celui vechi (de ex. dupa ce a fost aratat cuiva). Ruta veche a `tailscale serve`
    nu mai e de incredere imediat; comanda noua trebuie rulata pe gazda."""
    try:
        os.remove(SECRET_FILE)
    except OSError:
        pass
    _cache.update(secret=None, checked=0.0)
    return secret(create=True)


def serve_command():
    """Comanda de rulat o data pe gazda (aratata adminului)."""
    s = secret(create=True)
    return f"docker exec tailscale tailscale serve --bg --https={HTTPS_PORT} http://127.0.0.1:{LOCAL_PORT}/ts-{s}"


def _prefix():
    # creat mai tarziu din Setari -> Utilizatori sau de mana: se cauta din nou cel mult o data la 10 s
    if not _cache["secret"] and time.time() - _cache["checked"] > 10:
        _cache.update(secret=secret(), checked=time.time())
    return "/ts-" + _cache["secret"] if _cache["secret"] else None


def _first(value):
    return value.decode("latin-1").split(",")[0].strip()


def rewrite(scope):
    """Scope-ul ASGI vazut de Streamlit: prefixul taiat si cererea marcata, sau antetele de identitate sterse."""
    if scope.get("type") not in ("http", "websocket"):
        return scope
    path = scope.get("path") or "/"
    prefix = _prefix()
    headers = [(k, v) for k, v in scope.get("headers") or [] if k.lower() not in _DROP]
    if prefix and hmac.compare_digest(path[:len(prefix)], prefix) and path[len(prefix):len(prefix) + 1] in ("", "/"):
        raw = dict((k.lower(), v) for k, v in scope.get("headers") or [])
        new = dict(scope)
        new["path"] = path[len(prefix):] or "/"
        new["raw_path"] = new["path"].encode("utf-8")
        # ce vede browserul: hostul ts.net prin https, adresa persoanei din tailnet
        if raw.get(b"x-forwarded-host"):
            headers = [(k, v) for k, v in headers if k.lower() != b"host"] + [(b"host", _first(raw[b"x-forwarded-host"]).encode())]
        if raw.get(b"x-forwarded-for"):
            new["client"] = (_first(raw[b"x-forwarded-for"]), 0)
            headers = [(k, v) for k, v in headers if k.lower() != b"x-forwarded-for"]
        new["scheme"] = ("wss" if scope["type"] == "websocket" else "https")
        for k in (b"tailscale-user-login", b"tailscale-user-name"):
            if raw.get(k):
                headers.append((k, raw[k]))
        headers.append((MARK, _TOKEN.encode()))
        new["headers"] = headers
        return new
    return dict(scope, headers=headers)


class Middleware:
    """Middleware ASGI (vezi docstring-ul modulului)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(rewrite(scope), receive, send)


def _headers():
    try:
        import streamlit as st
        return st.context.headers
    except Exception:
        return {}


def via_tailscale(headers=None):
    h = _headers() if headers is None else headers
    return hmac.compare_digest(str(h.get(MARK.decode()) or ""), _TOKEN)


def identity(headers=None):
    """(login, nume afisat) al persoanei Tailscale din spatele cererii, sau (None, None)."""
    h = _headers() if headers is None else headers
    if not via_tailscale(h):
        return None, None
    login = (h.get("Tailscale-User-Login") or "").strip().lower()
    return (login or None), ((h.get("Tailscale-User-Name") or "").strip() or None)
