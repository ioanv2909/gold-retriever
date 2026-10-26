import io
import os
import zipfile

import openpyxl
import pytest

import upload_guard
import userctx
from upload_guard import check_xlsx
from userctx import UPath, as_user, contained_path, safe_name


def _xlsx_bytes():
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Open Positions"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip(entries, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_valid_xlsx_passes():
    assert check_xlsx(_xlsx_bytes()) is None


def test_too_large_rejected():
    assert check_xlsx(b"\0" * (upload_guard.MAX_UPLOAD_BYTES + 1)) == "too_large"


def test_not_a_zip_rejected():
    assert check_xlsx(b"just text, not a workbook") == "not_zip"


def test_zip_without_xlsx_structure_rejected():
    assert check_xlsx(_zip({"readme.txt": "hello"})) == "not_xlsx"


def test_zip_bomb_rejected():
    bomb = _zip({"[Content_Types].xml": "<x/>", "xl/workbook.xml": "<x/>",
                 "xl/worksheets/sheet1.xml": b"\0" * (150 * 1024 * 1024)})
    assert len(bomb) < upload_guard.MAX_UPLOAD_BYTES
    assert check_xlsx(bomb) == "too_big_unpacked"


def test_high_ratio_entry_rejected(monkeypatch):
    monkeypatch.setattr(upload_guard, "MAX_UNPACKED_BYTES", 10**12)
    bomb = _zip({"[Content_Types].xml": "<x/>", "xl/workbook.xml": "<x/>",
                 "xl/sharedStrings.xml": b"\0" * (20 * 1024 * 1024)})
    assert check_xlsx(bomb) == "too_big_unpacked"


def test_too_many_entries_rejected(monkeypatch):
    monkeypatch.setattr(upload_guard, "MAX_ENTRIES", 5)
    entries = {"[Content_Types].xml": "<x/>", "xl/workbook.xml": "<x/>"}
    entries.update({f"xl/p{i}.xml": "<x/>" for i in range(10)})
    assert check_xlsx(_zip(entries)) == "too_many_entries"


@pytest.mark.parametrize("name", ["../evil.xml", "xl/../../evil.xml", "/etc/evil.xml", "C:/evil.xml", "..\\evil.xml"])
def test_traversal_entry_names_rejected(name):
    raw = _zip({"[Content_Types].xml": "<x/>", "xl/workbook.xml": "<x/>", name: "x"})
    assert check_xlsx(raw) == "bad_entry"


@pytest.mark.parametrize("name", ["../bob", "ana/../bob", "a/b", "a\\b", "ana\0", ".", "..", "", "a.b", "x" * 33])
def test_bad_user_names_rejected(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_user_name_is_lowercased_not_rewritten():
    assert safe_name("Ana_1-x") == "ana_1-x"


@pytest.mark.parametrize("part", ["../x.json", "a/b.json", "a\\b.json", "x.json\0", "..", ".hidden", ""])
def test_contained_path_rejects_bad_parts(tmp_path, part):
    with pytest.raises(ValueError):
        contained_path(str(tmp_path), part)


def test_contained_path_rejects_symlink_escape(tmp_path):
    base = tmp_path / "users"
    other = tmp_path / "other"
    base.mkdir()
    other.mkdir()
    os.symlink(other, base / "ana")
    with pytest.raises(ValueError):
        contained_path(str(base), "ana")


def test_contained_path_accepts_normal_file(tmp_path):
    assert contained_path(str(tmp_path), "xtb.json") == os.path.join(str(tmp_path), "xtb.json")


@pytest.fixture
def users_root(tmp_path, monkeypatch):
    (tmp_path / "users.json").write_text("{}")
    monkeypatch.setattr(userctx, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(userctx, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(userctx, "_made", set())
    return tmp_path


def test_users_get_separate_folders(users_root):
    p = UPath("xtb.json")
    with as_user("ana"):
        ana = os.fspath(p)
    with as_user("bob"):
        bob = os.fspath(p)
    assert ana == os.path.join(str(users_root), "users", "ana", "xtb.json")
    assert bob == os.path.join(str(users_root), "users", "bob", "xtb.json")


@pytest.mark.parametrize("name", ["../bob", "ana/../bob", "ana\0", "a.b"])
def test_user_cannot_reach_another_users_files(users_root, name):
    with as_user(name):
        with pytest.raises(ValueError):
            os.fspath(UPath("xtb.json"))
    assert not (users_root / "bob").exists()
