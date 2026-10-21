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
