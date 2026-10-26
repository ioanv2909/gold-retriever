"""Validarea fisierelor incarcate inainte de parsare: totul se verifica in memorie, fara decomprimare."""
import io
import zipfile

MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_RATIO = 200
_XLSX_REQUIRED = ("[Content_Types].xml", "xl/workbook.xml")


def check_xlsx(raw):
    """Returneaza None daca raw arata ca un .xlsx sigur de deschis, altfel un cod de eroare
    (cheie i18n "upload.<cod>")."""
    if len(raw) > MAX_UPLOAD_BYTES:
        return "too_large"
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        return "not_zip"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            entries = z.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return "not_zip"
    if len(entries) > MAX_ENTRIES:
        return "too_many_entries"
    names = {e.filename for e in entries}
    for e in entries:
        n = e.filename
        if "\0" in n or n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") or ":" in n:
            return "bad_entry"
    if not all(r in names for r in _XLSX_REQUIRED):
        return "not_xlsx"
    if sum(e.file_size for e in entries) > MAX_UNPACKED_BYTES:
        return "too_big_unpacked"
    for e in entries:
        if e.file_size > 1024 * 1024 and e.file_size > MAX_RATIO * max(e.compress_size, 1):
            return "too_big_unpacked"
    return None
