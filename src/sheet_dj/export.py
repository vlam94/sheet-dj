"""The files of a set list: the tuba csv, the zip around them, and the output name."""

import csv
import io
import zipfile
from collections.abc import Sequence

from pathvalidate import sanitize_filename

from sheet_dj.model import Song

CSV_ENCODING = "utf-8-sig"  # the BOM is what makes Excel on Windows show ♭ and ↑
FALLBACK_NAME = "set list"


def output_name(requested: str, default: str) -> str:
    """A Windows-safe file name stem: the requested name, else the default, else a fixed one."""
    for candidate in (requested, default, FALLBACK_NAME):
        name = sanitize_filename(candidate, platform="windows", fs_encoding="utf-8").strip(" .")
        if name:
            return name
    return FALLBACK_NAME


def tuba_csv(songs: Sequence[Song]) -> bytes:
    """One `Title,line` row per song, without a header."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    for song in songs:
        writer.writerow([song.title, song.tuba_line])
    return buffer.getvalue().encode(CSV_ENCODING)


def set_list_zip(name: str, musicxml: bytes, tuba_csv_bytes: bytes) -> bytes:
    """A zip holding `{name}.musicxml` and `{name}_tuba.csv`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}.musicxml", musicxml, compress_type=zipfile.ZIP_STORED)
        archive.writestr(f"{name}_tuba.csv", tuba_csv_bytes, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()
