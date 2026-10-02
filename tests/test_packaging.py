import struct
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGING = Path(__file__).parent.parent / "packaging"
ICON_SIZES = {16, 24, 32, 48, 64, 128, 256}


def test_icon_svg_is_an_svg() -> None:
    root = ET.parse(PACKAGING / "sheet-dj.svg").getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"


def test_icon_ico_holds_every_size_windows_asks_for() -> None:
    data = (PACKAGING / "sheet-dj.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)  # an .ico, not a .cur
    # In the directory a width of 0 means 256.
    widths = {data[6 + 16 * i] or 256 for i in range(count)}
    assert widths == ICON_SIZES


def test_installer_inputs_exist() -> None:
    # What the spec and the Inno script name must be in the repository, or the Windows build breaks.
    for name in ("entry.py", "sheet-dj.spec", "sheet-dj.iss", "build.ps1", "smoke_test.py"):
        assert (PACKAGING / name).is_file(), name
    script = (PACKAGING / "sheet-dj.iss").read_text(encoding="utf-8")
    assert "SetupIconFile=sheet-dj.ico" in script
    assert "AppId={{" in script  # the id that lets a new setup upgrade an old install
