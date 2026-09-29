import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packaging"))
import make_icon  # noqa: E402


def test_grid_is_square_and_uses_known_colours():
    assert len(make_icon.GRID) == 16
    assert all(len(row) == 16 for row in make_icon.GRID)
    assert set("".join(make_icon.GRID)) <= set(make_icon.COLOURS)


def test_icon_has_every_size_and_sharp_pixels(tmp_path):
    out = make_icon.save_icon(tmp_path / "owl.ico")
    with Image.open(out) as ico:
        assert set(ico.info["sizes"]) == {(s, s) for s in make_icon.SIZES}
        ico.size = (32, 32)
        img = ico.convert("RGBA")
        img.load()
    # nearest-neighbour: every 2 x 2 block of the 32 px icon is one grid pixel
    for y in range(0, 32, 2):
        for x in range(0, 32, 2):
            block = {img.getpixel((x + dx, y + dy)) for dx in (0, 1) for dy in (0, 1)}
            assert len(block) == 1
    assert img.getpixel((8, 12)) == make_icon.COLOURS["K"]       # left pupil, grid column 4, row 6
