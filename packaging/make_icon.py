r"""Draws the pixel-art owl icon of Owl OCR and saves it as a Windows .ico file.

    py -3.11 packaging\make_icon.py build\owl.ico

The owl is a 16 x 16 pixel grid. Every icon size is scaled from it with nearest-neighbour
resampling, so the pixels stay sharp.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

GRID = (
    "..DD........DD..",
    "..DbD......DbD..",
    "..DbBDDDDDDBbD..",
    ".DBBBBBBBBBBBBD.",
    ".DBLLLLBBLLLLBD.",
    "DBLWWWLLLLWWWLBD",
    "DBLWKWLLLLWKWLBD",
    "DBLWWWLYYLWWWLBD",
    "DBBLLLLYYLLLLBBD",
    "DbBBBBBBBBBBBBbD",
    "DbBTLTLTLTLTBBbD",
    "DbBLTLTLTLTLBBbD",
    ".DbBTLTLTLTBBbD.",
    ".DbBBBBBBBBBBbD.",
    "..DDFFDDDDFFDD..",
    "................",
)
COLOURS = {
    ".": (0, 0, 0, 0),
    "D": (59, 42, 26, 255),       # outline
    "B": (139, 90, 43, 255),      # feathers
    "b": (107, 68, 32, 255),      # ear tufts and wings
    "L": (232, 199, 154, 255),    # face and belly
    "W": (255, 250, 240, 255),    # eyes
    "K": (26, 26, 26, 255),       # pupils
    "Y": (242, 178, 51, 255),     # beak
    "T": (201, 160, 107, 255),    # belly pattern
    "F": (224, 123, 36, 255),     # feet
}
SIZES = (16, 24, 32, 48, 64, 128, 256)


def owl_image() -> Image.Image:
    if len(GRID) != 16 or any(len(row) != 16 for row in GRID):
        raise ValueError("the owl grid must be 16 x 16")
    image = Image.new("RGBA", (16, 16))
    image.putdata([COLOURS[ch] for row in GRID for ch in row])
    return image


def save_icon(out: Path) -> Path:
    base = owl_image()
    frames = [base.resize((s, s), Image.Resampling.NEAREST) for s in SIZES]
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    return out


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent / "build" / "owl.ico"
    print("icon written to", save_icon(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
