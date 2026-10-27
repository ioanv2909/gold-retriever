"""Pagina principala cu surse partiale: XTB fara Trading 212, T212 fara pozitii, prima aducere T212 esuata.
Fiecare caz ruleaza app.py intreg (AppTest) intr-un proces separat, cu data/ propriu si fara retea."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(ROOT, "tests", "main_page_driver.py")


def _run(tmp_path, scenario, detail=None):
    work = tmp_path / "app"
    work.mkdir()
    args = [sys.executable, DRIVER, ROOT, str(work), scenario] + ([detail] if detail else [])
    p = subprocess.run(args, capture_output=True, text=True, timeout=240, cwd=str(work))
    lines = [line for line in p.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, p.stdout[-2000:] + p.stderr[-4000:]
    out = json.loads(lines[-1][len("RESULT "):])
    assert out["exception"] == [], p.stderr[-4000:]
    return out


def _metric(out, prefix):
    return next(v for label, v in out["metrics"] if label.startswith(prefix))


XTB_ONLY_SUMS = {"💰": "1,275.00", "📊": "1,500.00"}


@pytest.mark.parametrize("scenario", ["xtb_only", "t212_empty", "t212_first_error"])
def test_xtb_positions_show_without_usable_t212_data(tmp_path, scenario):
    out = _run(tmp_path, scenario)
    for prefix, value in XTB_ONLY_SUMS.items():
        assert _metric(out, prefix) == value
    assert out["rows"] == [2]
    if scenario == "t212_first_error":
        assert out["error"] == ["T212 API: 503"]
    else:
        assert out["error"] == [] and out["info"] == []
    # fara date T212 utilizabile, "Trading 212" nu se ofera; cu cont T212 gol (doar cash) ramane
    offered = [o for opts in out["pills"] for o in opts]
    assert ("Trading 212" in offered) == (scenario == "t212_empty")


def test_t212_and_xtb_are_added_up(tmp_path):
    out = _run(tmp_path, "both")
    assert _metric(out, "💰") == "1,575.00" and _metric(out, "📊") == "1,860.00"
    assert out["rows"][0] == 3
    # watchlist: pretul de la 15 minute, cu ora lui
    assert out["rows"][1] == 1 and "Preț la" in out["columns"][1]


def test_t212_only_is_unchanged(tmp_path):
    out = _run(tmp_path, "t212_only")
    assert _metric(out, "💰") == "300.00" and _metric(out, "📊") == "360.00"
    assert out["rows"] == [1]


def test_no_source_keeps_the_no_data_message(tmp_path):
    out = _run(tmp_path, "none")
    assert out["metrics"] == [] and out["rows"] == [] and len(out["info"]) == 1


def test_xtb_detail_link_opens_without_t212(tmp_path):
    out = _run(tmp_path, "xtb_only", detail="VWCE.DE")
    assert out["selected"] == "VWCE.DE"


def test_settings_has_the_weekly_report_tab(tmp_path):
    out = _run(tmp_path, "xtb_only", detail="page=settings&tab=weekly")
    assert "Trimite raportul săptămânal" in out["checkboxes"]
