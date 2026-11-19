"""Extrasul CSV de contributii al fondului de pensii (date fictive)."""
import pytest

import pension_statement as ps

HEAD = ('"Data Contributiei","Tip contributie","Valoare bruta - Angajat (RON)","Valoare bruta - Angajator (RON)",'
        '"Valoare bruta - Total (RON)","Valoare neta (RON)","VUAN la data contributiei (RON)","Nr unitati alocate la data contributiei"\n')


def _csv(rows):
    return (HEAD + "".join(f'"{d}","Virament lunar","0.00","{g}","{g}","{g}","{v}","{u}"\n' for d, g, v, u in rows) + "\n").encode()


def test_parse_units_value_and_return():
    raw = _csv([("05.11.2026", "100.00", "12.000000", "8.333333"), ("05.11.2025", "100.00", "10.000000", "10.000000")])
    info = ps.parse(raw)
    assert info["units"] == pytest.approx(18.333333) and info["vuan"] == pytest.approx(12.0)
    assert info["vuan_date"] == "2026-11-05" and info["value"] == pytest.approx(18.333333 * 12)
    assert info["paid_in"] == pytest.approx(200) and info["count"] == 2 and info["first_date"] == "2025-11-05"
    assert info["xirr"] == pytest.approx(20.0, abs=0.1)  # primii 100 au crescut cu 20% intr-un an
    assert info["monthly_avg"] == pytest.approx(100 / 12)  # doar contributiile din ultimele 12 luni


def test_rejects_other_files():
    for raw in (b"", b"a,b\n1,2\n", b"x" * (ps.MAX_BYTES + 1)):
        with pytest.raises(ps.StatementError):
            ps.parse(raw)
    with pytest.raises(ps.StatementError):
        ps.parse(_csv([("31.02.2026", "1", "1", "1")]))


def test_xirr_simple():
    from datetime import date
    assert ps.xirr([(date(2025, 1, 1), 100)], date(2026, 1, 1), 110) == pytest.approx(10, abs=0.05)


def test_monthly_average_uses_twelve_calendar_months():
    rows = [("03.11.2026", "50.00", "1", "1"), ("03.12.2025", "50.00", "1", "1"), ("04.11.2025", "50.00", "1", "1")]
    assert ps.parse(_csv(rows))["monthly_avg"] == pytest.approx(100 / 12)
