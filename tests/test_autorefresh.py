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
