"""Plan C: cutting tall images into overlapping strips (design 7.1)."""
from PIL import Image

from owlocr.pipeline.pages import cut_strips


def test_tall_image_is_cut_into_overlapping_strips(tmp_path):
    image = tmp_path / "chat.png"
    Image.new("RGB", (400, 2000), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert [(top, bottom) for _p, top, bottom in strips] == [(0, 800), (700, 1500), (1400, 2000)]
    for path, top, bottom in strips:
        with Image.open(path) as strip:
            assert strip.size == (400, bottom - top)
    assert strips[0][0].name == "chat_strip1.png"


def test_image_that_fits_one_strip_gives_one_strip(tmp_path):
    image = tmp_path / "short.png"
    Image.new("RGB", (400, 700), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert [(top, bottom) for _p, top, bottom in strips] == [(0, 700)]


def test_overlap_has_a_minimum_for_narrow_images(tmp_path):
    image = tmp_path / "narrow.png"
    Image.new("RGB", (100, 1000), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert strips[1][1] == strips[0][2] - 80
