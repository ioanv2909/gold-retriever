import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collections

import pytest


@pytest.fixture(autouse=True)
def _isolated_health(tmp_path, monkeypatch):
    """Starea serviciilor se scrie in data/; in teste merge intr-un director temporar, cu stare goala."""
    import health
    monkeypatch.setattr(health, "HEALTH_FILE", str(tmp_path / "service_status.json"))
    monkeypatch.setattr(health, "_events", {s: collections.deque(maxlen=health.KEEP) for s in health.SOURCES})
    monkeypatch.setattr(health, "_last", {s: {"ok": None, "fail": None, "error": None} for s in health.SOURCES})
    monkeypatch.setattr(health, "_saved", {"at": 0.0, "loaded": True})


@pytest.fixture(autouse=True)
def _isolated_strategies(tmp_path, monkeypatch):
    """Cache-ul lentilelor de strategie se scrie in data/; in teste merge intr-un director temporar."""
    import strategies
    monkeypatch.setattr(strategies, "STRATEGY_CACHE_FILE", str(tmp_path / "strategy_cache.json"))
    monkeypatch.setattr(strategies, "STRATEGY_STATUS_FILE", str(tmp_path / "strategy_status.json"))
    monkeypatch.setattr(strategies, "fetch_rf", lambda: None)
    import signals
    # fara retea si fara data/users.json in teste
    monkeypatch.setattr(signals, "fetch_news", lambda *a, **kw: [])
    monkeypatch.setattr(signals, "market_context", lambda: {"vix": None, "spx_vs_sma200": None})
    monkeypatch.setattr(signals, "ua_email", lambda: None)
    monkeypatch.setattr(signals, "SEC_TICKERS_FILE", str(tmp_path / "sec_tickers.json"))
    monkeypatch.setattr(strategies, "PROFILE_FILE", str(tmp_path / "strategy_profile.json"))


@pytest.fixture(autouse=True)
def _isolated_privacy(tmp_path, monkeypatch):
    """Setarea de confidentialitate se scrie in data/; in teste merge intr-un director temporar."""
    import privacy
    monkeypatch.setattr(privacy, "PRIVACY_FILE", str(tmp_path / "privacy.json"))


@pytest.fixture(autouse=True)
def _isolated_users(tmp_path, monkeypatch):
    """Conturile se scriu in data/users.json; in teste merg intr-un director temporar, fara blocari ramase."""
    import auth
    import users
    monkeypatch.setattr(users, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(users, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(users, "SECRET_FILE", str(tmp_path / "auth_secret"))
    monkeypatch.setattr(auth, "_fails", {})
    monkeypatch.setattr(auth, "_FAIL_DELAY", 0)


@pytest.fixture(autouse=True)
def _isolated_presence(tmp_path, monkeypatch):
    """Registrul de prezenta se scrie in data/; in teste merge intr-un director temporar, fara limitari ramase."""
    import presence
    monkeypatch.setattr(presence, "PRESENCE_FILE", str(tmp_path / "presence.json"))
    monkeypatch.setattr(presence, "_written", {})


@pytest.fixture(autouse=True)
def _isolated_session_policy(tmp_path, monkeypatch):
    """Limitele si activitatea sesiunilor se scriu in data/; in teste merg intr-un director temporar."""
    import session_policy
    monkeypatch.setattr(session_policy, "POLICY_FILE", str(tmp_path / "session_policy.json"))
    monkeypatch.setattr(session_policy, "ACTIVITY_FILE", str(tmp_path / "session_activity.json"))
    monkeypatch.setattr(session_policy, "_written", {})
    monkeypatch.setattr(session_policy, "_cache", {"key": None, "val": None})


@pytest.fixture(autouse=True)
def _isolated_known_devices(tmp_path, monkeypatch):
    """Dispozitivele cunoscute se scriu in data/; in teste merg intr-un director temporar, fara e-mailuri."""
    import known_devices
    monkeypatch.setattr(known_devices, "DEVICES_FILE", str(tmp_path / "known_devices.json"))
    monkeypatch.setattr(known_devices, "_alerts", {})


@pytest.fixture(autouse=True)
def _isolated_fx(tmp_path, monkeypatch):
    """Ultimele cursuri bune se scriu in data/; in teste merg intr-un director temporar, cu stare goala."""
    import t212_api
    monkeypatch.setattr(t212_api, "FX_LAST_GOOD_FILE", str(tmp_path / "fx_last_good.json"))
    monkeypatch.setattr(t212_api, "_fx_last_good", {})
    monkeypatch.setattr(t212_api, "_fx_saved", {})
    monkeypatch.setattr(t212_api, "_fx_state", {"loaded": False, "failures": 0})


@pytest.fixture(autouse=True)
def _isolated_twofa(tmp_path, monkeypatch):
    """Politica 2FA se scrie in data/; in teste merge intr-un director temporar."""
    import twofa
    monkeypatch.setattr(twofa, "POLICY_FILE", str(tmp_path / "twofa_policy.json"))
