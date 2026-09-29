from PIL import Image, ImageDraw

from owlocr.pipeline import pages
from owlocr.pipeline.pages import PageSource
from tests.conftest import PAGES
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf


def test_suffixes():
    assert pages.IMAGE_SUFFIXES == (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    assert pages.SUPPORTED_SUFFIXES == pages.IMAGE_SUFFIXES + (".pdf",)


def test_born_digital_pdf(tmp_path):
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["Hello world", "second line"], ["Page two"]])
    assert pages.count_pages(pdf) == 2
    listed = pages.list_pages(pdf)
    assert [p.kind for p in listed] == ["born_digital", "born_digital"]
    assert listed[0] == PageSource(index=0, kind="born_digital", text_layer="Hello world\nsecond line")
    assert listed[1].text_layer == "Page two"


def test_scanned_pdf(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf", pages=3)
    assert pages.count_pages(pdf) == 3
    listed = pages.list_pages(pdf)
    assert [(p.index, p.kind, p.text_layer) for p in listed] == [(0, "scan", None), (1, "scan", None), (2, "scan", None)]


def test_render_pdf_page_at_dpi(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf", pages=2)
    size = pages.render_page(pdf, 1, 200, tmp_path / "out" / "p1.png")
    assert size == (1700, 2200)                     # 8.5 x 11 inch at 200 dpi
    with Image.open(tmp_path / "out" / "p1.png") as im:
        assert im.size == size and im.mode == "RGB"


def test_image_file(tmp_path):
    src = PAGES / "08_screenshot.png"
    assert pages.count_pages(src) == 1
    assert pages.list_pages(src) == [PageSource(index=0, kind="image", text_layer=None)]
    assert pages.render_page(src, 0, 200, tmp_path / "p.png") == (1280, 720)


def test_exif_orientation_is_applied(tmp_path):
    im = Image.new("RGB", (400, 100), "white")
    exif = im.getexif()
    exif[0x0112] = 6                                 # rotate 90 degrees clockwise to display
    im.save(tmp_path / "photo.jpg", exif=exif)
    assert pages.render_page(tmp_path / "photo.jpg", 0, 200, tmp_path / "p.png") == (100, 400)


def test_multipage_tiff_and_transparency(tmp_path):
    frames = [Image.new("L", (50, 60), 255), Image.new("L", (70, 80), 0)]
    frames[0].save(tmp_path / "two.tif", save_all=True, append_images=frames[1:])
    assert pages.count_pages(tmp_path / "two.tif") == 2
    assert [p.index for p in pages.list_pages(tmp_path / "two.tif")] == [0, 1]
    assert pages.render_page(tmp_path / "two.tif", 1, 200, tmp_path / "f1.png") == (70, 80)
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(tmp_path / "clear.png")
    pages.render_page(tmp_path / "clear.png", 0, 200, tmp_path / "c.png")
    with Image.open(tmp_path / "c.png") as im:
        assert im.getpixel((5, 5)) == (255, 255, 255)


def test_16bit_grayscale_tiff_scales_instead_of_clipping(tmp_path):
    im = Image.new("I;16", (200, 200), 60000)                # bright paper
    ImageDraw.Draw(im).rectangle([50, 50, 150, 150], fill=2000)   # dark ink
    im.save(tmp_path / "scan16.tif")
    pages.render_page(tmp_path / "scan16.tif", 0, 200, tmp_path / "p.png")
    with Image.open(tmp_path / "p.png") as out:
        paper = out.getpixel((10, 10))
        ink = out.getpixel((100, 100))
        assert paper != (255, 255, 255) or ink != (255, 255, 255)   # not clipped to pure white
        assert ink[0] < paper[0]                              # ink clearly darker than paper


def test_reopened_16bit_tiff_scales_instead_of_clipping(tmp_path):
    # Building with plain "I;16" and saving is not enough to exercise the byte-order-suffixed
    # modes: on Pillow 12.3.0, Image.new("I;16", ...) round-trips through disk as plain "I;16"
    # again, so a test built that way passes even against the old exact-match ("I;16") code.
    # Building the image as "I;16B" (big-endian) directly does reopen as "I;16B" -- confirmed
    # both by the re-reviewer and by checking it here -- which is the mode render_page actually
    # sees for a real-world 16-bit TIFF (Pillow does not guarantee which of I;16/I;16B/I;16L/I;16N
    # a given file round-trips as; it depends on the file's own byte order).
    path = tmp_path / "scan16.tif"
    im = Image.new("I;16B", (200, 200), 60000)                # bright paper, big-endian
    ImageDraw.Draw(im).rectangle([50, 50, 150, 150], fill=2000)   # dark ink
    im.save(path)
    with Image.open(path) as reopened:
        assert reopened.mode == "I;16B"
    pages.render_page(path, 0, 200, tmp_path / "p.png")
    with Image.open(tmp_path / "p.png") as out:
        paper = out.getpixel((10, 10))
        ink = out.getpixel((100, 100))
        assert paper != (255, 255, 255) or ink != (255, 255, 255)   # not clipped to pure white
        assert ink[0] < paper[0]                              # ink clearly darker than paper


def test_find_inputs(tmp_path):
    (tmp_path / "a" / "deep").mkdir(parents=True)
    wanted = [tmp_path / "a" / "B.PNG", tmp_path / "a" / "deep" / "c.pdf", tmp_path / "z.jpg"]
    for p in wanted:
        p.write_bytes(b"x")
    (tmp_path / "a" / "notes.txt").write_text("x")
    (tmp_path / "a" / "deep" / "c.ocr.pdf").write_bytes(b"x")
    found = pages.find_inputs([tmp_path / "a", tmp_path / "z.jpg", tmp_path / "z.jpg", tmp_path / "missing.png"])
    assert found == sorted((p.resolve() for p in wanted), key=lambda p: str(p).lower())


def test_find_inputs_skips_the_image_crops_of_a_markdown_export(tmp_path):
    from owlocr.export.markdown import export_markdown
    from owlocr.pipeline.document import Block
    from tests.samples import sample_document
    folder = tmp_path / "docs"
    folder.mkdir()
    pdf = make_scan_pdf(folder / "My scan (1).pdf")
    doc = sample_document()
    doc.source_path = str(pdf)
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [Block(label="figure", box=(0, 0, 499, 499), text="", raw_text="", flags=[])]
    export_markdown(doc, folder / "My scan (1).md")
    assert list((folder / "My scan (1)_images").glob("*.png"))            # crops were written
    (tmp_path / "photos_images").mkdir()                                  # a user's own folder: no .md
    (tmp_path / "photos_images" / "cat.png").write_bytes(b"x")
    assert pages.find_inputs([folder]) == [pdf.resolve()]
    assert pages.find_inputs([tmp_path]) == sorted(
        [pdf.resolve(), (tmp_path / "photos_images" / "cat.png").resolve()], key=lambda p: str(p).lower())


# ---- final review C1: pypdfium2 gives a line-end hyphen as U+FFFE -----------------------------

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


def test_line_end_hyphen_of_a_pdf_text_layer_becomes_a_hyphen_and_a_line_break(tmp_path):
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["Je to rostlina kaktu-", "sovitych a roste."]])
    text = pages.list_pages(pdf)[0].text_layer
    assert "\ufffe" not in text
    assert text == "Je to rostlina kaktu-\nsovitych a roste."


def test_xml_invalid_characters_are_removed_from_the_text_layer():
    text = pages._text_layer(_FakePdfPage("Dub\x01 a\x0b buk\uffff\x1f.\tStrom\r\nroste"))
    assert text == "Dub a buk.\tStrom\nroste"
    assert pages._text_layer(_FakePdfPage("kaktu\ufffesovitých")) == "kaktu-\nsovitých"
