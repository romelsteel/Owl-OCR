"""One page through the whole pipeline (design 7):

    text layer usable? yes -> blocks from the text layer
                       no  -> blank? -> engine -> guards (empty, runaway) -> parse
    -> layout -> repair -> spellcheck -> cleanup -> Page

EngineError is never caught here: out of memory, a dead worker and every other engine failure
reach the caller. The caller retries (design 5.7): out of memory in Quality -> the page once more
with mode="fast" and the warning "out_of_memory_fast"; a dead worker -> restart once, read again.

Warnings written into Page.warnings (plan B shows them):
    "empty_retried"       the first reading had no text; the page was read again in the other mode
    "empty"               no text even after the retry
    "runaway"             the output repeated itself; it was cut where the repetition starts
    "time_limit"          the page hit time_limit_s; what was read so far is kept
    "cancelled"           reading was cancelled; what was read so far is kept
    "rotated"             the orientation check turned the page and read it again
"""
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from owlocr.engine.protocol import PageResult
from owlocr.pipeline import layout, repair, spellcheck
from owlocr.pipeline.document import Block, Page
from owlocr.pipeline.guards import is_blank, is_runaway, trim_runaway
from owlocr.pipeline.pages import PageSource, render_page
from owlocr.pipeline.parse import parse_raw
from owlocr.pipeline import guards

from PIL import Image

from owlocr.pipeline import pages

_NO_TEXT_LABELS = ("image", "figure")


@dataclass
class ProcessOptions:
    mode: str = "quality"
    dpi: int = 200
    use_text_layer: str = "born_digital"
    language: str = "auto"
    repairs_enabled: bool = True
    time_limit_s: float = 300.0
    max_new_tokens: int = 6000
    personal_words: frozenset[str] = frozenset()


def _use_text_layer(page: PageSource, options: ProcessOptions) -> bool:
    if not page.text_layer:
        return False
    if options.use_text_layer == "always":
        return True
    return options.use_text_layer == "born_digital" and page.kind == "born_digital"


def _text_layer_blocks(text: str) -> list[Block]:
    paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", text) if p.strip()]
    return [Block(label="text", box=None, text=p, raw_text=p, flags=[]) for p in paragraphs]


def _has_text(blocks: list[Block]) -> bool:
    return any(b.text.strip() for b in blocks if b.label not in _NO_TEXT_LABELS)


def _read(engine, png: Path, mode: str, options: ProcessOptions, on_progress, cancel) -> PageResult:
    return engine.ocr_page(png, mode, max_new_tokens=options.max_new_tokens,
                           time_limit_s=options.time_limit_s, on_progress=on_progress, cancel=cancel)


ORIENTATION_MIN_WORDS = 10       # fewer words say nothing about the orientation
ORIENTATION_MIN_RATE = 0.5       # design 7.3: under 50 % known words -> probe the other rotations
W_ROTATED = "rotated"            # warning: the post-OCR check turned the page and read it again


@dataclass
class _Reading:
    blocks: list[Block]
    raw: str
    mode: str
    warnings: list[str]
    cancelled: bool
    timed_out: bool

    @property
    def stopped(self) -> bool:
        return self.cancelled or self.timed_out


def _read_once(engine, image: Path, options: ProcessOptions, on_progress, cancel) -> _Reading:
    """Plan A's reading of one image, unchanged: no text -> once more in the other mode (not after
    cancel or time limit); warnings empty_retried, empty, time_limit, cancelled, runaway."""
    mode = options.mode
    warnings: list[str] = []
    result = _read(engine, image, mode, options, on_progress, cancel)
    stopped = result.cancelled or result.timed_out
    if not stopped and not _has_text(parse_raw(result.text)):
        warnings.append("empty_retried")
        mode = "fast" if mode == "quality" else "quality"
        result = _read(engine, image, mode, options, on_progress, cancel)
        stopped = result.cancelled or result.timed_out
        if not stopped and not _has_text(parse_raw(result.text)):
            warnings.append("empty")
    if result.timed_out:
        warnings.append("time_limit")
    if result.cancelled:
        warnings.append("cancelled")
    raw = text = result.text
    if is_runaway(text, result.hit_token_cap):
        text = trim_runaway(text)
        warnings.append("runaway")
    return _Reading(parse_raw(text), raw, mode, warnings, result.cancelled, result.timed_out)


