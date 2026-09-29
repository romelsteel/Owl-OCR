"""Checks before and after OCR (design 7.2, 7.3). Plan A: blank page and runaway output.
Plan C adds looks_sideways, dictionary_hit_rate and best_rotation to this file."""
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from owlocr.pipeline import spellcheck

BLANK_DARK_SHARE = 0.002          # fewer than 0.2 % ink pixels = blank
DARK_BELOW_PAPER = 80             # "dark" = at least this much darker than the paper, on normal (bright) paper
_MIN_DARK_BELOW_PAPER = 40        # the ink threshold never drops below this, even on very dark paper
RUNAWAY_MIN_CHARS = 5000
RUNAWAY_RATIO = 0.05              # whole text compresses to under 5 %
_WINDOW = 1000                    # trim_runaway looks at the text in windows of this size
_WINDOW_RATIO = 0.25              # a window compressing under 25 % is repetition


def _dark_threshold(paper: int) -> int:
    """How far (in either direction) a pixel must be from the paper to count as ink. Scales down
    with the paper's own brightness: `DARK_BELOW_PAPER` (80) on normal bright paper (>=160), down
    to `_MIN_DARK_BELOW_PAPER` (40) on dark paper, never below that floor. A false "blank" silently
    loses text, while a false "not blank" only costs one extra OCR run, so this errs toward
    catching ink rather than toward a wide, safe-looking margin."""
    return max(_MIN_DARK_BELOW_PAPER, min(DARK_BELOW_PAPER, paper // 2))


def ink_pixels(image: Path) -> tuple[int, int]:
    """(ink pixels, all pixels) after a 3 px median filter (which removes speckles), counted the
    way is_blank counts them (see there)."""
    with Image.open(image) as im:
        gray = im.convert("L").filter(ImageFilter.MedianFilter(3))
    histogram = gray.histogram()
    pixels = gray.width * gray.height
    seen, paper = 0, 255
    for level, count in enumerate(histogram):
        seen += count
        if seen * 2 >= pixels:
            paper = level
            break
    threshold = _dark_threshold(paper)
    ink = sum(count for level, count in enumerate(histogram) if abs(level - paper) >= threshold)
    return ink, pixels


def is_blank(image: Path) -> bool:
    """Fewer than 0.2 % ink pixels after a 3 px median filter (which removes speckles).
    Ink is measured against the paper (the median brightness), not against a fixed 128, and it
    may be darker OR lighter than the paper (dark text on light paper, or light text on a dark
    background such as a photographed dark-mode screen): a pixel counts once its brightness is
    at least `_dark_threshold(paper)` levels away from the paper's, in either direction. That
    threshold scales down with the paper itself (see `_dark_threshold`), because a fixed,
    darker-only threshold would call a page full of text blank whenever the paper is dim or dark
    (median below ~81 clips the old darker-only cutoff to 0), and a fixed threshold that is too
    high for dim paper misses real, but lower-contrast, ink."""
    ink, pixels = ink_pixels(image)
    return ink < BLANK_DARK_SHARE * pixels


def _ratio(text: str) -> float:
    data = text.encode("utf-8")
    return len(zlib.compress(data, 9)) / max(len(data), 1)


def is_runaway(text: str, hit_token_cap: bool) -> bool:
    if hit_token_cap:
        return True
    return len(text) > RUNAWAY_MIN_CHARS and _ratio(text) < RUNAWAY_RATIO


def trim_runaway(text: str) -> str:
    """Keep the text up to where it starts repeating itself. The text is cut into windows; the
    repetition starts at the first window from which every later window is repetitive."""
    windows = [text[i:i + _WINDOW] for i in range(0, len(text), _WINDOW)]
    repetitive = []
    for window in windows:
        if len(window) < _WINDOW // 5 and repetitive:
            repetitive.append(repetitive[-1])        # a short tail says nothing on its own
        else:
            repetitive.append(_ratio(window) < _WINDOW_RATIO)
    start = len(windows)
    while start > 0 and repetitive[start - 1]:
        start -= 1
    if start == len(windows):
        return text                                  # no repetition at the end
    if start == 0:
        return text[:_WINDOW // 5].rstrip()          # all of it loops: keep the beginning
    cut = start * _WINDOW
    head = text[:cut]
    newline = head.rfind("\n")
    if newline > cut - _WINDOW // 2:
        head = head[:newline]
    return head.rstrip()


# ---- plan C: orientation ---------------------------------------------------------------------

ROTATIONS = (0, 90, 180, 270)   # clockwise, as Page.rotation_applied (agreed with plan B)
SIDEWAYS_RATIO = 3.0            # the column profile is this many times more varied than the rows
INK_BELOW_BACKGROUND = 0.25     # ink = a quarter of the ink-to-paper range darker than around it
_MIN_CONTRAST = 8               # grey levels between ink and paper; less = an even, empty page
_MIN_INK = 0.001


def rotate_image(image: Path, degrees: int, out: Path) -> Path:
    """Save `image` turned CLOCKWISE by `degrees` (0, 90, 180, 270) to `out`.

    Same convention as Page.rotation_applied: plan B reproduces the read image with
    Image.rotate(-rotation_applied, expand=True)."""
    with Image.open(image) as img:
        img.load()
        rotated = img if degrees % 360 == 0 else img.rotate(-degrees, expand=True)
        rotated.save(out)
    return out


def _profile_variation(values: np.ndarray) -> float:
    mean = float(values.mean())
    return 0.0 if mean == 0 else float(values.var()) / (mean * mean)


def looks_sideways(image: Path) -> bool:
    """True when the text lines seem to run vertically (design 7.2).

    The page is first normalised against its own brightness (1st percentile = ink, median =
    paper), so grey, low-contrast scans behave like clean ones. Ink = pixels clearly darker than
    their neighbourhood, so a dark background around a photo of a page does not count. Upright
    text makes the row profile of ink vary strongly (lines and gaps) and the column profile flat;
    sideways text does the opposite.
    """
    with Image.open(image) as img:
        grey = img.convert("L")
    grey.thumbnail((1000, 1000))
    pixels = np.asarray(grey, dtype=np.float64)
    ink_level, paper = np.percentile(pixels, 1), np.percentile(pixels, 50)
    if paper - ink_level < _MIN_CONTRAST:
        return False
    norm = np.clip((pixels - ink_level) / (paper - ink_level), 0.0, 1.5)
    as_image = Image.fromarray(np.uint8(np.round(norm / 1.5 * 255)))
    background = np.asarray(as_image.filter(ImageFilter.BoxBlur(15)), dtype=np.float64) / 255 * 1.5
    ink = (norm < background - INK_BELOW_BACKGROUND).astype(np.float64)
    if ink.mean() < _MIN_INK:
        return False
    rows = _profile_variation(ink.mean(axis=1))
    cols = _profile_variation(ink.mean(axis=0))
    return cols > SIDEWAYS_RATIO * max(rows, 1e-9)


PROBE_TOKENS = 120              # design 7.3: probes read only the start of the page
PROBE_TIME_LIMIT_S = 60.0
ROTATION_MARGIN = 0.15          # a turned probe must beat probe 0 by this much (final review M7)


def dictionary_hit_rate(text: str, language: str) -> float:
    """Share of the words the dictionary knows; 1.0 without a dictionary, 0.0 without words."""
    rate = spellcheck._hit_rate(text, language)
    return 1.0 if rate is None else rate


def best_rotation(image: Path, engine, language: str) -> int:
    """Read the image in all four orientations with a short Fast-mode probe and return the
    clockwise rotation (0, 90, 180, 270) whose text the dictionary knows best.
    Without a dictionary no probe is made and 0 is returned. A cancelled or timed-out probe ends
    the probing and returns 0 ("keep the page as it is", ruling R3); EngineError is not caught.
    A turn is returned only when its hit rate beats probe 0 (the page as it is) by at least
    ROTATION_MARGIN, so a noise win does not cost a full second reading (final review M7)."""
    from owlocr.pipeline.parse import parse_raw   # local: parse may import guards

    if not spellcheck.available(language):
        return 0
    best, best_rate, upright_rate = 0, -1.0, 0.0
    for degrees in ROTATIONS:
        probe = rotate_image(image, degrees, image.with_name(f"{image.stem}_probe{degrees}.png"))
        try:
            result = engine.ocr_page(probe, "fast", max_new_tokens=PROBE_TOKENS,
                                     time_limit_s=PROBE_TIME_LIMIT_S)
        finally:
            probe.unlink(missing_ok=True)
        if result.cancelled or result.timed_out:
            return 0
        text = "\n".join(block.text for block in parse_raw(result.text))
        rate = dictionary_hit_rate(text, language)
        if degrees == 0:
            upright_rate = rate
        if rate > best_rate:
            best, best_rate = degrees, rate
    return best if best_rate - upright_rate >= ROTATION_MARGIN - 1e-9 else 0   # float slack
