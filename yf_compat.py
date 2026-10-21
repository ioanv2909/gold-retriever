import time

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    YFINANCE_AVAILABLE = False

# La un HTTP 401 (crumb invalid, de obicei la pornire), yfinance incearca o data cealalta strategie de cookie,
# apoi scrie eroarea in log si intoarce date goale, pe care le-am salva in cache ca "fara date" (12 ore - o saptamana).
# Aici reincercam cu un crumb nou, dupa o scurta pauza.
AUTH_RETRIES = 2
AUTH_DELAY = 2.0


def _status(exc):
    return getattr(getattr(exc, "response", None), "status_code", None)


def install_auth_retry(data_cls, http_error, sleep=time.sleep):
    """Inlocuieste data_cls.get_raw_json cu o varianta care reincearca la 401. Idempotent."""
    if getattr(data_cls, "_gr_auth_retry", False):
        return
    original = data_cls.get_raw_json

    def get_raw_json(self, url, params=None, timeout=30):
        for attempt in range(AUTH_RETRIES + 1):
            try:
                return original(self, url, params=params, timeout=timeout)
            except http_error as e:
                if _status(e) != 401 or attempt == AUTH_RETRIES:
                    raise
                print(f"[yf_compat] HTTP 401, new crumb and retry {attempt + 1}/{AUTH_RETRIES}", flush=True)
                lock = getattr(self, "_cookie_lock", None)
                if lock is not None:
                    with lock:
                        self._crumb = None  # se cere unul nou la urmatoarea incercare
                else:
                    self._crumb = None
                sleep(AUTH_DELAY * (attempt + 1))

    data_cls.get_raw_json = get_raw_json
    data_cls._gr_auth_retry = True


def install_health(data_cls, record):
    """Masoara fiecare cerere HTTP yfinance pentru pagina de stare. 404 (simbol fara date) nu e o eroare a serviciului."""
    if getattr(data_cls, "_gr_health", False):
        return
    original = data_cls._make_request

    def _make_request(self, url, *args, **kwargs):
        t0 = time.time()
        try:
            response = original(self, url, *args, **kwargs)
        except Exception as e:
            record("yahoo", False, time.time() - t0, "%s: %s" % (type(e).__name__, e))
            raise
        code = getattr(response, "status_code", 0)
        ok = code < 400 or code == 404
        record("yahoo", ok, time.time() - t0, None if ok else "HTTP %s: %s" % (code, str(url).split("?")[0][-80:]))
        return response

    data_cls._make_request = _make_request
    data_cls._gr_health = True


if YFINANCE_AVAILABLE:
    try:
        import health
        from yfinance._http import HTTPError as _HTTPError
        from yfinance.data import YfData as _YfData
        install_auth_retry(_YfData, _HTTPError)
        install_health(_YfData, health.record)
    except Exception as _e:  # alta versiune de yfinance: fara retry, restul merge ca inainte
        print(f"[yf_compat] auth retry not installed: {_e}", flush=True)
