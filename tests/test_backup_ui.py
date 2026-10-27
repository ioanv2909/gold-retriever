import json

import backup_ui


def test_request_is_written_once_while_pending():
    assert backup_ui.request_backup("admin", now=1000) is True
    req = backup_ui.load_request()
    assert req["state"] == "requested" and req["by"] == "admin"
    assert backup_ui.request_backup("admin", now=1010) is False


def test_finished_or_stuck_requests_allow_a_new_one():
    for state, ts in (("done", 1000), ("failed", 1000), ("running", 1000 - backup_ui.RUNNING_MAX_S - 1)):
        with open(backup_ui.REQUEST_FILE, "w") as f:
            json.dump({"state": state, "ts": ts}, f)
        assert not backup_ui.pending(now=1000)
        assert backup_ui.request_backup("admin", now=1000) is True


def test_bad_request_file_is_ignored():
    with open(backup_ui.REQUEST_FILE, "w") as f:
        f.write("[1]")
    assert backup_ui.load_request() == {} and not backup_ui.pending()
