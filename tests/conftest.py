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
