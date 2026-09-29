"""Searchable PDF (design 11): the original page stays untouched and every block's text is added
as invisible text (render mode 3) inside the block's box.

Uses pikepdf (MPL-2.0) and reportlab (BSD). Never PyMuPDF (AGPL). The embedded font is
DejaVu Sans (Bitstream Vera licence + public-domain changes, redistribution allowed), so Czech
letters are searchable and copyable.
"""
from __future__ import annotations

import io
import math
import re
import tempfile
from pathlib import Path

import pikepdf
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from owlocr.paths import atomic_write_file, unique_path
from owlocr.pipeline.document import Block, Document, Page
from owlocr.pipeline.pages import render_page
from owlocr.pipeline.parse import html_table_to_rows

FONT_NAME = "OwlDejaVuSans"
FONT_FILE = Path(__file__).with_name("fonts") / "DejaVuSans.ttf"
IMAGE_DPI_DEFAULT = 200
MAX_PAGE_PT = 14400.0         # PDF limit for a page side (final review M6)
_CHAR_WIDTH_EM = 0.5          # average glyph width as a share of the font size
_LINE_PITCH_EM = 1.2          # line height as a share of the font size
_TAG = re.compile(r"<[^>]*>")
_SKIP_LABELS = ("image", "figure")


def _register_font() -> None:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_FILE)))


def _block_lines(block: Block) -> list[str]:
    """The block's text as lines: HTML tables row by row, everything else (including a `table`
    block whose text is not HTML — ruling R4) as written."""
    text = block.text
    if block.label == "table" and "<t" in text.lower():
        rows = html_table_to_rows(text)
        if rows:
            return [" ".join(cell for cell in row if cell) for row in rows if any(row)]
        text = _TAG.sub(" ", re.sub(r"</tr>", "\n", text, flags=re.I))
    return [" ".join(line.split()) for line in text.split("\n") if line.strip()]


def _wrap(line: str, count: int) -> list[str]:
    """Split one line into `count` lines of similar length at spaces."""
    words = line.split()
    if count <= 1 or len(words) <= 1:
        return [line]
    target = len(line) / count
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > target and len(lines) < count - 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _fit_lines(lines: list[str], width: float, height: float) -> tuple[list[str], float]:
    """Estimate the text lines inside a box and the font size (design 11: one line per estimated
    text line, font size fitted to the box)."""
    if len(lines) == 1:
        chars = max(len(lines[0]), 1)
        size = math.sqrt(width * height / (chars * _CHAR_WIDTH_EM * _LINE_PITCH_EM))
        count = max(1, min(round(height / (size * _LINE_PITCH_EM)), len(lines[0].split())))
        lines = _wrap(lines[0], count)
    size = height / (len(lines) * _LINE_PITCH_EM)
    return lines, max(1.0, min(size, 400.0))


def _frame_matrix(rotation: int, width: float, height: float) -> tuple[float, ...]:
    """Matrix from the upright frame (the image the model read, in points, y up) back to the
    unrotated page frame of `width` x `height` points, when the read image was the page turned
    `rotation` degrees CLOCKWISE (the convention of Page.rotation_applied)."""
    rotation %= 360
    if rotation == 90:
        return (0, 1, -1, 0, width, 0)
    if rotation == 180:
        return (-1, 0, 0, -1, width, height)
    if rotation == 270:
        return (0, -1, 1, 0, 0, height)
    return (1, 0, 0, 1, 0, 0)


def _draw_page_text(c, page: Page, rotation: int, width: float, height: float,
                    offset: tuple[float, float] = (0.0, 0.0)) -> None:
    """Draw every block of `page` as invisible text onto canvas `c` whose page is width x height
    points; the read image was that page turned `rotation` degrees clockwise."""
    upright_w, upright_h = (height, width) if rotation % 180 == 90 else (width, height)
    c.saveState()
    c.translate(*offset)
    c.transform(*_frame_matrix(rotation, width, height))
    for block in page.blocks:
        if block.box is None or block.label in _SKIP_LABELS:
            continue
        lines = _block_lines(block)
        if not lines:
            continue
        x1, y1, x2, y2 = block.box
        left = x1 / 999 * upright_w
        right = x2 / 999 * upright_w
        top = upright_h - y1 / 999 * upright_h
        bottom = upright_h - y2 / 999 * upright_h
        box_w, box_h = max(right - left, 1.0), max(top - bottom, 1.0)
        lines, size = _fit_lines(lines, box_w, box_h)
        pitch = box_h / len(lines)
        for n, line in enumerate(lines):
            natural = pdfmetrics.stringWidth(line, FONT_NAME, size)
            text = c.beginText()
            text.setTextRenderMode(3)
            text.setFont(FONT_NAME, size)
            if natural > 0:
                text.setHorizScale(max(1.0, min(1000.0, 100.0 * box_w / natural)))
            text.setTextOrigin(left, top - (n + 1) * pitch + 0.2 * pitch)
            text.textOut(line)
            c.drawText(text)
    c.restoreState()


