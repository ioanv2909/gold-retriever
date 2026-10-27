import os
import shutil
import subprocess
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "backup-goldretriever.sh")

pytestmark = pytest.mark.skipif(not shutil.which("gpg"), reason="gpg missing")


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "app" / "data"
    src.mkdir(parents=True)
    (src / "users.json").write_text('{"users": {}}')
    (src / ".x.json.123.tmp").write_text("partial")
    dest = tmp_path / "nas"
    dest.mkdir()
    return {"src": src, "dest": dest, "tmp": tmp_path,
            "env": dict(os.environ, APP=str(tmp_path / "app"), SRC=str(src), DEST=str(dest),
                        BACKUP_KEY=str(tmp_path / "app" / "backup-key.asc"),
                        BACKUP_SKIP_MOUNT_CHECK="1", BACKUP_NO_ALERT="1")}


def _run(e):
    return subprocess.run(["bash", SCRIPT], env=e["env"], capture_output=True, text=True, timeout=60)


@pytest.fixture
def gpg_key(env):
    home = env["tmp"] / "g"
    home.mkdir(mode=0o700)
    g = ["gpg", "--batch", "--homedir", str(home)]
    subprocess.run(g + ["--passphrase", "", "--quick-gen-key", "test <t@example.invalid>", "future-default",
                        "default", "never"], check=True, capture_output=True, timeout=60)
    pub = subprocess.run(g + ["--armor", "--export"], check=True, capture_output=True).stdout
    with open(env["env"]["BACKUP_KEY"], "wb") as f:
        f.write(pub)
    yield g
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"], capture_output=True)


def test_encrypted_backup_can_be_restored_with_the_private_key(env, gpg_key):
    r = _run(env)
    assert r.returncode == 0, r.stderr
    files = os.listdir(env["dest"])
    assert len(files) == 1 and files[0].endswith(".tar.gz.gpg")
    enc = env["dest"] / files[0]
    assert b"users.json" not in enc.read_bytes()
    out = env["tmp"] / "restored.tar.gz"
    subprocess.run(gpg_key + ["--output", str(out), "--decrypt", str(enc)], check=True, capture_output=True)
    with tarfile.open(out) as t:
        names = t.getnames()
    assert "data/users.json" in names and not any(n.endswith(".tmp") for n in names)
    status = (env["src"] / "backup_status.json").read_text()
    assert '"encrypted": true' in status and files[0] in status


def test_without_key_the_backup_is_plain_and_marked(env):
    r = _run(env)
    assert r.returncode == 0, r.stderr
    assert "necriptat" in r.stderr
    files = os.listdir(env["dest"])
    assert len(files) == 1 and files[0].endswith(".tar.gz")
    assert '"encrypted": false' in (env["src"] / "backup_status.json").read_text()


def test_private_key_on_the_server_is_refused(env):
    with open(env["env"]["BACKUP_KEY"], "w") as f:
        f.write("-----BEGIN PGP PRIVATE KEY BLOCK-----\nxx\n")
    r = _run(env)
    assert r.returncode == 1 and "cheie privata" in r.stderr
    assert os.listdir(env["dest"]) == []


def test_no_plaintext_left_behind_and_retention(env, gpg_key):
    for i in range(16):
        p = env["dest"] / ("data-2026-01-%02d_000000.tar.gz" % (i + 1))
        p.write_text("old")
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))
    assert _run(env).returncode == 0
    files = sorted(os.listdir(env["dest"]))
    assert len(files) == 14 and any(f.endswith(".gpg") for f in files)
    assert "data-2026-01-01_000000.tar.gz" not in files and not any(f.endswith(".part") for f in files)


def test_unmounted_share_fails(env):
    env["env"].pop("BACKUP_SKIP_MOUNT_CHECK")
    r = _run(env)
    assert r.returncode == 1 and "nu este montat" in r.stderr


@pytest.mark.parametrize("status,level", [
    ({"encrypted": True}, "🟢"), ({"encrypted": False}, "🟡"), ({}, "🟡")])
def test_status_page_flags_plain_backups(tmp_path, monkeypatch, status, level):
    import json
    import time
    import alerts
    import health_ui
    p = tmp_path / "backup_status.json"
    p.write_text(json.dumps(dict(status, ts=time.time() - 60)))
    monkeypatch.setattr(alerts, "BACKUP_STATUS_FILE", str(p))
    row = health_ui._backup_row()
    assert list(row.values())[1].startswith(level)


