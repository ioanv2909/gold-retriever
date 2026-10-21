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


if YFINANCE_AVAILABLE:
    try:
        from yfinance._http import HTTPError as _HTTPError
        from yfinance.data import YfData as _YfData
        install_auth_retry(_YfData, _HTTPError)
    except Exception as _e:  # alta versiune de yfinance: fara retry, restul merge ca inainte
        print(f"[yf_compat] auth retry not installed: {_e}", flush=True)
