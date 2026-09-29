import threading

import pytest

from owlocr.engine.protocol import EngineError, PageResult
from owlocr.pipeline import process, repair
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, cleanup, process_page
from tests.conftest import PAGES, RAW
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf

LETTER_RAW = (RAW / "01_letter_clean.gundam.raw.txt").read_text(encoding="utf-8")
IMAGE_PAGE = PageSource(index=0, kind="image", text_layer=None)


def result(text: str, **changes) -> PageResult:
    values = dict(text=text, seconds=1.0, prefix_tokens=907, output_tokens=len(text) // 3,
                  hit_token_cap=False, cancelled=False, timed_out=False, peak_vram_mib=0)
    values.update(changes)
    return PageResult(**values)


class StubEngine:
    """Answers ocr_page from a list of PageResults or EngineErrors, in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0, on_progress=None, cancel=None):
        self.calls.append({"image": image, "mode": mode, "max_new_tokens": max_new_tokens,
                           "time_limit_s": time_limit_s, "on_progress": on_progress, "cancel": cancel})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_options_defaults():
    o = ProcessOptions()
    assert (o.mode, o.dpi, o.use_text_layer, o.language, o.repairs_enabled) == ("quality", 200, "born_digital", "auto", True)
    assert (o.time_limit_s, o.max_new_tokens, o.personal_words) == (300.0, 6000, frozenset())


def test_image_page_is_read(tmp_path):
    engine = StubEngine(result(LETTER_RAW))
    progress, cancel = [].append, threading.Event()
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine,
                        ProcessOptions(time_limit_s=120, max_new_tokens=4000), tmp_path,
                        on_progress=progress, cancel=cancel)
    assert (page.index, page.source, page.mode) == (0, "ocr", "quality")
    assert (page.width_px, page.height_px, page.rotation_applied) == (2480, 3508, 0)
    assert len(page.blocks) == 7 and page.blocks[0].text == "Vážená paní doktorko Šťastná,"
    assert page.raw == LETTER_RAW and page.warnings == []
    call = engine.calls[0]
    assert call["image"] == tmp_path / "page_0000.png" and call["image"].is_file()
    assert (call["mode"], call["max_new_tokens"], call["time_limit_s"]) == ("quality", 4000, 120)
    assert call["on_progress"] is progress and call["cancel"] is cancel


def test_blank_page_skips_the_engine(tmp_path):
    engine = StubEngine()
    page = process_page(PAGES / "10_blank_page.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert (page.source, page.mode, page.blocks, page.raw) == ("blank", None, [], "")
    assert engine.calls == []


def test_born_digital_pdf_uses_the_text_layer(tmp_path):
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["First paragraph line"]])
    engine = StubEngine()
    source = PageSource(index=0, kind="born_digital", text_layer="First para-\ngraph\n\nSecond one")
    page = process_page(pdf, source, engine, ProcessOptions(dpi=100), tmp_path / "scratch")
    assert engine.calls == []
    assert (page.source, page.mode, page.width_px, page.height_px) == ("text_layer", None, 850, 1100)
    assert [(b.label, b.box, b.text) for b in page.blocks] == [("text", None, "First paragraph"),
                                                               ("text", None, "Second one")]
    assert page.raw == "First para-\ngraph\n\nSecond one"


def test_text_layer_settings(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    scan_with_old_ocr = PageSource(index=0, kind="scan", text_layer="old hidden text")
    engine = StubEngine(result("<|det|>text [1, 1, 500, 100]<|/det|>fresh text"))
    page = process_page(pdf, scan_with_old_ocr, engine, ProcessOptions(), tmp_path)
    assert page.source == "ocr" and page.blocks[0].text == "fresh text"          # born_digital ignores scans
    page = process_page(pdf, scan_with_old_ocr, StubEngine(), ProcessOptions(use_text_layer="always"), tmp_path)
    assert page.source == "text_layer" and page.blocks[0].text == "old hidden text"
    digital = PageSource(index=0, kind="born_digital", text_layer="layer")
    engine = StubEngine(result("<|det|>text [1, 1, 500, 100]<|/det|>read"))
    page = process_page(pdf, digital, engine, ProcessOptions(use_text_layer="never"), tmp_path)
    assert page.source == "ocr" and len(engine.calls) == 1


@pytest.mark.parametrize("kind", ["out_of_memory", "died", "bad_image", "internal"])
def test_engine_errors_reach_the_caller(tmp_path, kind):
    """process_page never swallows EngineError; the caller (CLI, plan B runner) decides."""
    engine = StubEngine(EngineError(kind, "x"), result(LETTER_RAW))
    with pytest.raises(EngineError) as e:
        process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert e.value.kind == kind
    assert len(engine.calls) == 1


def test_empty_output_is_retried_in_the_other_mode(tmp_path):
    engine = StubEngine(result("<|det|>image [0, 0, 999, 999]<|/det|>"), result(LETTER_RAW))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert [c["mode"] for c in engine.calls] == ["quality", "fast"]
    assert page.mode == "fast" and page.warnings == ["empty_retried"] and len(page.blocks) == 7


def test_still_empty_after_retry(tmp_path):
    engine = StubEngine(result(""), result(""))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(mode="fast"), tmp_path)
    assert [c["mode"] for c in engine.calls] == ["fast", "quality"]
    assert page.warnings == ["empty_retried", "empty"] and page.blocks == []


def test_runaway_output_is_trimmed(tmp_path):
    loop = "<|det|>text [1, 1, 900, 900]<|/det|>" + "50 or greater, 70 or greater, " * 800
    engine = StubEngine(result(LETTER_RAW + "\n" + loop, hit_token_cap=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["runaway"]
    assert page.raw.endswith("or greater, ")                  # raw keeps everything that was read
    assert sum(len(b.text) for b in page.blocks) < len(LETTER_RAW) + 1000
    assert page.blocks[0].text == "Vážená paní doktorko Šťastná,"


def test_cancelled_and_timed_out_pages_keep_their_text_and_are_not_retried(tmp_path):
    engine = StubEngine(result("<|det|>text [1, 1, 9, 9]<|/det|>Vážená", cancelled=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["cancelled"] and page.blocks[0].text == "Vážená"
    engine = StubEngine(result("", timed_out=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["time_limit"] and len(engine.calls) == 1


def test_layout_runs_and_repairs_can_be_switched_off(tmp_path, monkeypatch):
    def boom(*args):
        raise AssertionError("repair must not run")

    monkeypatch.setattr(repair, "repair_block", boom)
    engine = StubEngine(result("<|det|>text [1, 1, 9, 9]<|/det|>kaktu-\nsovitých"))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine,
                        ProcessOptions(repairs_enabled=False), tmp_path)
    assert page.blocks[0].text == "kaktusovitých"
    assert page.blocks[0].raw_text == "kaktu-\nsovitých"


def test_cleanup_is_a_no_op():
    from owlocr.pipeline.document import Page
    page = Page(index=0, source="blank", mode=None, width_px=1, height_px=1, rotation_applied=0,
                blocks=[], raw="", warnings=[], seconds=0.0)
    assert cleanup(page, ProcessOptions()) is page
    assert process.cleanup is cleanup
