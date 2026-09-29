"""Plan C: the rotated fixture page through the real engine client and tests/fake_worker.py.

The fake worker answers an `ocr` request with the content of '<image path>.raw.txt' when that
file exists, so the canned text of every rotation is written next to the image names that
process_page and guards.best_rotation create in the scratch folder. The fixture is turned by
another 180° first, so that the first 90° turn leaves it upside down and the probes through the
real client have to find the remaining 180°.
"""
import sys

from PIL import Image

from owlocr.engine.client import SubprocessEngine
from owlocr.pipeline import process
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, process_page
from tests.conftest import FAKE_WORKER, PAGES

GOOD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je velký strom a list je malý. "
        "Dub a buk jsou dřevitý druh.")
BAD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam. "
       "Bdu a kbu uojs tývěřd hurd.")


def test_rotated_letter_through_the_fake_worker(tiny_dicts, tmp_path):
    source = tmp_path / "turned_the_other_way.png"
    with Image.open(PAGES / "09_letter_rotated_90.png") as img:
        img.rotate(180, expand=True).save(source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "page_0000_r90.png.raw.txt").write_text(BAD, encoding="utf-8")
    for degrees in (0, 90, 180, 270):
        (scratch / f"page_0000_r90_probe{degrees}.png.raw.txt").write_text(
            GOOD if degrees == 180 else BAD, encoding="utf-8")
    (scratch / "page_0000_r270.png.raw.txt").write_text(GOOD, encoding="utf-8")
    engine = SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER,
                              model_dir=tmp_path / "model", device="cpu", dtype="float32",
                              log_file=tmp_path / "logs" / "engine.log")
    try:
        engine.load()                                   # starts the fake worker, then loads
        page = process_page(source, PageSource(0, "image", None), engine,
                            ProcessOptions(language="cs"), scratch)
    finally:
        engine.stop()
    assert page.rotation_applied == 270
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert process.W_ROTATED in page.warnings
    with Image.open(source) as original:
        assert (page.width_px, page.height_px) == (original.height, original.width)
