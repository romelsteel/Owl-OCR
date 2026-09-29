from PIL import Image, ImageDraw

from owlocr.pipeline import guards
from tests.conftest import PAGES, RAW

REAL_TEXT = "\n".join(
    (RAW / f"{name}.gundam.raw.txt").read_text(encoding="utf-8")
    for name in ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
                 "06_textbook_poor_scan")
)


def test_fixture_pages():
    assert guards.is_blank(PAGES / "10_blank_page.png")
    for name in ("01_letter_clean", "03_small_print_clean", "05_letter_poor_scan", "06_textbook_poor_scan",
                 "07_letter_phone_photo", "08_screenshot"):
        assert not guards.is_blank(PAGES / f"{name}.png"), name


def test_speckles_alone_are_blank(tmp_path):
    im = Image.new("L", (1000, 1000), 255)
    for i in range(0, 1000, 37):                    # isolated dark pixels: removed by the median filter
        im.putpixel((i, (i * 7) % 1000), 0)
    im.save(tmp_path / "speckles.png")
    assert guards.is_blank(tmp_path / "speckles.png")


def test_grey_paper_without_text_is_blank(tmp_path):
    Image.new("L", (800, 800), 200).save(tmp_path / "grey.png")
    assert guards.is_blank(tmp_path / "grey.png")


def test_one_line_of_text_is_not_blank(tmp_path):
    im = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(im).rectangle([100, 500, 900, 520], fill="black")   # 1.6 % of the pixels
    im.save(tmp_path / "line.png")
    assert not guards.is_blank(tmp_path / "line.png")


def test_dark_mode_page_with_light_text_is_not_blank(tmp_path):
    im = Image.new("L", (800, 800), 25)                     # dark background
    ImageDraw.Draw(im).rectangle([100, 300, 700, 320], fill=255)   # light text bar
    im.save(tmp_path / "dark_mode.png")
    assert not guards.is_blank(tmp_path / "dark_mode.png")


def test_dim_photo_with_dim_ink_is_not_blank(tmp_path):
    im = Image.new("L", (800, 800), 100)                    # dim paper, not a clean white scan
    ImageDraw.Draw(im).rectangle([100, 300, 700, 320], fill=30)    # dim ink: 70 levels from the
    im.save(tmp_path / "dim.png")                                 # paper, below the fixed 80-level
    assert not guards.is_blank(tmp_path / "dim.png")                # cutoff but caught by the scaled one


def test_uniform_dark_page_is_blank(tmp_path):
    Image.new("L", (800, 800), 30).save(tmp_path / "uniform_dark.png")
    assert guards.is_blank(tmp_path / "uniform_dark.png")


def test_uniform_mid_grey_page_with_mild_noise_is_blank(tmp_path):
    # +-10 levels of sensor/scan noise around a mid-grey paper must not look like ink.
    im = Image.new("L", (800, 800))
    px = im.load()
    for x in range(im.width):
        for y in range(im.height):
            px[x, y] = 128 + ((x * 31 + y * 17) % 21 - 10)     # deterministic pseudo-noise, +-10
    im.save(tmp_path / "noisy_grey.png")
    assert guards.is_blank(tmp_path / "noisy_grey.png")


def test_dark_below_paper_is_inclusive(tmp_path):
    # off-by-one: a pixel exactly at the (scaled) ink threshold must count as ink.
    paper = 100
    threshold = guards._dark_threshold(paper)
    im = Image.new("L", (800, 800), paper)
    ImageDraw.Draw(im).rectangle([100, 300, 700, 320], fill=paper - threshold)
    im.save(tmp_path / "boundary.png")
    assert not guards.is_blank(tmp_path / "boundary.png")


def test_is_runaway():
    assert guards.is_runaway("short", hit_token_cap=True)
    assert not guards.is_runaway(REAL_TEXT, hit_token_cap=False)
    assert len(REAL_TEXT) > 5000
    assert guards.is_runaway("50 or greater, " * 800, hit_token_cap=False)
    assert not guards.is_runaway("abc " * 1000, hit_token_cap=False)      # under 5,000 characters


def test_trim_runaway_keeps_the_real_text():
    loop = "50 or greater, 70 or greater, " * 1500
    trimmed = guards.trim_runaway(REAL_TEXT + "\n" + loop)
    assert trimmed.startswith(REAL_TEXT[:4000])
    assert len(trimmed) < len(REAL_TEXT) + 1000
    assert not guards.is_runaway(trimmed, hit_token_cap=False)


def test_trim_runaway_leaves_normal_text_alone():
    assert guards.trim_runaway(REAL_TEXT) == REAL_TEXT
    assert guards.trim_runaway("") == ""
    table = (RAW / "04_table_clean.gundam.raw.txt").read_text(encoding="utf-8")
    assert guards.trim_runaway(table) == table


def test_trim_runaway_all_loop():
    assert guards.trim_runaway("la " * 5000) == ("la " * 5000)[:200].rstrip()


def test_ink_pixels_counts_ink_after_the_speckle_filter(tmp_path):
    img = Image.new("L", (200, 200), 255)
    ImageDraw.Draw(img).rectangle((50, 50, 59, 59), fill=0)     # a 10 x 10 mark
    img.putpixel((150, 150), 0)                                 # a speckle
    img.save(tmp_path / "mark.png")
    ink, pixels = guards.ink_pixels(tmp_path / "mark.png")
    assert pixels == 200 * 200 and 90 <= ink <= 100
    Image.new("L", (200, 200), 255).save(tmp_path / "white.png")
    assert guards.ink_pixels(tmp_path / "white.png") == (0, 200 * 200)
