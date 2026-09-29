"""Plan C: searchable PDF export (design 11). Text is checked by extracting it with pypdfium2."""
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas

from owlocr.export.searchable_pdf import export_searchable_pdf
from owlocr.pipeline.document import Block, Document, Page

PAGES = Path(__file__).parent / "fixtures" / "pages"
SENTENCE = "Účet byl uhrazen pojišťovnou v Žďáru, děkujeme."
TABLE = "<table><tr><td>Jméno</td><td>Obec</td></tr><tr><td>Řehoř</td><td>Třebíč</td></tr></table>"


def _block(label, box, text):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def _page(index=0, rotation=0, source="ocr", blocks=None):
    blocks = blocks if blocks is not None else [
        _block("title", (100, 60, 500, 90), "Lékařská zpráva"),
        _block("text", (100, 100, 900, 200), SENTENCE),
        _block("table", (100, 300, 900, 400), TABLE),
        _block("image", (100, 500, 400, 700), ""),
    ]
    return Page(index=index, source=source, mode="quality", width_px=1654, height_px=2339,
                rotation_applied=rotation, blocks=blocks, raw="", warnings=[], seconds=1.0)


def _doc(source: Path, pages):
    return Document(source_path=str(source), engine_id="unlimited_ocr", engine_revision="x",
                    app_version="0.1.0", created="2026-09-28T10:00:00", pages=pages)


def _scan_pdf(path: Path, image: Path, pages: int = 1, rotate: int = 0) -> Path:
    c = rl_canvas.Canvas(str(path), pagesize=(595.28, 841.89))
    for _ in range(pages):
        c.drawImage(str(image), 0, 0, 595.28, 841.89)
        c.showPage()
    c.save()
    if rotate:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for page in pdf.pages:
                page.Rotate = rotate
            pdf.save(path)
    return path


def _text(pdf_path: Path, index: int = 0) -> str:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return pdf[index].get_textpage().get_text_range()
    finally:
        pdf.close()


