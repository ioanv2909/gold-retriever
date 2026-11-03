"""Linii de log la pornirea si terminarea joburilor de fundal: "[job] start <nume> user=<u>" si
"[job] done <nume> user=<u> 12.3s". Ca sa nu umple logul:
- joburile dese (la 15 minute) scriu doar linia de final;
- joburile orare care sar tickerele proaspete scriu doar daca au lucrat ceva (au durat cel putin MIN_WORK_S).
Un job care arunca o exceptie scrie "[job_failed] ..." (logwatch o trateaza ca problema) si exceptia merge mai departe."""
import functools
import time

MIN_WORK_S = 1.0


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
            print(f"[job] start {name} user={user}", flush=True)
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            print(f"[job_failed] {name} user={user} after {time.monotonic() - t0:.1f}s: {type(e).__name__}: {e}",
                  flush=True)
            raise
        took = time.monotonic() - t0
        if not (skip_fast and took < MIN_WORK_S):
            print(f"[job] done {name} user={user} {took:.1f}s", flush=True)
        return result

    return run
