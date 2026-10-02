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
