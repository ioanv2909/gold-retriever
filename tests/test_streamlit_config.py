import os
import tomllib

import upload_guard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg():
    with open(os.path.join(ROOT, ".streamlit", "config.toml"), "rb") as f:
        return tomllib.load(f)


def test_errors_are_not_shown_in_the_browser():
    assert _cfg()["client"]["showErrorDetails"] == "none"


def test_upload_limit_matches_the_guard_and_xsrf_is_on():
    s = _cfg()["server"]
    assert s["maxUploadSize"] == upload_guard.MAX_UPLOAD_MB
    assert s["enableXsrfProtection"] is True and s["enableCORS"] is True


def test_options_exist_in_streamlit():
    from streamlit import config
    for section, opts in _cfg().items():
        for name in opts:
            assert "%s.%s" % (section, name) in config._config_options_template


def test_config_goes_into_the_image():
    lines = [l.strip() for l in open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8")]
    assert not any(l in (".streamlit", ".streamlit/", ".*", "*.toml") for l in lines)
