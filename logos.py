"""Logo-ul fiecarei pozitii, luat de pe site-ul companiei (adresa vine de la Yahoo).

Nu foloseste servicii terte de logo-uri: serverul descarca iconul direct de pe site-ul companiei
(apple-touch-icon / icon / favicon.ico), il micsoreaza la 64x64 PNG si il pastreaza in data/logos/.
Pagina citeste doar cache-ul; descarcarile ruleaza in fundal, deci tabelul nu asteapta reteaua.
Fara logo (ETF-uri fara site, site-uri fara icon): insigna SVG cu initialele, generata local.
"""
import base64
import colorsys
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import socket
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import joblog

DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LOGO_DIR = os.path.join(DATA_ROOT, "logos")
INDEX_FILE = os.path.join(LOGO_DIR, "index.json")
RETRY_MISS_S = 14 * 86400      # pozitiile fara logo se reincearca dupa 14 zile
TIMEOUT_S = 8
MAX_PAGE_BYTES = 1_000_000
MAX_ICON_BYTES = 400_000
SIZE = 64
UA = "Mozilla/5.0 (X11; Linux x86_64) GoldRetriever-logo-fetch"

_lock = threading.Lock()
_inflight: set[str] = set()
_index_cache = {"mtime": None, "data": {}}


# ---------------------------------------------------------------- cache
def _load_index():
    try:
        mtime = os.path.getmtime(INDEX_FILE)
    except OSError:
        return {}
    if _index_cache["mtime"] != mtime:
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                data = json.load(f)
            _index_cache.update(mtime=mtime, data=data if isinstance(data, dict) else {})
        except (OSError, ValueError):
            _index_cache.update(mtime=mtime, data={})
    return _index_cache["data"]


def _save_entry(key, entry):
    with _lock:
        os.makedirs(LOGO_DIR, exist_ok=True)
        data = dict(_load_index())
        data[key] = entry
        tmp = INDEX_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, INDEX_FILE)


def _file_name(key):
    return hashlib.sha1(key.encode()).hexdigest()[:16] + ".png"


# ---------------------------------------------------------------- afisare
def initials(name, ticker):
    words = re.findall(r"[A-Za-z0-9]+", str(name or ""))
    words = [w for w in words if w.lower() not in {"inc", "plc", "ltd", "corp", "the", "co", "sa", "ag", "nv", "se"}]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper()
    return re.sub(r"[^A-Za-z0-9]", "", str(ticker or "?"))[:2].upper() or "?"


def badge_uri(name, ticker):
    """Insigna rotunda cu initiale; culoarea e stabila pentru acelasi ticker."""
    hue = int(hashlib.md5(str(ticker).encode()).hexdigest()[:4], 16) % 360 / 360
    r, g, b = (int(c * 255) for c in colorsys.hls_to_rgb(hue, 0.42, 0.55))
    text = html.escape(initials(name, ticker))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="32" '
           f'fill="#{r:02x}{g:02x}{b:02x}"/><text x="32" y="41" font-family="Arial,sans-serif" font-size="24" '
           f'font-weight="700" fill="#fff" text-anchor="middle">{text}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def logo_uri(ticker, name):
    """Logo din cache (data URI PNG) sau insigna cu initiale. Nu face trafic."""
    entry = _load_index().get(str(ticker))
    if isinstance(entry, dict) and entry.get("file"):
        try:
            with open(os.path.join(LOGO_DIR, entry["file"]), "rb") as f:
                return "data:image/png;base64," + base64.b64encode(f.read()).decode()
        except OSError:
            pass
    return badge_uri(name, ticker)


def needs_fetch(ticker, now=None):
    entry = _load_index().get(str(ticker))
    if not isinstance(entry, dict):
        return True
    if entry.get("file"):
        return False
    return (now or time.time()) - float(entry.get("ts") or 0) > RETRY_MISS_S


# ---------------------------------------------------------------- descarcare
class _IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        if not a.get("href") or not ({"icon", "apple-touch-icon", "apple-touch-icon-precomposed"} & set(rel)):
            return
        sizes = [int(n) for n in re.findall(r"(\d+)x\d+", a.get("sizes", ""))]
        touch = any(r.startswith("apple-touch-icon") for r in rel)
        self.links.append((touch, max(sizes) if sizes else (180 if touch else 0), a["href"], a.get("type", "")))


