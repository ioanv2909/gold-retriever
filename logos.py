"""Logo-ul fiecarei pozitii.

Ordinea surselor: 1) baza de logo-uri Financial Modeling Prep, dupa simbolul Yahoo (serviciu public, fara cont;
vede doar simbolul, o data pe simbol); 2) iconul de pe site-ul companiei (adresa vine de la Yahoo:
apple-touch-icon / icon / favicon.ico); 3) pentru fonduri, site-ul emitentului. Imaginea e micsorata la
64x64 PNG si pastrata in data/logos/.
Pagina citeste doar cache-ul; descarcarile ruleaza in fundal, deci tabelul nu asteapta reteaua.
ETF-urile primesc logo-ul emitentului (iShares, Vanguard, Xtrackers...), recunoscut din familia fondului
data de Yahoo si din numele pozitiei; site-ul emitentului vine dintr-o lista fixa (ISSUERS).
Un site se descarca o singura data (cheia "site:<domeniu>"), refolosit de toate pozitiile lui.
Fara logo (site-uri fara icon, emitent necunoscut): insigna SVG cu initialele, generata local.
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
VERSION = 4        # intrarile FARA logo din versiuni mai vechi se reincearca imediat
LOGO_VERSION = 3   # logo-urile gasite inainte de aceasta versiune se refac
FMP_URL = "https://financialmodelingprep.com/image-stock/{}.png"

# Emitenti de ETF/ETC: (tipar in familia fondului / nume, site oficial). Ordinea conteaza: primul tipar gasit.
ISSUERS = [
    (r"\bishares\b", "https://www.ishares.com"),
    (r"\bvanguard\b", "https://www.vanguard.com"),
    (r"\bx-?trackers\b|\bdws\b", "https://etf.dws.com"),
    (r"\bspdr\b|\bstate street\b", "https://www.ssga.com"),
    (r"\bamundi\b|\blyxor\b", "https://www.amundietf.com"),
    (r"\binvesco\b|\bpowershares\b", "https://www.invesco.com"),
    (r"\bwisdomtree\b", "https://www.wisdomtree.eu"),
    (r"\bvaneck\b|\bmarket vectors\b", "https://www.vaneck.com"),
    (r"\bglobal x\b", "https://www.globalxetfs.eu"),
    (r"\bhsbc\b", "https://www.hsbc.com"),
    (r"\bubs\b", "https://www.ubs.com"),
    (r"\bj\.?p\.? ?morgan\b|\bjpm\b", "https://am.jpmorgan.com"),
    (r"\bfranklin\b", "https://www.franklintempleton.com"),
    (r"\bl&g\b|\blegal (?:&|and) general\b", "https://www.lgim.com"),
    (r"\bfidelity\b", "https://www.fidelity.com"),
    (r"\bfirst trust\b", "https://www.ftglobalportfolios.com"),
    (r"\bgoldman sachs\b", "https://am.gs.com"),
    (r"\bbnp paribas\b", "https://www.bnpparibas-am.com"),
    (r"\bdeka\b", "https://www.deka.de"),
    (r"\bhanetf\b", "https://www.hanetf.com"),
    (r"\bossiam\b", "https://www.ossiam.com"),
    (r"\btabula\b", "https://www.tabulaim.com"),
    (r"\b21shares\b", "https://www.21shares.com"),
    (r"\bcoinshares\b", "https://coinshares.com"),
    (r"\bboost\b", "https://www.wisdomtree.eu"),
    (r"\bschwab\b", "https://www.schwab.com"),
    (r"\bark\b", "https://www.ark-funds.com"),
]

# Rezerva pentru fonduri cand nici simbolul fondului, nici site-ul emitentului nu dau logo:
# logo-ul companiei-mama listate, din aceeasi baza FMP (site emitent -> simbol bursier).
ISSUER_FMP = {
    "https://www.ishares.com": "BLK", "https://www.ssga.com": "STT", "https://www.invesco.com": "IVZ",
    "https://www.wisdomtree.eu": "WT", "https://www.amundietf.com": "AMUN.PA", "https://www.hsbc.com": "HSBA.L",
    "https://www.ubs.com": "UBSG.SW", "https://am.jpmorgan.com": "JPM", "https://www.franklintempleton.com": "BEN",
    "https://www.lgim.com": "LGEN.L", "https://am.gs.com": "GS", "https://www.bnpparibas-am.com": "BNP.PA",
    "https://etf.dws.com": "DWS.DE", "https://www.schwab.com": "SCHW",
}

_lock = threading.Lock()
_inflight: set[str] = set()
_index_cache = {"mtime": None, "data": {}}


# ---------------------------------------------------------------- cache
def _load_index():
    try:
        mtime = os.stat(INDEX_FILE).st_mtime_ns
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
        # scrierile din aceeasi clipa pot avea acelasi mtime: cache-ul se actualizeaza direct
        _index_cache.update(mtime=os.stat(INDEX_FILE).st_mtime_ns, data=data)


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
    version = int(entry.get("v") or 1)
    if entry.get("file"):
        return version < LOGO_VERSION
    if version < VERSION:
        return True
    return (now or time.time()) - float(entry.get("ts") or 0) > RETRY_MISS_S


def issuer_site(*texts):
    """Site-ul emitentului unui fond, dupa familia fondului / nume; "" daca nu e recunoscut."""
    text = " ".join(str(t or "") for t in texts).lower()
    for pattern, site in ISSUERS:
        if re.search(pattern, text):
            return site
    return ""


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


def yahoo_symbol(ticker):
    from yahoo import resolve_yahoo_symbol
    return resolve_yahoo_symbol(ticker)


def yahoo_profile(symbol):
    """(site, text despre fond, e_fond) de la Yahoo."""
    import yfinance as yf
    info = yf.Ticker(symbol).info or {}
    site = (info.get("website") or "").strip()
    if site and not site.startswith(("http://", "https://")):
        site = "https://" + site
    text = " ".join(str(info.get(k) or "") for k in ("fundFamily", "longName", "shortName"))
    return site, text, info.get("quoteType") in ("ETF", "MUTUALFUND")


def choose_site(ticker, name, profile):
    """Fondurile (sau pozitiile fara site) primesc site-ul emitentului; restul, site-ul companiei."""
    site, text, is_fund = profile
    issuer = issuer_site(text, name)
    if issuer and (is_fund or not site):
        return issuer
    return site


def fmp_logo(symbol):
    """Logo din baza Financial Modeling Prep dupa simbolul Yahoo; None daca lipseste."""
    if not symbol or not re.fullmatch(r"[A-Za-z0-9.\-^=]{1,20}", symbol):
        return None
    try:
        _, raw, _ = _get(FMP_URL.format(symbol.upper()), MAX_ICON_BYTES)
    except Exception:  # noqa: BLE001 - 404 / retea: trecem la urmatoarea sursa
        return None
    return to_png(raw)


def _site_key(site):
    return "site:" + (urlparse(site).hostname or site).lower().removeprefix("www.")


def _download_icon(site):
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
            return png
    return None


def _store(key, png):
    file_name = _file_name(key)
    os.makedirs(LOGO_DIR, exist_ok=True)
    with open(os.path.join(LOGO_DIR, file_name), "wb") as f:
        f.write(png)
    return file_name


def fetch_logo(ticker, name=""):
    """Cauta logo-ul pozitiei si il salveaza in cache. Intoarce True daca a gasit unul."""
    key = str(ticker)
    now = time.time()
    try:
        symbol = yahoo_symbol(key)
    except Exception:  # noqa: BLE001
        symbol = ""
    png = fmp_logo(symbol)
    if png:
        _save_entry(key, {"file": _store("fmp:" + symbol.upper(), png), "source": "fmp", "symbol": symbol, "ts": now, "v": VERSION})
        return True
    try:
        profile = yahoo_profile(symbol) if symbol else ("", "", False)
    except Exception:  # noqa: BLE001 - Yahoo indisponibil: macar emitentul dupa nume
        profile = ("", "", False)
    site = choose_site(key, name, profile)
    if not site:
        _save_entry(key, {"file": None, "site": "", "symbol": symbol, "ts": now, "v": VERSION})
        return False
    skey = _site_key(site)
    cached = _load_index().get(skey)
    if (isinstance(cached, dict) and int(cached.get("v") or 1) >= VERSION
            and (cached.get("file") or now - float(cached.get("ts") or 0) < RETRY_MISS_S)):
        _save_entry(key, {"file": cached.get("file"), "source": "site", "site": site, "symbol": symbol, "ts": now, "v": VERSION})
        return bool(cached.get("file"))
    png = _download_icon(site) or fmp_logo(ISSUER_FMP.get(site, ""))
    file_name = _store(skey, png) if png else None
    _save_entry(skey, {"file": file_name, "site": site, "ts": now, "v": VERSION})
    _save_entry(key, {"file": file_name, "source": "site", "site": site, "symbol": symbol, "ts": now, "v": VERSION})
    return bool(file_name)


def _run(items):
    tickers = [tk for tk, _ in items]
    try:
        for tk, name in items:
            try:
                fetch_logo(tk, name)
            finally:
                with _lock:
                    _inflight.discard(tk)
    finally:
        with _lock:
            _inflight.difference_update(tickers)


def prefetch(items):
    """Porneste in fundal descarcarea logo-urilor lipsa; nu blocheaza pagina. items: (ticker, nume) sau ticker."""
    todo = []
    with _lock:
        pairs = [(str(i[0]), str(i[1] or "")) if isinstance(i, (tuple, list)) else (str(i), "") for i in items if i]
        for tk, name in dict(pairs).items():
            if tk and tk not in _inflight and needs_fetch(tk):
                _inflight.add(tk)
                todo.append((tk, name))
    if todo:
        threading.Thread(target=joblog.wrap("logos", _run, skip_fast=True), args=(todo,), daemon=True).start()
    return todo