def _char_centre(pdf_path: Path, needle: str, index: int = 0) -> tuple[float, float, float, float]:
    """(x, y, width, height) of the first character of `needle` and of the MediaBox, all in PDF
    user space (unrotated; get_size() would give the displayed size of a /Rotate page)."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[index]
        textpage = page.get_textpage()
        at = textpage.get_text_range().index(needle)
        left, bottom, right, top = textpage.get_charbox(at)
        x0, y0, x1, y1 = page.get_mediabox()
        return (left + right) / 2, (bottom + top) / 2, x1 - x0, y1 - y0
    finally:
        pdf.close()


def _render(pdf_path: Path, index: int = 0) -> bytes:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return pdf[index].render(scale=0.5).to_pil().convert("L").tobytes()
    finally:
        pdf.close()


def test_czech_words_are_searchable_in_a_scanned_pdf(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert out == tmp_path / "scan.ocr.pdf"
    text = _text(out)
    for word in ("pojišťovnou", "Žďáru", "Lékařská", "Řehoř", "Třebíč"):
        assert word in text, word


def test_original_page_looks_exactly_the_same(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert _render(out) == _render(source)
    assert len(pdfium.PdfDocument(str(out))) == 1


def test_text_sits_inside_the_block_box(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    assert 0.09 * width < x < 0.2 * width             # box starts at x = 100/999
    assert (1 - 0.2) * height < y < (1 - 0.1) * height  # box spans y = 100..200 of 999, from the top


def test_only_processed_pages_get_text_and_all_pages_stay(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png", pages=3)
    out = export_searchable_pdf(_doc(source, [_page(index=1)]), source, tmp_path / "o.pdf")
    assert len(pdfium.PdfDocument(str(out))) == 3
    assert "pojišťovnou" not in _text(out, 0)
    assert "pojišťovnou" in _text(out, 1)


def test_existing_file_is_not_overwritten(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    (tmp_path / "scan.ocr.pdf").write_bytes(b"keep me")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert out == tmp_path / "scan_1.ocr.pdf"          # plan A keeps the double suffix
    assert (tmp_path / "scan.ocr.pdf").read_bytes() == b"keep me"


def test_page_with_rotate_attribute(tmp_path):
    source = _scan_pdf(tmp_path / "turned.pdf", PAGES / "01_letter_clean.png", rotate=90)
    block = _block("text", (0, 0, 500, 200), SENTENCE)   # top-left of the page as displayed
    out = export_searchable_pdf(_doc(source, [_page(blocks=[block])]), source, tmp_path / "t.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # displayed = user space turned clockwise: the displayed top-left is the user-space bottom-left
    assert x < 0.2 * width and y < 0.5 * height


def test_image_input_becomes_a_pdf_page_with_text(tmp_path):
    source = tmp_path / "letter.png"
    with Image.open(PAGES / "01_letter_clean.png") as img:
        img.save(source, dpi=(200, 200))
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "letter.ocr.pdf")
    pdf = pdfium.PdfDocument(str(out))
    width, height = pdf[0].get_size()
    pdf.close()
    with Image.open(source) as img:
        assert abs(width - img.width * 72 / 200) < 1 and abs(height - img.height * 72 / 200) < 1
    assert "pojišťovnou" in _text(out)


def test_image_read_after_rotation_puts_text_in_the_original_orientation(tmp_path):
    source = tmp_path / "sideways.png"
    with Image.open(PAGES / "09_letter_rotated_90.png") as img:
        img.save(source, dpi=(200, 200))
    block = _block("text", (0, 0, 500, 200), SENTENCE)   # top-left of the upright reading
    page = _page(rotation=90, blocks=[block])
    out = export_searchable_pdf(_doc(source, [page]), source, tmp_path / "s.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # the fixture is a letter turned 90° counter-clockwise, so it was read after a 90° clockwise
    # turn (rotation_applied = 90); the letter's top-left is the original's bottom-left corner,
    # which in PDF coordinates (y up) is the left edge, lower half
    assert x < 0.25 * width and y < 0.55 * height
    assert "pojišťovnou" in _text(out)


def test_text_layer_and_blank_pages_get_no_extra_text(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png", pages=2)
    pages = [_page(index=0, source="text_layer"), _page(index=1, source="blank", blocks=[])]
    out = export_searchable_pdf(_doc(source, pages), source, tmp_path / "o.pdf")
    assert _text(out, 0).strip() == "" and _text(out, 1).strip() == ""


def test_rotate_attribute_and_turned_reading_combine(tmp_path):
    source = _scan_pdf(tmp_path / "turned.pdf", PAGES / "01_letter_clean.png", rotate=90)
    block = _block("text", (0, 0, 500, 200), SENTENCE)
    page = _page(rotation=90, blocks=[block])        # displayed page, then turned 90° clockwise
    out = export_searchable_pdf(_doc(source, [page]), source, tmp_path / "t.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # 90° (/Rotate) + 90° (reading) = the user space turned 180°: upright top-left is the
    # user-space bottom-right corner
    assert x > 0.8 * width and y < 0.5 * height


def test_table_without_html_is_still_searchable(tmp_path):
    # ruling R4: html_table_to_rows returns [] for a table block whose text is not HTML; the
    # plain text lines must still make it into the export rather than silently disappearing.
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    block = _block("table", (100, 300, 900, 400), "Jméno Obec\nŘehoř Třebíč")
    out = export_searchable_pdf(_doc(source, [_page(blocks=[block])]), source, tmp_path / "o.pdf")
    assert "Třebíč" in _text(out)


# ---- final review M5: a failed write leaves no broken .ocr.pdf ---------------------------------

def _failing_write(real_save):
    def save(self, *args, **kwargs):
        target = args[0] if args else getattr(self, "_filename", None)
        if isinstance(target, (str, Path)):
            Path(target).write_bytes(b"%PDF-1.4 half written")
        raise OSError("disk full")
    return save


def test_failed_pdf_source_write_leaves_no_file(tmp_path, monkeypatch):
    import pytest
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    monkeypatch.setattr(pikepdf.Pdf, "save", _failing_write(pikepdf.Pdf.save))
    with pytest.raises(OSError):
        export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "out" / "scan.ocr.pdf")
    assert list((tmp_path / "out").iterdir()) == []


def test_failed_image_source_write_leaves_no_file(tmp_path, monkeypatch):
    import pytest
    source = tmp_path / "letter.png"
    with Image.open(PAGES / "01_letter_clean.png") as img:
        img.save(source, dpi=(200, 200))
    monkeypatch.setattr(rl_canvas.Canvas, "save", _failing_write(rl_canvas.Canvas.save))
    with pytest.raises(OSError):
        export_searchable_pdf(_doc(source, [_page()]), source,
                              tmp_path / "out" / "letter.ocr.pdf")
    assert list((tmp_path / "out").iterdir()) == []


# ---- final review M6: image pages never exceed the PDF limit of 14,400 pt ----------------------

def test_tall_screenshot_page_is_scaled_to_the_pdf_limit(tmp_path):
    source = tmp_path / "tall.png"
    Image.new("RGB", (1000, 20000), "white").save(source, dpi=(72, 72))
    blocks = [_block("text", (100, 100, 900, 200), SENTENCE)]
    page = Page(index=0, source="ocr", mode="quality", width_px=1000, height_px=20000,
                rotation_applied=0, blocks=blocks, raw="", warnings=[], seconds=1.0)
    out = export_searchable_pdf(_doc(source, [page]), source, tmp_path / "tall.ocr.pdf")
    pdf = pdfium.PdfDocument(str(out))
    width, height = pdf[0].get_size()
    pdf.close()
    assert abs(height - 14400) < 1 and abs(width - 1000 * 14400 / 20000) < 1
    assert "pojišťovnou" in _text(out)
    x, y, w, h = _char_centre(out, "Účet")
    assert 0.09 * w < x < 0.91 * w and (1 - 0.2) * h < y < (1 - 0.1) * h   # inside the box