def icon_candidates(page_html, base_url):
    """URL-urile iconurilor din pagina, cele mai bune primele; SVG-urile sunt ignorate (nu se pot converti)."""
    parser = _IconLinks()
    try:
        parser.feed(page_html)
    except Exception:  # noqa: BLE001 - HTML stricat: folosim ce s-a gasit
        pass
    links = [l for l in parser.links if "svg" not in l[3].lower() and not l[2].lower().split("?")[0].endswith(".svg")]
    links.sort(key=lambda l: (l[0], l[1]), reverse=True)
    urls = [urljoin(base_url, l[2]) for l in links]
    urls.append(urljoin(base_url, "/favicon.ico"))
    seen, out = set(), []
    for u in urls:
        if u not in seen and urlparse(u).scheme in ("http", "https"):
            seen.add(u)
            out.append(u)
    return out


def _public_host(url):
    """Refuza adresele locale/private (site-ul vine din date externe)."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def _get(url, limit):
    import requests
    if not _public_host(url):
        raise ValueError("adresa nepublica")
    with requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": UA}, stream=True, allow_redirects=True) as r:
        if not _public_host(r.url):
            raise ValueError("redirectionare spre adresa nepublica")
        r.raise_for_status()
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > limit:
                raise ValueError("raspuns prea mare")
        return r.url, body, r.headers.get("Content-Type", "")


def to_png(raw):
    """Imaginea (ICO/PNG/JPEG/GIF/WebP) -> PNG 64x64 cu transparenta; None daca nu e imagine utilizabila."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(raw))
        if getattr(img, "format", "") == "ICO":
            sizes = sorted(img.info.get("sizes") or [img.size])
            img.size = sizes[-1]
        img.load()
    except Exception:  # noqa: BLE001 - orice fisier care nu e imagine
        return None
    if img.width < 16 or img.height < 16:
        return None
    img = img.convert("RGBA")
    img.thumbnail((SIZE, SIZE))
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img)
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def website_for(ticker):
    from yahoo import resolve_yahoo_symbol
    import yfinance as yf
    symbol = resolve_yahoo_symbol(ticker)
    info = yf.Ticker(symbol).info or {}
    site = (info.get("website") or "").strip()
    if site and not site.startswith(("http://", "https://")):
        site = "https://" + site
    return site


def fetch_logo(ticker):
    """Cauta logo-ul pozitiei si il salveaza in cache. Intoarce True daca a gasit unul."""
    key = str(ticker)
    try:
        site = website_for(key)
    except Exception:  # noqa: BLE001 - Yahoo indisponibil: reincercam mai tarziu
        site = ""
    found = None
    if site:
        try:
            final_url, page, _ = _get(site, MAX_PAGE_BYTES)
            candidates = icon_candidates(page.decode("utf-8", "replace"), final_url)
        except Exception:  # noqa: BLE001 - site picat: macar /favicon.ico
            candidates = [urljoin(site, "/favicon.ico")]
        for url in candidates[:6]:
            try:
                _, raw, _ = _get(url, MAX_ICON_BYTES)
            except Exception:  # noqa: BLE001
                continue
            png = to_png(raw)
            if png:
                found = png
                break
    if found:
        name = _file_name(key)
        os.makedirs(LOGO_DIR, exist_ok=True)
        with open(os.path.join(LOGO_DIR, name), "wb") as f:
            f.write(found)
        _save_entry(key, {"file": name, "site": site, "ts": time.time()})
        return True
    _save_entry(key, {"file": None, "site": site, "ts": time.time()})
    return False


def _run(tickers):
    try:
        for tk in tickers:
            try:
                fetch_logo(tk)
            finally:
                with _lock:
                    _inflight.discard(tk)
    finally:
        with _lock:
            _inflight.difference_update(tickers)


def prefetch(tickers):
    """Porneste in fundal descarcarea logo-urilor lipsa; nu blocheaza pagina."""
    todo = []
    with _lock:
        for tk in dict.fromkeys(str(t) for t in tickers if t):
            if tk not in _inflight and needs_fetch(tk):
                _inflight.add(tk)
                todo.append(tk)
    if todo:
        threading.Thread(target=joblog.wrap("logos", _run, skip_fast=True), args=(todo,), daemon=True).start()
    return todo
