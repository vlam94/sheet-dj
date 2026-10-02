"""Render sheet-dj.svg into sheet-dj.ico (needs `rsvg-convert` and Pillow; run by hand).

.venv/bin/python packaging/make_icon.py
"""

import io
import subprocess
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> Image.Image:
    png = subprocess.run(
        ["rsvg-convert", "--width", str(size), "--height", str(size), str(HERE / "sheet-dj.svg")],
        check=True,
        capture_output=True,
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    images = [render(size) for size in SIZES]
    images[-1].save(
        HERE / "sheet-dj.ico",
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[:-1],
    )


if __name__ == "__main__":
    main()
