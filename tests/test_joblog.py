import pytest

import joblog
import logwatch


def test_rare_job_logs_start_and_done(capsys):
    assert joblog.wrap("demo", lambda x: x + 1)(1) == 2
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "[job] start demo user=-"
    assert out[1].startswith("[job] done demo user=- ") and out[1].endswith("s")


def test_often_job_logs_only_done(capsys):
    joblog.wrap("demo", lambda: None, often=True)()
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and out[0].startswith("[job] done demo")


def test_skip_fast_job_is_silent_when_nothing_to_do(capsys, monkeypatch):
    joblog.wrap("demo", lambda: None, skip_fast=True)()
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(joblog, "MIN_WORK_S", 0.0)
    joblog.wrap("demo", lambda: None, skip_fast=True)()
    assert capsys.readouterr().out.startswith("[job] done demo")


def test_failed_job_is_logged_and_reraised(capsys):
    def boom():
        raise ValueError("bad")
    with pytest.raises(ValueError):
        joblog.wrap("demo", boom)()
    out = capsys.readouterr().out
    assert "[job_failed] demo user=-" in out and "ValueError: bad" in out


def test_job_lines_are_not_problems_but_failures_are():
    assert not logwatch.is_problem("[job] start t212_dividends user=admin")
    assert not logwatch.is_problem("[job] done xtb_prices user=admin 2.1s")
    assert logwatch.is_problem("[job_failed] events user=admin after 1.0s: ValueError: bad")
