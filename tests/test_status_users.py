import json
import os
import time

import userctx


def _setup(tmp_path, monkeypatch, names):
    monkeypatch.setattr(userctx, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(userctx, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(userctx, "_made", set())
    (tmp_path / "users.json").write_text(json.dumps({"users": {n: {} for n in names}}))


def test_as_user_resolves_per_user_paths_and_restores(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, ["ana", "bob"])
    p = userctx.UPath("ratings_status.json")
    userctx.set_user("ana")
    with userctx.as_user("bob"):
        assert os.fspath(p) == os.path.join(str(tmp_path), "users", "bob", "ratings_status.json")
    assert os.fspath(p) == os.path.join(str(tmp_path), "users", "ana", "ratings_status.json")
    userctx.set_user(None)


def test_status_page_lists_per_user_jobs_for_every_user(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, ["ana", "bob"])
    import health_ui
    import users
    monkeypatch.setattr(users, "names", lambda: ["ana", "bob"])
    monkeypatch.setattr(health_ui, "t", lambda key, **kw: key if not kw else "%s%s" % (key, kw))
    os.makedirs(tmp_path / "users" / "bob")
    (tmp_path / "users" / "bob" / "ratings_status.json").write_text(json.dumps({"in_progress": False, "done": 3, "total": 3}))
    rows = health_ui._jobs()
    by = {(r["hs.col.job"], r["hs.col.user"]): r for r in rows}
    assert len(rows) == len(health_ui.SHARED_JOBS) + 2 * len(health_ui.USER_JOBS)
    assert ("hs.job.quality", "hs.all_users") in by
    assert by[("hs.job.ratings", "bob")]["hs.col.state"].startswith("🟢")
    assert by[("hs.job.ratings", "bob")]["hs.col.progress"] == "3/3"
    assert by[("hs.job.ratings", "ana")]["hs.col.state"].startswith("⚪")
