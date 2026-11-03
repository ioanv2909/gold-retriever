"""Linii de log la pornirea si terminarea joburilor de fundal: "[job] start <nume> user=<u>" si
"[job] done <nume> user=<u> 12.3s". Ca sa nu umple logul:
- joburile dese (la 15 minute) scriu doar linia de final;
- joburile care sar datele proaspete (orare, justETF) scriu doar daca au lucrat ceva (au durat cel putin MIN_WORK_S).
Un job care arunca o exceptie scrie "[job_failed] ..." (logwatch o trateaza ca problema) si exceptia merge mai departe."""
import functools
import sys
import time

MIN_WORK_S = 1.0


def _log(line):
    """O singura scriere (linia cu tot cu sfarsitul ei), ca liniile din fire paralele sa nu se amestece."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _user():
    try:
        from userctx import current_user
        return current_user() or "-"
    except Exception:
        return "-"


def wrap(name, fn, often=False, skip_fast=False):
    """fn cu linii de log la start/final. often: fara linia de start; skip_fast: nimic daca a durat < MIN_WORK_S."""
    quiet_start = often or skip_fast

    @functools.wraps(fn)
    def run(*args, **kwargs):
        user = _user()
        if not quiet_start:
            _log(f"[job] start {name} user={user}")
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            _log(f"[job_failed] {name} user={user} after {time.monotonic() - t0:.1f}s: {type(e).__name__}: {e}")
            raise
        took = time.monotonic() - t0
        if not (skip_fast and took < MIN_WORK_S):
            _log(f"[job] done {name} user={user} {took:.1f}s")
        return result

    return run
