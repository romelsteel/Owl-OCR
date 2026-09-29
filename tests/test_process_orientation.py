"""Plan C: orientation, dictionaries and (task 14) strips inside process_page (design 7.1-7.3)."""
import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from owlocr.engine.protocol import EngineError, PageResult
from owlocr.pipeline import guards, pages, process
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, process_page
from tests.conftest import PAGES

IMAGE_PAGE = PageSource(index=0, kind="image", text_layer=None)
GOOD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je velký strom a list je malý. "
        "Dub a buk jsou dřevitý druh.")
BAD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam. "
       "Bdu a kbu uojs tývěřd hurd.")


def _result(text, **changes):
    values = dict(text=text, seconds=0.1, prefix_tokens=1, output_tokens=10, hit_token_cap=False,
                  cancelled=False, timed_out=False, peak_vram_mib=0)
    values.update(changes)
    return PageResult(**values)


class ScriptedEngine:
    """Answers like tests/fake_worker.py: the content of '<image path>.raw.txt' when it exists.
    `answer(path, mode)` may override it (return a PageResult or text, or raise)."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls = []

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        image = Path(image)
        self.calls.append({"name": image.name, "mode": mode, "max_new_tokens": max_new_tokens,
                           "on_progress": on_progress, "cancel": cancel})
        if self.answer is not None:
            answer = self.answer(image, mode)
            if answer is not None:
                return answer if isinstance(answer, PageResult) else _result(answer)
        canned = Path(str(image) + ".raw.txt")
        if canned.exists():
            return _result(canned.read_text(encoding="utf-8"))
        return _result(f"<|det|>text [100, 100, 900, 200]<|/det|>fake text for {image.name}")


def _text_image(path: Path, size=(800, 1000)) -> Path:
    img = Image.new("L", size, 255)
    draw = ImageDraw.Draw(img)
    for top in range(80, size[1] - 80, 40):
        draw.rectangle((60, top, size[0] - 60, top + 12), fill=0)
    img.save(path)
    return path


def _upside_down_after_turn(tmp_path) -> tuple[Path, Path]:
    """The rotated letter turned another 180°: the first 90° turn leaves it upside down."""
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
    return source, scratch


def test_rotated_letter_is_turned_upright(tiny_dicts, tmp_path):
    # the fixture is an upright letter turned 90° counter-clockwise; one clockwise turn fixes it
    source = tmp_path / "09_letter_rotated_90.png"
    shutil.copy(PAGES / "09_letter_rotated_90.png", source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "page_0000_r90.png.raw.txt").write_text(GOOD, encoding="utf-8")
    engine = ScriptedEngine()
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert page.rotation_applied == 90
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png"]      # no probes needed
    with Image.open(source) as original:
        assert (page.width_px, page.height_px) == (original.height, original.width)


def test_upside_down_after_the_turn_is_found_by_probing(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)
    engine = ScriptedEngine()
    progress, cancel = [].append, threading.Event()
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch,
                        on_progress=progress, cancel=cancel)
    assert page.rotation_applied == 270
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert process.W_ROTATED in page.warnings
    probes = [c for c in engine.calls if "_probe" in c["name"]]
    assert [(c["mode"], c["max_new_tokens"]) for c in probes] == [("fast", 120)] * 4
    assert all(c["on_progress"] is progress and c["cancel"] is cancel for c in engine.calls)
    with (Image.open(scratch / "page_0000.png") as rendered,
          Image.open(scratch / "page_0000_r270.png") as read):
        # plan B reproduces the read image from the page image with rotate(-rotation_applied)
        assert read.tobytes() == rendered.rotate(-270, expand=True).tobytes()


def test_a_cancelled_probe_is_not_taken_for_a_page(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if "_probe" in image.name:
            return _result("", cancelled=True)
        return None

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png", "page_0000_r90_probe0.png"]
    assert page.rotation_applied == 90 and process.W_ROTATED not in page.warnings
    assert page.blocks[0].text.startswith("Rtsnl")                 # the first reading is kept


def test_a_timed_out_probe_ends_the_page_engine_calls(tiny_dicts, tmp_path):
    # ruling R3 (plan A note 24): a timed-out probe ends probing, no second read on that page
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if "_probe" in image.name:
            return _result("", timed_out=True)
        return None

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png", "page_0000_r90_probe0.png"]
    assert page.rotation_applied == 90 and process.W_ROTATED not in page.warnings
    assert page.blocks[0].text.startswith("Rtsnl")


def test_a_timed_out_first_reading_is_not_probed(tiny_dicts, tmp_path):
    # ruling R3: the page's time budget is spent, so no probes follow
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if image.name == "page_0000_r90.png":
            return _result(BAD, timed_out=True)
        return None

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png"]
    assert page.rotation_applied == 90 and "time_limit" in page.warnings


def test_engine_errors_in_a_probe_reach_the_caller(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if "_probe" in image.name:
            raise EngineError("died", "worker gone")
        return None

    with pytest.raises(EngineError) as error:
        process_page(source, IMAGE_PAGE, ScriptedEngine(answer), ProcessOptions(language="cs"),
                     scratch)
    assert error.value.kind == "died"


def test_no_probes_without_a_dictionary(no_dicts, tmp_path):
    source = _text_image(tmp_path / "upright.png")
    engine = ScriptedEngine(lambda image, mode: BAD)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == 1 and page.rotation_applied == 0


def test_upright_page_with_known_words_is_not_probed(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "upright.png")
    engine = ScriptedEngine(lambda image, mode: GOOD)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == 1 and page.rotation_applied == 0


def test_repairs_and_flags_are_applied(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "page.png")
    text = "<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je bud' strom, nebo bylinny list."
    page = process_page(source, IMAGE_PAGE, ScriptedEngine(lambda image, mode: text),
                        ProcessOptions(language="cs"), tmp_path / "scratch")
    block = page.blocks[0]
    assert block.text == "Rostlina je buď strom, nebo bylinny list."
    assert block.raw_text == "Rostlina je bud' strom, nebo bylinny list."
    assert [(f.kind, f.original) for f in block.flags] == [("repaired", "bud'"),
                                                           ("suspicious", "bylinny")]


def test_auto_language_picks_english(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "page.png")
    text = ("<|det|>text [100, 100, 900, 300]<|/det|>This is the doctor and the report "
            "of the green tree.")
    page = process_page(source, IMAGE_PAGE, ScriptedEngine(lambda image, mode: text),
                        ProcessOptions(language="auto"), tmp_path / "scratch")
    assert page.blocks[0].flags == []


def test_tall_image_is_read_in_strips(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    strips = pages.cut_strips(source, tmp_path / "precut")      # same cut as process_page makes
    lines = [(k * 100 + 20, k * 100 + 50) for k in range(20)]   # image px of 20 text lines

    def answer(image, mode):
        n = int(image.stem.rsplit("strip", 1)[1])
        _path, top, bottom = strips[n - 1]
        out = []
        for k, (y1, y2) in enumerate(lines):
            if top <= y1 and y2 <= bottom:                      # the model sees the whole line
                s1 = round((y1 - top) / (bottom - top) * 999)
                s2 = round((y2 - top) / (bottom - top) * 999)
                out.append(f"<|det|>text [10, {s1}, 990, {s2}]<|/det|>line {k}")
        return "\n".join(out)

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == len(strips) == 3
    assert [b.text for b in page.blocks] == [f"line {k}" for k in range(20)]
    for block, (y1, _y2) in zip(page.blocks, lines):
        assert abs(block.box[1] - y1 / 2000 * 999) <= 2
    assert page.warnings == []


def _strip_answers(by_strip):
    """Engine answer per strip number (1-based); strips not listed read as empty."""
    def answer(image, mode):
        n = int(image.stem.rsplit("strip", 1)[1])
        return by_strip.get(n, "")
    return answer


def test_a_strip_with_very_little_ink_is_still_read(no_dicts, tmp_path):
    # is_blank's 0.2 % cut-off must not skip a strip - a lone short message is under it
    source = tmp_path / "tall.png"
    img = Image.new("L", (400, 2000), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 60, 360, 90), fill=0)                  # text at the top: page not blank
    draw.rectangle((40, 1800, 49, 1805), fill=0)               # a tiny message in the last strip
    img.save(source)
    strips = pages.cut_strips(source, tmp_path / "precut")
    assert len(strips) == 3 and guards.is_blank(strips[2][0])  # premise: that strip alone is "blank"
    engine = ScriptedEngine(_strip_answers({
        1: "<|det|>text [10, 70, 990, 120]<|/det|>nahoře",
        3: "<|det|>text [10, 660, 300, 680]<|/det|>Ahoj"}))
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    names = {c["name"] for c in engine.calls}
    assert names == {f"page_0000_strip{n}.png" for n in (1, 3)}   # strip 2 has no ink at all
    assert [b.text for b in page.blocks] == ["nahoře", "Ahoj"]
    assert page.warnings == []


def test_a_pure_background_strip_is_not_read(no_dicts, tmp_path):
    source = tmp_path / "tall.png"
    img = Image.new("L", (400, 2000), 255)
    ImageDraw.Draw(img).rectangle((40, 60, 360, 90), fill=0)    # text only at the very top
    for x, y in ((100, 1000), (300, 1300), (200, 1700)):
        img.putpixel((x, y), 0)                                 # speckles are not ink
    img.save(source)
    engine = ScriptedEngine(lambda image, mode: "<|det|>text [10, 10, 990, 60]<|/det|>nahoře")
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert [c["name"] for c in engine.calls] == ["page_0000_strip1.png"]
    assert [b.text for b in page.blocks] == ["nahoře"]


def test_strips_without_any_ink_give_an_empty_reading(no_dicts, tmp_path):
    source = tmp_path / "white.png"
    Image.new("L", (400, 2000), 255).save(source)
    engine = ScriptedEngine()
    reading = process._read_strips(engine, source, ProcessOptions(language="cs"),
                                   tmp_path / "scratch", None, None)
    assert engine.calls == []
    assert reading.blocks == [] and reading.warnings == ["empty"]


def test_repeated_lines_inside_one_strip_are_all_kept(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    engine = ScriptedEngine(_strip_answers({1: "<|det|>text [10, 100, 990, 130]<|/det|>Ano\n"
                                               "<|det|>text [10, 200, 990, 230]<|/det|>Ano"}))
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert [b.text for b in page.blocks] == ["Ano", "Ano"]
    assert page.warnings == []          # empty neighbouring strips do not mark the page


def test_a_line_across_a_strip_edge_is_kept_once(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    strips = pages.cut_strips(source, tmp_path / "precut")
    (_p1, top1, bottom1), (_p2, top2, bottom2) = strips[0], strips[1]
    y1, y2 = bottom1 - 20, bottom1 + 30          # starts in the overlap, runs past strip 1's end
    assert top2 <= y1 < bottom1 < y2
    cut = round((y1 - top1) / (bottom1 - top1) * 999)
    s1 = round((y1 - top2) / (bottom2 - top2) * 999)
    s2 = round((y2 - top2) / (bottom2 - top2) * 999)
    engine = ScriptedEngine(_strip_answers({
        1: f"<|det|>text [10, {cut}, 990, 999]<|/det|>přes okraj",        # only its top half
        2: f"<|det|>text [10, {s1}, 990, {s2}]<|/det|>přes okraj"}))       # the whole line
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert [b.text for b in page.blocks] == ["přes okraj"]
    assert abs(page.blocks[0].box[1] - y1 / 2000 * 999) <= 2


def test_a_tall_image_with_no_text_in_any_strip_is_empty(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    engine = ScriptedEngine(lambda image, mode: "")
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert page.blocks == []
    assert "empty" in page.warnings


def test_a_timed_out_strip_ends_the_page(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    engine = ScriptedEngine(lambda image, mode: _result(
        "<|det|>text [10, 10, 990, 60]<|/det|>začátek", timed_out=True))
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert [c["name"] for c in engine.calls] == ["page_0000_strip1.png"]
    assert "time_limit" in page.warnings and [b.text for b in page.blocks] == ["začátek"]


# ---- final review C1: a U+FFFE line-end hyphen in a PDF text layer ----------------------------

class _FakeTextPage:
    def __init__(self, text):
        self.text = text

    def get_text_range(self):
        return self.text

    def close(self):
        pass


class _FakePdfPage:
    def __init__(self, text):
        self.text = text

    def get_textpage(self):
        return _FakeTextPage(self.text)


def test_text_layer_hyphen_from_pdfium_is_joined_by_the_dictionary(tiny_dicts, tmp_path):
    from tests.pdf_fixtures import make_text_pdf
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["x"]])
    layer = pages._text_layer(_FakePdfPage("Rostlina je kaktu\ufffesovitých a roste."))
    source = PageSource(index=0, kind="born_digital", text_layer=layer)
    page = process_page(pdf, source, ScriptedEngine(), ProcessOptions(language="cs", dpi=50),
                        tmp_path / "scratch")
    block = page.blocks[0]
    assert block.text == "Rostlina je kaktusovitých a roste."
    assert [(f.kind, f.original) for f in block.flags] == [("repaired", "kaktu-\nsovitých")]


# ---- final review I1: default install (Czech dictionary only) with language "auto" -------------

@pytest.fixture
def cs_only(tiny_dicts):
    from owlocr.pipeline import spellcheck
    for suffix in (".aff", ".dic"):
        (tiny_dicts / f"en_US{suffix}").unlink()
    spellcheck._reset_cache()
    assert spellcheck.available("cs") and not spellcheck.available("en")
    return tiny_dicts


def test_auto_language_with_only_czech_installed_still_turns_an_upside_down_page(cs_only,
                                                                                  tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)
    engine = ScriptedEngine()
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="auto"), scratch)
    assert page.rotation_applied == 270
    assert process.W_ROTATED in page.warnings
    assert page.blocks[0].text.startswith("Rostlina je velký strom")


def test_low_hit_rate_czech_page_with_only_czech_installed_gets_czech_flags(cs_only, tmp_path):
    source = _text_image(tmp_path / "page.png")
    text = "<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je xqzt wvpl krrt."
    page = process_page(source, IMAGE_PAGE, ScriptedEngine(lambda image, mode: text),
                        ProcessOptions(language="auto"), tmp_path / "scratch")
    assert [(f.kind, f.original) for f in page.blocks[0].flags] == [
        ("suspicious", "xqzt"), ("suspicious", "wvpl"), ("suspicious", "krrt")]
