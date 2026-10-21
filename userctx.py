import contextlib
import os
import re
import threading

DATA_ROOT = "data"
USERS_FILE = os.path.join(DATA_ROOT, "users.json")

_tl = threading.local()
_made = set()


def set_user(name):
    _tl.user = name


@contextlib.contextmanager
def as_user(name):
    """Fisierele per utilizator (UPath) se rezolva temporar pentru alt utilizator; apoi se revine."""
    previous = getattr(_tl, "user", None)
    _tl.user = name
    try:
        yield
    finally:
        _tl.user = previous


def current_user():
    u = getattr(_tl, "user", None)
    if u:
        return u
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return None
        import streamlit as st
        return st.session_state.get("_user")
    except Exception:
        return None


def safe_name(u):
    return re.sub(r"[^a-z0-9_-]", "_", str(u).lower())


def user_dir():
    if not os.path.exists(USERS_FILE):
        return DATA_ROOT  # mod vechi, fara utilizatori
    u = current_user()
    base = os.path.join(DATA_ROOT, "users", safe_name(u)) if u else os.path.join(DATA_ROOT, "_anon")
    if base not in _made:
        os.makedirs(base, exist_ok=True)
        _made.add(base)
    return base


class UPath(os.PathLike):
    def __init__(self, name, shared=False):
        self.name = name
        self.shared = shared

    def _p(self):
        return os.path.join(DATA_ROOT if self.shared else user_dir(), self.name)

    def __fspath__(self):
        return self._p()

    def __str__(self):
        return self._p()

    def __repr__(self):
        return "UPath(%r)" % self._p()

    def __add__(self, other):
        return self._p() + str(other)

    def __radd__(self, other):
        return str(other) + self._p()

    def __eq__(self, other):
        return self._p() == (os.fspath(other) if isinstance(other, os.PathLike) else other)

    def __hash__(self):
        return hash(self._p())


def _install_thread_propagation():
    if getattr(threading.Thread, "_pt_user_patched", False):
        return
    _orig_start = threading.Thread.start
    _orig_run = threading.Thread.run

    def start(self):
        self._pt_user = current_user()
        return _orig_start(self)

    def run(self):
        u = getattr(self, "_pt_user", None)
        if u:
            _tl.user = u
        return _orig_run(self)

    threading.Thread.start = start
    threading.Thread.run = run
    threading.Thread._pt_user_patched = True


_install_thread_propagation()