TALL_RATIO = 3.5                 # design 7.1: taller than 3.5 x the width -> strips
STRIP_MIN_INK_PX = 20            # a strip with at most this many ink pixels is plain background


def _strip_box_to_page(box, top: int, bottom: int, height: int):
    """A 0..999 box of a strip -> a 0..999 box of the whole image (x does not change)."""
    if box is None:
        return None
    x1, y1, x2, y2 = box
    span = bottom - top

    def to_image(y: int) -> int:
        return round((top + y / 999 * span) / height * 999)

    return (x1, to_image(y1), x2, to_image(y2))


def _read_strips(engine, image: Path, options: ProcessOptions, scratch: Path,
                 on_progress, cancel) -> _Reading:
    """Design 7.1: a tall image is read as overlapping strips and the results are joined. A block
    belongs to the strip whose own zone (every overlap is split in the middle) holds the block's
    centre, so text inside an overlap is kept once; repeated lines are kept (no text is lost).
    A strip is skipped only when it has essentially no ink (at most STRIP_MIN_INK_PX pixels,
    counted like guards.is_blank): is_blank's 0.2 % share would skip a strip holding one short
    message, and the whole image already passed the blank check. A cancelled or timed-out strip
    ends the page's engine calls (plan A note 24: after a timeout the worker exits and is loaded
    again for the next page); what was read so far is kept. No text in any strip -> the warning
    "empty"; a page with text carries no "empty"/"empty_retried" from its empty strips."""
    with Image.open(image) as img:
        height = img.height
    strips = pages.cut_strips(image, scratch)
    blocks: list[Block] = []
    raws: list[str] = []
    warnings: list[str] = []
    mode = options.mode
    cancelled = timed_out = False
    for n, (path, top, bottom) in enumerate(strips):
        if guards.ink_pixels(path)[0] <= STRIP_MIN_INK_PX:
            continue                                    # plain background: nothing to read
        own_top = 0 if n == 0 else (top + strips[n - 1][2]) / 2
        own_bottom = height if n == len(strips) - 1 else (bottom + strips[n + 1][1]) / 2
        part = _read_once(engine, path, options, on_progress, cancel)
        raws.append(part.raw)
        mode = "fast" if part.mode == "fast" else mode
        warnings += [w for w in part.warnings if w not in warnings]
        timed_out = timed_out or part.timed_out
        for block in part.blocks:
            box = _strip_box_to_page(block.box, top, bottom, height)
            centre = (top + bottom) / 2 if box is None else (box[1] + box[3]) / 2 / 999 * height
            if not own_top <= centre < own_bottom:
                continue
            blocks.append(Block(block.label, box, block.text, block.raw_text, list(block.flags)))
        if part.cancelled or part.timed_out:     # cancel, or the page's time budget is spent
            cancelled = part.cancelled
            break
    if _has_text(blocks):
        warnings = [w for w in warnings if w not in ("empty", "empty_retried")]   # strips only
    elif not (cancelled or timed_out) and "empty" not in warnings:
        warnings.append("empty")                           # no strip had text: an empty page
    return _Reading(blocks, "\n".join(raws), mode, warnings, cancelled, timed_out)


def _read_image(engine, image: Path, options: ProcessOptions, scratch: Path,
                on_progress, cancel) -> _Reading:
    with Image.open(image) as img:
        width, height = img.size
    if height > TALL_RATIO * width:
        return _read_strips(engine, image, options, scratch, on_progress, cancel)
    return _read_once(engine, image, options, on_progress, cancel)


class _Relay:
    """Gives every probe of guards.best_rotation the page's on_progress and cancel, so Cancel and
    "Stop engine" also stop the probes. EngineError is not caught."""

    def __init__(self, engine, on_progress, cancel) -> None:
        self._engine = engine
        self._on_progress = on_progress
        self._cancel = cancel

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        return self._engine.ocr_page(image, mode, max_new_tokens=max_new_tokens,
                                     time_limit_s=time_limit_s,
                                     on_progress=on_progress or self._on_progress,
                                     cancel=cancel or self._cancel)


