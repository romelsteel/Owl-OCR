"""Input files -> pages (design 7.1). PDFs are read with pypdfium2 (never PyMuPDF: AGPL).

A PDF page is a 'scan' when one image covers at least 80 % of the page, else 'born_digital'.
Image files are 'image' pages; a multi-page TIFF has one page per frame.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + (".pdf",)
SCAN_COVERAGE = 0.80
_OUTPUT_SUFFIXES = (".ocr.pdf",)          # our own searchable PDFs are never inputs
# pypdfium2 gives a hyphen at the end of a line as U+FFFE and drops the line break
_PDFIUM_LINE_HYPHEN = '\ufffe'
# characters XML (and so Word) does not allow: C0 controls except tab/LF/CR, U+FFFE, U+FFFF
XML_INVALID = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')


def xml_safe(text: str) -> str:
    """`text` without the characters XML does not allow."""
    return XML_INVALID.sub("", text)


@dataclass
class PageSource:
    index: int
    kind: str                  # 'scan' | 'born_digital' | 'image'
    text_layer: str | None     # text of the PDF page, if any


def _is_pdf(path: Path) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def count_pages(path: Path) -> int:
    path = Path(path)
    if _is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    with Image.open(path) as im:
        return getattr(im, "n_frames", 1)


def _image_coverage(page) -> float:
    left, bottom, right, top = page.get_bbox()
    area = max((right - left) * (top - bottom), 1e-6)
    best = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        l, b, r, t = obj.get_bounds()
        w = max(0.0, min(r, right) - max(l, left))
        h = max(0.0, min(t, top) - max(b, bottom))
        best = max(best, w * h / area)
    return best


def _text_layer(page) -> str | None:
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_range()
    finally:
        textpage.close()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # a line-end hyphen becomes "-" plus the lost line break, so dehyphenation decides (C1)
    text = xml_safe(text.replace(_PDFIUM_LINE_HYPHEN, "-\n")).strip()
    return text or None


def list_pages(path: Path) -> list[PageSource]:
    path = Path(path)
    if not _is_pdf(path):
        return [PageSource(index=i, kind="image", text_layer=None) for i in range(count_pages(path))]
    pdf = pdfium.PdfDocument(str(path))
    pages = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                kind = "scan" if _image_coverage(page) >= SCAN_COVERAGE else "born_digital"
                pages.append(PageSource(index=i, kind=kind, text_layer=_text_layer(page)))
            finally:
                page.close()
    finally:
        pdf.close()
    return pages


def _to_8bit_grayscale(im: Image.Image) -> Image.Image:
    """I;16/I/F images hold values far outside 0..255; convert("RGB") on them clips instead of
    scaling, so a 16-bit page with real content (e.g. paper near 60000, ink near 2000) renders as
    solid white. Scale to 8 bits first: I;16 (in any byte order: I;16B/I;16L/I;16N, which is how
    Pillow opens big/little-endian and native 16-bit TIFFs) is a fixed /256 (its native range is
    0..65535) — the byte-order variants only differ in on-disk storage, so convert("I") first to
    get a plain machine-native int32 image the /256 step below can read. I and F have no fixed
    range, so they are scaled from the image's own min/max, clamped into 0..255."""
    if im.mode.startswith("I;16"):
        im = im.convert("I")
        return im.point(lambda v: v / 256, mode="L")
    low, high = im.getextrema()
    span = max(high - low, 1)
    # every pixel is within [low, high] by definition, so this affine map already lands in
    # 0..255; .point(..., mode="L") itself clamps/truncates the result to that range.
    return im.point(lambda v: (v - low) * 255 / span, mode="L")


def _flatten(im: Image.Image) -> Image.Image:
    """RGB on white; transparent areas become paper, not black."""
    if im.mode.startswith("I;16") or im.mode in ("I", "F"):
        im = _to_8bit_grayscale(im)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        background = Image.new("RGB", im.size, "white")
        background.paste(im, mask=im.getchannel("A"))
        return background
    return im.convert("RGB")


def render_page(path: Path, index: int, dpi: int, out_png: Path) -> tuple[int, int]:
    """Write page `index` as a PNG. PDFs are rendered at `dpi`; images keep their pixels and get
    their EXIF orientation applied. Returns (width, height) in pixels."""
    path, out_png = Path(path), Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if _is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            page = pdf[index]
            try:
                image = page.render(scale=dpi / 72).to_pil()
            finally:
                page.close()
        finally:
            pdf.close()
    else:
        with Image.open(path) as im:
            im.seek(index)
            image = ImageOps.exif_transpose(im)
    image = _flatten(image)
    image.save(out_png, "PNG")
    return image.width, image.height


def _is_export_crop(p: Path) -> bool:
    """An image cut out by the Markdown export: it sits in <stem>_images/ next to <stem>.md."""
    folder = p.parent
    return (folder.name.lower().endswith("_images")
            and folder.with_name(folder.name[:-len("_images")] + ".md").is_file())


def find_inputs(paths: list[Path]) -> list[Path]:
    """Files as given plus folders searched recursively; only supported types; sorted, no repeats.
    The app's own outputs found in a folder (.ocr.pdf, Markdown image crops) are never inputs."""
    found: set[Path] = set()
    for item in paths:
        item = Path(item)
        candidates = item.rglob("*") if item.is_dir() else [item]
        for p in candidates:
            name = p.name.lower()
            if (p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
                    and not name.endswith(_OUTPUT_SUFFIXES)
                    and not (item.is_dir() and _is_export_crop(p))):
                found.add(p.resolve())
    return sorted(found, key=lambda p: str(p).lower())


# ---- plan C: tall images (design 7.1) -------------------------------------------------------

STRIP_HEIGHT_RATIO = 2.0       # each strip is at most twice as tall as it is wide
STRIP_OVERLAP_RATIO = 0.25     # neighbouring strips share a quarter of the width in height
_MIN_OVERLAP_PX = 80


def cut_strips(image: Path, out_dir: Path) -> list[tuple[Path, int, int]]:
    """Cut a tall image into overlapping horizontal strips.

    Returns (strip png, top px, bottom px) from top to bottom; the last strip ends at the bottom
    of the image. Strips are saved into `out_dir` as <image stem>_strip<N>.png.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image) as img:
        img.load()
        width, height = img.size
        strip = max(1, round(width * STRIP_HEIGHT_RATIO))
        overlap = min(strip // 2, max(_MIN_OVERLAP_PX, round(width * STRIP_OVERLAP_RATIO)))
        result = []
        top = 0
        while True:
            bottom = min(top + strip, height)
            path = out_dir / f"{image.stem}_strip{len(result) + 1}.png"
            img.crop((0, top, width, bottom)).save(path)
            result.append((path, top, bottom))
            if bottom >= height:
                return result
            top = bottom - overlap
