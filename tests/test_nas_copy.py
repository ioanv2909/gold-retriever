import importlib.util
import json
import os
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(monkeypatch, app, dest):
    monkeypatch.setenv("APP", str(app))
    monkeypatch.setenv("DEST", str(dest))
    spec = importlib.util.spec_from_file_location("nas_copy", os.path.join(ROOT, "tools", "nas_copy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def app(tmp_path):
    a = tmp_path / "app"
    a.mkdir()
    run = lambda *c: subprocess.run(["git", "-C", str(a), *c], check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (a / "app.py").write_text("print(1)\n")
    run("add", "app.py")
    run("commit", "-q", "-m", "v0.4.0: first")
    run("tag", "v0.4.0")
    (a / "RESTORE-CASAOS.local.md").write_text("# restore\n")
    (a / "docker-compose.override.yml").write_text("services: {}\n")
    (a / "backup-key.asc").write_text("-----BEGIN PGP PUBLIC KEY BLOCK-----\n")
    (a / "backup-tag").write_text("tag1\n")
    (a / "data").mkdir()
    return a


def test_copies_procedure_bundle_and_config(monkeypatch, app, tmp_path):
    dest = tmp_path / "nas"
    dest.mkdir()
    m = _load(monkeypatch, app, dest)
    out = m.run(check_mount=False)
    assert (dest / "RESTORE-CASAOS.md").read_text() == "# restore\n"
    for n in ("docker-compose.override.yml", "backup-key.asc", "backup-tag"):
        assert (dest / "config" / n).exists()
    bundle = dest / "code" / "gold-retriever.bundle"
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bundle), str(clone)], check=True, capture_output=True)
    tags = subprocess.run(["git", "-C", str(clone), "tag"], check=True, capture_output=True, text=True).stdout
    assert "v0.4.0" in tags and (clone / "app.py").exists()
    last = json.loads((dest / "LAST_COPY.json").read_text())
    assert last["error"] is None and "v0.4.0: first" in last["code"] and out["copied_files"] == 5
    # a doua rulare nu mai copiaza nimic (fisiere identice)
    assert m.run(check_mount=False)["copied_files"] == 0


def test_refuses_unmounted_share_and_private_key(monkeypatch, app, tmp_path):
    dest = tmp_path / "nas"
    dest.mkdir()
    m = _load(monkeypatch, app, dest)
    with pytest.raises(RuntimeError, match="not mounted"):
        m.run(check_mount=True)
    (app / "backup-key.asc").write_text("-----BEGIN PGP PRIVATE KEY BLOCK-----\n")
    with pytest.raises(RuntimeError, match="private key"):
        m.run(check_mount=False)
    assert not (dest / "config" / "backup-key.asc").exists()


def test_main_writes_status_for_the_status_page(monkeypatch, app, tmp_path):
    dest = tmp_path / "nas"
    dest.mkdir()
    m = _load(monkeypatch, app, dest)
    monkeypatch.setenv("NAS_COPY_SKIP_MOUNT_CHECK", "1")
    assert m.main() == 0
    ok = json.loads((app / "data" / "nas_copy_status.json").read_text())
    assert ok["ok_ts"] and ok["fail_ts"] is None
    monkeypatch.setenv("NAS_COPY_SKIP_MOUNT_CHECK", "0")
    assert m.main() == 1
    bad = json.loads((app / "data" / "nas_copy_status.json").read_text())
    assert bad["ok_ts"] == ok["ok_ts"] and bad["fail_ts"] and "not mounted" in bad["error"]


def test_status_row_levels(monkeypatch, tmp_path):
    import health_ui
    import notify
    monkeypatch.setattr(notify, "DATA_ROOT", str(tmp_path))
    f = tmp_path / "nas_copy_status.json"

    def level():
        return list(health_ui._nas_copy_row().values())[1]

    gray = level()
    f.write_text(json.dumps({"ok_ts": time.time(), "fail_ts": None}))
    green = level()
    f.write_text(json.dumps({"ok_ts": time.time() - 30 * 3600, "fail_ts": None}))
    yellow = level()
    f.write_text(json.dumps({"ok_ts": time.time() - 3600, "fail_ts": time.time(), "error": "x"}))
    red = level()
    assert len({gray, green, yellow, red}) == 4
