"""Ruleaza app.py cu AppTest intr-un director izolat (cod prin symlink, data/ propriu, fara retea) si
tipareste ce s-a afisat. Folosit de test_main_page_sources.py intr-un proces separat.
argv: repo, workdir, scenariu, [ticker pentru ?detail=]"""
import json
import os
import socket
import sys
import time

repo, work, scenario = sys.argv[1], sys.argv[2], sys.argv[3]
for n in os.listdir(repo):
    if n not in ("data", ".git", ".venv", "tests") and not n.startswith("__") and not os.path.lexists(os.path.join(work, n)):
        os.symlink(os.path.join(repo, n), os.path.join(work, n))
os.makedirs(os.path.join(work, "data"), exist_ok=True)
os.chdir(work)
sys.path.insert(0, work)
sys.path.insert(1, os.path.join(repo, "tests"))


def _no_network(*a, **k):
    raise OSError("network disabled in tests")


socket.socket.connect = _no_network
socket.create_connection = _no_network

import users  # noqa: E402
import xtb  # noqa: E402
from core import ACCOUNT_INFO_CACHE_FILE, PORTFOLIO_CACHE_FILE, save_json_file  # noqa: E402
from test_xtb_parse import make_report  # noqa: E402
from userctx import set_user  # noqa: E402

users.create_user("ana", "parola-lunga-1", "admin")
set_user("ana")
if scenario in ("xtb_only", "t212_empty", "t212_first_error", "both"):
    xtb.import_xtb(xtb.parse_xtb_file(make_report()), "h1")
now = time.time()
if scenario == "t212_empty":
    save_json_file(PORTFOLIO_CACHE_FILE, {"fetched_at": now, "cash": {"free": 10.0, "invested": 0.0, "ppl": 0.0},
                                          "positions": [], "instruments": [], "errors": {}, "stale_errors": {}})
if scenario == "t212_first_error":
    save_json_file(PORTFOLIO_CACHE_FILE, {"fetched_at": now, "cash": None, "positions": None, "instruments": None,
                                          "errors": {"cash": "T212 API: 503", "portfolio": "T212 API: 503"},
                                          "stale_errors": {}})
if scenario in ("both", "t212_only"):
    save_json_file(PORTFOLIO_CACHE_FILE, {
        "fetched_at": now, "cash": {"free": 10.0, "invested": 300.0, "ppl": 60.0, "blocked": 0.0, "result": 0.0},
        "positions": [{"ticker": "AAPL_US_EQ", "quantity": 2.0, "averagePrice": 150.0, "currentPrice": 180.0, "ppl": 60.0,
                       "initialFillDate": "2024-01-02T10:00:00.000+02:00"}],
        "instruments": [{"ticker": "AAPL_US_EQ", "name": "Apple", "currencyCode": "EUR", "isin": "US0378331005", "type": "STOCK"}],
        "errors": {}, "stale_errors": {}})
    save_json_file(ACCOUNT_INFO_CACHE_FILE, {"currencyCode": "EUR", "fetched_at": now})
if scenario == "both":
    from core import WATCHLIST_CACHE_FILE, WATCHLIST_FILE
    save_json_file(WATCHLIST_FILE, [{"symbol": "NVDA"}])
    save_json_file(WATCHLIST_CACHE_FILE, {"NVDA": {"name": "NVIDIA", "price": 123.4, "currency": "USD",
                                                   "updated": "2026-10-27T03:00:00", "price_updated": "2026-10-27T13:15:00"}})
set_user(None)

import auth  # noqa: E402
import background  # noqa: E402

auth.require_login = lambda: (auth.st.session_state.__setitem__("_user", "ana"), "ana")[1]
background.start_background_scheduler = lambda *a, **k: None
from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(os.path.join(work, "app.py"), default_timeout=120)
if len(sys.argv) > 4:
    # "VWCE.DE" -> ?detail=VWCE.DE; "page=settings&tab=weekly" -> parametrii dati
    for part in sys.argv[4].split("&") if "=" in sys.argv[4] else ["detail=" + sys.argv[4]]:
        key, _, value = part.partition("=")
        at.query_params[key] = value
at.run()
print("RESULT " + json.dumps({
    "exception": [e.value for e in at.exception],
    "info": [e.value for e in at.info],
    "error": [e.value for e in at.error],
    "metrics": [[m.label, m.value] for m in at.metric],
    "rows": [len(d.value) for d in at.dataframe],
    "columns": [[str(c) for c in d.value.columns] for d in at.dataframe],
    "pills": [list(p.options) for p in at.get("button_group")],
    "selected": at.session_state["selected_ticker"] if "selected_ticker" in at.session_state else None,
    "checkboxes": [c.label for c in at.checkbox],
    "tabs": [t.label for t in at.tabs],
    "keys": sorted(str(w.key) for kind in ("text_input", "button", "checkbox", "selectbox") for w in at.get(kind) if w.key),
}, ensure_ascii=False))
