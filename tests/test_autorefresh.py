import json
import os

import autorefresh


def _write(path, fetched_at, mtime):
    path.write_text(json.dumps({"fetched_at": fetched_at, "data": {}}))
    os.utime(path, (mtime, mtime))


def test_setting_defaults_on_and_persists():
    assert autorefresh.enabled() is True
    autorefresh.save_enabled(False)
    assert autorefresh.enabled() is False
    autorefresh.save_enabled(True)
    assert autorefresh.enabled() is True


def test_signature_changes_only_with_new_fetched_at(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "missing.json"
    _write(a, 100, 1000)
    cache = {}
    first = autorefresh.signature(cache, files=(str(a), str(b)))
    assert first == (100, None)
    # rescris cu acelasi fetched_at (salvare partiala): semnatura nu se schimba
    _write(a, 100, 2000)
    assert autorefresh.signature(cache, files=(str(a), str(b))) == first
    _write(a, 200, 3000)
    assert autorefresh.signature(cache, files=(str(a), str(b))) == (200, None)


def test_signature_skips_unchanged_files(tmp_path, monkeypatch):
    a = tmp_path / "a.json"
    _write(a, 100, 1000)
    cache = {}
    autorefresh.signature(cache, files=(str(a),))
    calls = []
    monkeypatch.setattr(autorefresh, "load_json_file", lambda *x: calls.append(x) or {})
    assert autorefresh.signature(cache, files=(str(a),)) == (100,)
    assert calls == []


def test_signature_tolerates_bad_json(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("[1, 2]")
    assert autorefresh.signature({}, files=(str(a),)) == (None,)


def _watch(path, entries, mtime):
    path.write_text(json.dumps(entries))
    os.utime(path, (mtime, mtime))


def test_watchlist_signature_waits_for_the_refresh_to_finish(tmp_path):
    cache_f, status_f = tmp_path / "watchlist_cache.json", tmp_path / "watchlist_status.json"
    status_f.write_text(json.dumps({"in_progress": False}))
    _watch(cache_f, {"AAPL": {"updated": "2026-10-26T10:00:00"}, "MSFT": {"updated": "2026-10-26T10:00:01"}}, 1000)
    c = {}
    sig = lambda: autorefresh.watchlist_signature(c, path=str(cache_f), status_path=str(status_f))
    assert sig() == "2026-10-26T10:00:01"
    # actualizare in curs: fisierul se schimba dupa fiecare simbol, semnatura nu
    status_f.write_text(json.dumps({"in_progress": True}))
    _watch(cache_f, {"AAPL": {"updated": "2026-10-27T10:00:00"}, "MSFT": {"updated": "2026-10-26T10:00:01"}}, 2000)
    assert sig() == "2026-10-26T10:00:01"
    status_f.write_text(json.dumps({"in_progress": False}))
    assert sig() == "2026-10-27T10:00:00"


def test_watchlist_signature_without_files(tmp_path):
    assert autorefresh.watchlist_signature({}, path=str(tmp_path / "a.json"), status_path=str(tmp_path / "b.json")) is None


def test_watchlist_signature_sees_price_only_updates(tmp_path):
    cache_f, status_f = tmp_path / "watchlist_cache.json", tmp_path / "watchlist_status.json"
    _watch(cache_f, {"AAPL": {"updated": "2026-10-27T03:00:00"}}, 1000)
    c = {}
    assert autorefresh.watchlist_signature(c, path=str(cache_f), status_path=str(status_f)) == "2026-10-27T03:00:00"
    _watch(cache_f, {"AAPL": {"updated": "2026-10-27T03:00:00", "price_updated": "2026-10-27T13:15:00"}}, 2000)
    assert autorefresh.watchlist_signature(c, path=str(cache_f), status_path=str(status_f)) == "2026-10-27T13:15:00"