def test_tag_from_file_is_added_before_the_extension(env):
    (env["tmp"] / "app" / "backup-tag").write_text("2xAB\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    files = os.listdir(env["dest"])
    assert len(files) == 1 and files[0].startswith("data-") and files[0].endswith("-2xAB.tar.gz")


def test_tag_env_overrides_file_and_bad_tag_fails(env):
    (env["tmp"] / "app" / "backup-tag").write_text("fromfile")
    env["env"]["BACKUP_TAG"] = "fromenv"
    assert _run(env).returncode == 0
    assert os.listdir(env["dest"])[0].endswith("-fromenv.tar.gz")
    env["env"]["BACKUP_TAG"] = "../x"
    r = _run(env)
    assert r.returncode != 0 and "eticheta" in r.stderr


def _run_req(e):
    return subprocess.run(["bash", SCRIPT, "--if-requested"], env=e["env"], capture_output=True, text=True, timeout=60)


def test_if_requested_does_nothing_without_a_request(env):
    r = _run_req(env)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert os.listdir(env["dest"]) == []
    assert not (env["src"] / "backup_status.json").exists()


def test_if_requested_runs_and_reports_done(env):
    import json
    (env["src"] / "backup_request.json").write_text('{"state": "requested", "ts": 1, "by": "admin"}')
    r = _run_req(env)
    assert r.returncode == 0, r.stderr
    files = os.listdir(env["dest"])
    assert len(files) == 1
    req = json.loads((env["src"] / "backup_request.json").read_text())
    assert req["state"] == "done" and req["detail"] == files[0]
    # a doua rulare nu mai face nimic: cererea a fost preluata
    assert _run_req(env).returncode == 0 and len(os.listdir(env["dest"])) == 1


def test_if_requested_reports_failure(env):
    import json
    (env["src"] / "backup_request.json").write_text('{"state": "requested", "ts": 1}')
    env["env"]["BACKUP_TAG"] = "bad tag"
    assert _run_req(env).returncode != 0
    req = json.loads((env["src"] / "backup_request.json").read_text())
    assert req["state"] == "failed" and "eticheta" in req["detail"]


def test_status_file_replaces_a_symlink_instead_of_following_it(env):
    victim = env["tmp"] / "victim"
    victim.write_text("keep")
    os.symlink(victim, env["src"] / "backup_status.json")
    assert _run(env).returncode == 0
    assert victim.read_text() == "keep"
    assert not os.path.islink(env["src"] / "backup_status.json")


def test_backup_of_a_folder_being_written_is_consistent(env):
    """Aplicatia scrie in data/ in timpul backup-ului (rename atomic + fisiere temporare care apar si dispar)."""
    import json
    import sys
    import time
    big = env["src"] / "portfolio_cache.json"
    big.write_text(json.dumps({"n": 0, "pad": "x" * 2_000_000}))
    writer = subprocess.Popen([sys.executable, "-c", """
import json, os, sys, time
d = sys.argv[1]
end = time.time() + 20
i = 0
while time.time() < end:
    i += 1
    tmp = os.path.join(d, ".portfolio_cache.json.%d.tmp" % i)
    with open(tmp, "w") as f:
        json.dump({"n": i, "pad": "x" * 2_000_000}, f)
    os.replace(tmp, os.path.join(d, "portfolio_cache.json"))
    open(os.path.join(d, ".other.%d.tmp" % i), "w").close()
    os.remove(os.path.join(d, ".other.%d.tmp" % i))
""", str(env["src"])])
    try:
        time.sleep(0.5)
        r = _run(env)
    finally:
        writer.kill()
        writer.wait()
    assert r.returncode == 0, r.stderr
    assert "changed as we read it" not in r.stderr
    [name] = os.listdir(env["dest"])
    with tarfile.open(env["dest"] / name) as tf:
        names = tf.getnames()
        data = json.load(tf.extractfile("data/portfolio_cache.json"))
    assert data["n"] >= 0 and len(data["pad"]) == 2_000_000
    assert not any(n.endswith(".tmp") for n in names)
