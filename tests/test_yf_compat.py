import threading

import pytest

import yf_compat


class FakeHTTPError(Exception):
    def __init__(self, status):
        super().__init__("HTTP Error %d" % status)
        self.response = type("R", (), {"status_code": status})()


def make_cls(responses):
    class FakeData:
        def __init__(self):
            self._crumb = "old"
            self._cookie_lock = threading.Lock()
            self.calls = []

        def get_raw_json(self, url, params=None, timeout=30):
            self.calls.append(self._crumb)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            self._crumb = "fresh"
            return r
    return FakeData


def test_401_is_retried_with_a_new_crumb():
    sleeps = []
    cls = make_cls([FakeHTTPError(401), {"ok": 1}])
    yf_compat.install_auth_retry(cls, FakeHTTPError, sleep=sleeps.append)
    d = cls()
    assert d.get_raw_json("u") == {"ok": 1}
    assert d.calls == ["old", None]  # a doua incercare porneste fara crumb, deci yfinance cere unul nou
    assert sleeps == [yf_compat.AUTH_DELAY]


def test_gives_up_after_retries_and_other_errors_pass_through():
    sleeps = []
    cls = make_cls([FakeHTTPError(401)] * (yf_compat.AUTH_RETRIES + 1) + [FakeHTTPError(404)])
    yf_compat.install_auth_retry(cls, FakeHTTPError, sleep=sleeps.append)
    d = cls()
    with pytest.raises(FakeHTTPError):
        d.get_raw_json("u")
    assert len(d.calls) == yf_compat.AUTH_RETRIES + 1 and len(sleeps) == yf_compat.AUTH_RETRIES
    with pytest.raises(FakeHTTPError) as e:
        d.get_raw_json("u")
    assert e.value.response.status_code == 404 and len(sleeps) == yf_compat.AUTH_RETRIES


def test_install_is_idempotent_and_real_yfinance_is_patched():
    cls = make_cls([{"a": 1}])
    yf_compat.install_auth_retry(cls, FakeHTTPError)
    first = cls.get_raw_json
    yf_compat.install_auth_retry(cls, FakeHTTPError)
    assert cls.get_raw_json is first
    if yf_compat.YFINANCE_AVAILABLE:
        from yfinance.data import YfData
        assert getattr(YfData, "_gr_auth_retry", False)