def _overlay_for_pdf(doc: Document, pdf: pikepdf.Pdf) -> tuple[bytes, list[int]]:
    """One overlay page per OCR page, each as large as the target page's MediaBox."""
    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pageCompression=1)
    targets = []
    for page in doc.pages:
        if page.source != "ocr" or not page.blocks or page.index >= len(pdf.pages):
            continue
        target = pdf.pages[page.index]
        mx0, my0, mx1, my1 = (float(v) for v in target.mediabox)
        cx0, cy0, cx1, cy1 = (float(v) for v in target.cropbox)
        c.setPageSize((mx1 - mx0, my1 - my0))
        page_rotate = int(target.obj.get("/Rotate", 0)) % 360
        # the rendered page image shows the crop box turned clockwise by /Rotate, and the model
        # read that image turned clockwise by rotation_applied
        rotation = (page.rotation_applied + page_rotate) % 360
        _draw_page_text(c, page, rotation, cx1 - cx0, cy1 - cy0, (cx0 - mx0, cy0 - my0))
        c.showPage()
        targets.append(page.index)
    c.save()
    return buffer.getvalue(), targets


def _stamp(target: pikepdf.Page, form: pikepdf.Object) -> None:
    """Draw `form` over the page at the MediaBox origin, scale 1. pikepdf's Page.add_overlay is
    not used: on a page with /Rotate it turned the layer a second time (seen while testing), and
    _overlay_for_pdf has already taken /Rotate into account."""
    name = target.add_resource(form, pikepdf.Name.XObject)
    x0, y0 = float(target.mediabox[0]), float(target.mediabox[1])
    target.contents_add(b"q\n", prepend=True)
    target.contents_add(b"\nQ\nq 1 0 0 1 %.4f %.4f cm %s Do Q\n" % (x0, y0, name.unparse()),
                        prepend=False)
    target.contents_coalesce()


def _export_pdf_source(doc: Document, source: Path, out: Path) -> Path:
    with pikepdf.open(source) as pdf:
        overlay_bytes, targets = _overlay_for_pdf(doc, pdf)
        if targets:
            with pikepdf.open(io.BytesIO(overlay_bytes)) as overlay:
                for n, index in enumerate(targets):
                    _stamp(pdf.pages[index], pdf.copy_foreign(overlay.pages[n].as_form_xobject()))
        pdf.save(out)
    return out


def _image_dpi(image: Image.Image) -> float:
    dpi = image.info.get("dpi")
    try:
        value = float(dpi[0]) if dpi else 0.0
    except (TypeError, ValueError, IndexError):
        value = 0.0
    return value if value >= 50 else IMAGE_DPI_DEFAULT


def _export_image_source(doc: Document, source: Path, out: Path) -> Path:
    with Image.open(source) as original:
        dpi = _image_dpi(original)
    c = rl_canvas.Canvas(str(out), pageCompression=1)
    with tempfile.TemporaryDirectory() as tmp:
        for page in doc.pages:
            png = Path(tmp) / f"page_{page.index:04d}.png"
            pixels_w, pixels_h = render_page(source, page.index, IMAGE_DPI_DEFAULT, png)
            width, height = pixels_w * 72 / dpi, pixels_h * 72 / dpi
            # a tall screenshot at 72 dpi can exceed the PDF page limit: scale the page (and so
            # its text layer, which is drawn in the same width x height) down, keeping the aspect
            scale = min(1.0, MAX_PAGE_PT / max(width, height))
            width, height = width * scale, height * scale
            c.setPageSize((width, height))
            c.drawImage(str(png), 0, 0, width, height)
            if page.source == "ocr":
                _draw_page_text(c, page, page.rotation_applied, width, height)
            c.showPage()
        c.save()
    return out


def export_searchable_pdf(doc: Document, source: Path, out: Path) -> Path:
    _register_font()
    out = unique_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write = _export_pdf_source if source.suffix.lower() == ".pdf" else _export_image_source
    atomic_write_file(out, lambda tmp: write(doc, source, tmp))      # final review M5
    return out
