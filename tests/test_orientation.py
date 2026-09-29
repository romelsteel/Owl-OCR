"""Plan C: orientation guards (design 7.2 and 7.3)."""
import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from owlocr.engine.protocol import PageResult
from owlocr.pipeline import guards

PAGES = Path(__file__).parent / "fixtures" / "pages"
GOOD = "<|det|>text [100, 100, 900, 200]<|/det|>Rostlina je velký strom a list je malý."
BAD = "<|det|>text [100, 100, 900, 200]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam."


def _lines_image(path: Path, sideways: bool) -> Path:
    """Lines of 'words' (black bars of random width) like a page of text."""
    rng = random.Random(7)
    img = Image.new("L", (800, 1100), 255)
    draw = ImageDraw.Draw(img)
    for top in range(100, 1000, 40):
        left = 80
        while True:
            width = rng.randint(20, 110)
            if left + width > 720:
                break
            draw.rectangle((left, top, left + width, top + 14), fill=0)
            left += width + rng.randint(10, 18)
    if sideways:
        img = img.rotate(90, expand=True)
    img.save(path)
    return path


def test_upright_fixture_is_not_sideways():
    assert guards.looks_sideways(PAGES / "01_letter_clean.png") is False


def test_rotated_fixture_is_sideways():
    assert guards.looks_sideways(PAGES / "09_letter_rotated_90.png") is True


def test_other_fixtures_are_not_sideways():
    for name in ("02_textbook_clean", "03_small_print_clean", "04_table_clean",
                 "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo",
                 "08_screenshot", "10_blank_page"):
        assert guards.looks_sideways(PAGES / f"{name}.png") is False, name


def test_grey_low_contrast_scans_work_too(tmp_path):
    """Normalised against the page's own brightness: grey paper, grey ink."""
    for name, sideways in (("01_letter_clean", False), ("05_letter_poor_scan", False),
                           ("09_letter_rotated_90", True)):
        with Image.open(PAGES / f"{name}.png") as img:
            low = Image.eval(img.convert("L"), lambda v: int(v * 0.25 + 150))   # 150..213
        path = tmp_path / f"{name}_grey.png"
        low.save(path)
        assert guards.looks_sideways(path) is sideways, name


def test_drawn_lines(tmp_path):
    assert guards.looks_sideways(_lines_image(tmp_path / "up.png", False)) is False
    assert guards.looks_sideways(_lines_image(tmp_path / "side.png", True)) is True


def test_rotate_image_turns_clockwise(tmp_path):
    src = tmp_path / "src.png"
    img = Image.new("RGB", (40, 20), "white")
    img.putpixel((39, 0), (255, 0, 0))              # red dot in the top-right corner
    img.save(src)
    out = guards.rotate_image(src, 90, tmp_path / "out.png")
    with Image.open(out) as rotated:
        assert rotated.size == (20, 40)
        assert rotated.getpixel((19, 39)) == (255, 0, 0)  # top-right went to bottom-right
    with Image.open(src) as original, Image.open(out) as rotated:
        # plan B reproduces the read image exactly like this
        assert rotated.tobytes() == original.rotate(-90, expand=True).tobytes()


class CannedEngine:
    """Answers with GOOD for one orientation of the probe and BAD for the others."""

    def __init__(self, good_degrees: int):
        self.good = good_degrees
        self.calls = []
        self.cancel_after = None          # answer "cancelled" from this call on (1-based)
        self.timeout_after = None         # answer "timed out" from this call on (1-based)

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        self.calls.append((Path(image).name, mode, max_new_tokens))
        text = GOOD if Path(image).stem.endswith(f"_probe{self.good}") else BAD
        cancelled = self.cancel_after is not None and len(self.calls) >= self.cancel_after
        timed_out = self.timeout_after is not None and len(self.calls) >= self.timeout_after
        return PageResult(text="" if cancelled or timed_out else text, seconds=0.1,
                          prefix_tokens=1, output_tokens=10, hit_token_cap=False,
                          cancelled=cancelled, timed_out=timed_out, peak_vram_mib=0)


def test_hit_rate_with_dictionary(tiny_dicts):
    assert guards.dictionary_hit_rate("Rostlina je velký strom.", "cs") == 1.0
    assert guards.dictionary_hit_rate("Rostlina je xqzt wvpl.", "cs") == 0.5
    assert guards.dictionary_hit_rate("123 456", "cs") == 0.0


def test_hit_rate_without_dictionary_is_one(no_dicts):
    assert guards.dictionary_hit_rate("xqzt wvpl", "cs") == 1.0


@pytest.mark.parametrize("good", [0, 90, 180, 270])
def test_best_rotation_picks_the_readable_orientation(tiny_dicts, tmp_path, good):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(good)
    assert guards.best_rotation(image, engine, "cs") == good
    assert [c[1:] for c in engine.calls] == [("fast", 120)] * 4
    assert not list(tmp_path.glob("*_probe*.png"))            # probes are cleaned up


def test_best_rotation_without_dictionary_makes_no_probe(no_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(90)
    assert guards.best_rotation(image, engine, "cs") == 0
    assert engine.calls == []


def test_best_rotation_stops_at_a_cancelled_probe(tiny_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(180)
    engine.cancel_after = 2
    assert guards.best_rotation(image, engine, "cs") == 0
    assert len(engine.calls) == 2


def test_best_rotation_stops_at_a_timed_out_probe(tiny_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(270)
    engine.timeout_after = 3
    assert guards.best_rotation(image, engine, "cs") == 0
    assert len(engine.calls) == 3
    assert not list(tmp_path.glob("*_probe*.png"))


# ---- final review M7: a probe must clearly beat the page as it is ------------------------------

class _RatedEngine:
    def __init__(self, texts):
        self.texts = texts                 # degrees -> probe text

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        degrees = int(Path(image).stem.rsplit("_probe", 1)[1])
        return PageResult(text=self.texts.get(degrees, "xqzt wvpl"), seconds=0.1,
                          prefix_tokens=1, output_tokens=10, hit_token_cap=False,
                          cancelled=False, timed_out=False, peak_vram_mib=0)


def test_a_noise_win_by_a_turned_probe_keeps_the_page(tiny_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = _RatedEngine({0: "strom list xqzt wvpl", 90: "strom list dub xqzt wvpl"})  # .5/.6
    assert guards.ROTATION_MARGIN == 0.15
    assert guards.best_rotation(image, engine, "cs") == 0


def test_a_clear_win_by_a_turned_probe_turns_the_page(tiny_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = _RatedEngine({0: "strom list xqzt wvpl", 90: "strom list dub buk xqzt"})  # .5/.8
    assert guards.best_rotation(image, engine, "cs") == 90
