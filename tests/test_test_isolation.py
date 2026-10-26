import os

import pytest

import notify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_writes_to_data_fail_in_tests():
    with pytest.raises(AssertionError, match="data/"):
        open(os.path.join(ROOT, "data", "should-never-exist.json"), "w")
    assert not os.path.exists(os.path.join(ROOT, "data", "should-never-exist.json"))


def test_notify_uses_temporary_files_and_no_real_smtp(tmp_path):
    for path in (notify.MAIL_FILE, notify.STATE_FILE, notify.USERS_FILE):
        assert not os.path.realpath(path).startswith(os.path.realpath(os.path.join(ROOT, "data")))
    with pytest.raises(AssertionError, match="SMTP"):
        notify.smtplib.SMTP("smtp.example.invalid", 587)