def _language(options: ProcessOptions, blocks: list[Block]) -> str:
    """The language for repairs and flags. With "auto", a detected language whose dictionary is
    missing gives way to Czech when the Czech dictionary is the only one installed (final review
    I1: a Czech page with a low hit rate would otherwise lose its Czech repairs and flags)."""
    if options.language in ("cs", "en"):
        return options.language
    detected = spellcheck.detect_language("\n".join(b.text for b in blocks))
    if not spellcheck.available(detected) and spellcheck.available("cs"):
        return "cs"
    return detected


def _orientation_language(options: ProcessOptions, language: str) -> str:
    """The language of the orientation check and the probes. With "auto" it is always one whose
    dictionary is installed (the detected one if it is, else an installed one, Czech first): an
    upside-down page's garbled words make detection guess, and the page must still be checked
    (final review I1)."""
    if options.language in ("cs", "en") or spellcheck.available(language):
        return language
    return next((other for other in ("cs", "en") if spellcheck.available(other)), language)


def _rate(blocks: list[Block], language: str) -> float:
    return guards.dictionary_hit_rate("\n".join(b.text for b in blocks), language)


def _wrong_orientation(blocks: list[Block], language: str) -> bool:
    """Design 7.3: under 50 % of the words are in the dictionary. Needs a dictionary and at
    least ORIENTATION_MIN_WORDS words to judge."""
    words = sum(len(b.text.split()) for b in blocks)
    return (spellcheck.available(language) and words >= ORIENTATION_MIN_WORDS
            and _rate(blocks, language) < ORIENTATION_MIN_RATE)


def process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> Page:
    t0 = time.perf_counter()
    png = Path(scratch) / f"page_{page.index:04d}.png"
    width, height = render_page(Path(source), page.index, options.dpi, png)
    mode: str | None = None
    rotation = 0                      # degrees clockwise applied to png before reading

    if _use_text_layer(page, options):
        kind, raw, warnings = "text_layer", page.text_layer, []
        blocks = _text_layer_blocks(raw)
        language = _language(options, blocks)
    elif is_blank(png):
        blank = Page(index=page.index, source="blank", mode=None, width_px=width, height_px=height,
                     rotation_applied=0, blocks=[], raw="", warnings=[],
                     seconds=round(time.perf_counter() - t0, 3))
        return cleanup(blank, options)
    else:
        kind, image = "ocr", png
        if guards.looks_sideways(png):             # design 7.2: turn now, 90 vs 270 decided below
            rotation = 90
            image = guards.rotate_image(png, 90, png.with_name(f"{png.stem}_r90.png"))
        reading = _read_image(engine, image, options, Path(scratch), on_progress, cancel)
        language = _language(options, reading.blocks)
        probe_language = _orientation_language(options, language)
        if not reading.stopped and _wrong_orientation(reading.blocks, probe_language):
            turn = guards.best_rotation(image, _Relay(engine, on_progress, cancel),
                                        probe_language)
            if turn and not (cancel is not None and cancel.is_set()):
                total = (rotation + turn) % 360
                turned = guards.rotate_image(png, total, png.with_name(f"{png.stem}_r{total}.png"))
                second = _read_image(engine, turned, options, Path(scratch), on_progress, cancel)
                if not second.cancelled and (_rate(second.blocks, probe_language)
                                             > _rate(reading.blocks, probe_language)):
                    reading, rotation = second, total
                    reading.warnings.append(W_ROTATED)
                    language = _language(options, reading.blocks)
        mode, raw, warnings, blocks = reading.mode, reading.raw, reading.warnings, reading.blocks

    personal = set(options.personal_words)
    blocks = layout.arrange(blocks, language)
    if options.repairs_enabled:
        blocks = [repair.repair_block(b, language, personal) for b in blocks]
    blocks = [spellcheck.flag_suspicious(b, language, personal) for b in blocks]
    if rotation in (90, 270):
        width, height = height, width             # boxes refer to the turned image
    result_page = Page(index=page.index, source=kind, mode=mode, width_px=width, height_px=height,
                       rotation_applied=rotation, blocks=blocks, raw=raw, warnings=warnings,
                       seconds=round(time.perf_counter() - t0, 3))
    return cleanup(result_page, options)


def cleanup(page: Page, options: ProcessOptions) -> Page:
    """Slot for the local cleanup add-on (design 14). A no-op in v1."""
    return page
