from PIL import Image

from owlocr.export.markdown import export_markdown
from owlocr.pipeline.document import Block, Flag
from tests.pdf_fixtures import make_scan_pdf
from tests.samples import sample_document


def test_markdown(tmp_path):
    doc = sample_document()
    out = export_markdown(doc, tmp_path / "kniha.md")
    assert out == tmp_path / "kniha.md"
    text = out.read_text(encoding="utf-8")
    assert text == ("## Buněčné dýchání\n\n"
                    "Buňka získává energii.\n\n"
                    "| Jméno | Obec |\n|---|---|\n| Žaneta | Třebíč |\n")
    assert not (tmp_path / "kniha_images").exists()          # source PDF does not exist: no crops


def test_markdown_options(tmp_path):
    doc = sample_document()
    doc.pages[0].blocks[2].flags.append(Flag(kind="suspicious", start=0, end=5, original="Buňka", note=""))
    text = export_markdown(doc, tmp_path / "k.md", page_comments=True, keep_furniture=True,
                           suspicious_appendix=True).read_text(encoding="utf-8")
    assert text.startswith("<!-- page 1 -->\n\nKapitola 1\n\n## Buněčné dýchání")
    assert "\n\n7\n\n<!-- page 2 -->\n\n---" in text
    assert text.endswith("**Suspicious words / Podezřelá slova**\n\n- page 1: `Buňka`\n")


def block(label, text, box=(100, 100, 900, 120)):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def test_markdown_block_types(tmp_path):
    doc = sample_document()
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [
        block("title", "Velký nadpis", (100, 50, 900, 90)),              # 40 high vs 20 for a text line
        block("title", "Malý\nnadpis", (100, 100, 900, 125)),
        block("text", "Odstavec.", (100, 130, 900, 150)),
        block("list", "• první\n2) druhá\n- třetí"),
        block("formula", "$$E = mc^2$$"),
        block("image_caption", "Obr. 1  Buňka"),
        block("table_caption", "Tab. 2"),
        block("table", '<table><tr><td colspan="2">a|b</td></tr></table>'),
        block("table", "<table><tr><td>a|b</td><td>c</td></tr><tr><td>d</td></tr></table>"),
        block("footer", "zápatí"),
    ]
    text = export_markdown(doc, tmp_path / "t.md").read_text(encoding="utf-8")
    assert text == ("# Velký nadpis\n\n"
                    "## Malý nadpis\n\n"
                    "Odstavec.\n\n"
                    "- první\n- druhá\n- třetí\n\n"
                    "$$\nE = mc^2\n$$\n\n"
                    "*Obr. 1 Buňka*\n\n"
                    "*Tab. 2*\n\n"
                    '<table><tr><td colspan="2">a|b</td></tr></table>\n\n'
                    "| a\\|b | c |\n|---|---|\n| d |  |\n")


def test_markdown_cuts_images_from_the_source(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    doc = sample_document()
    doc.source_path = str(pdf)
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [block("text", "Nad obrázkem."), block("figure", "", (0, 0, 499, 499))]
    out = export_markdown(doc, tmp_path / "out" / "scan.md")
    text = out.read_text(encoding="utf-8")
    assert text == "Nad obrázkem.\n\n![](scan_images/scan-s001-obr1.png)\n"
    with Image.open(tmp_path / "out" / "scan_images" / "scan-s001-obr1.png") as im:
        assert im.size == (849, 1098)            # 499/999 of 1700 x 2200 (letter at 200 dpi)


def test_image_links_survive_spaces_and_parentheses(tmp_path):
    pdf = make_scan_pdf(tmp_path / "My scan (1).pdf")
    doc = sample_document()
    doc.source_path = str(pdf)
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [block("figure", "", (0, 0, 499, 499))]
    text = export_markdown(doc, tmp_path / "My scan (1).md").read_text(encoding="utf-8")
    assert text == "![](<My scan (1)_images/My scan (1)-s001-obr1.png>)\n"
    assert (tmp_path / "My scan (1)_images" / "My scan (1)-s001-obr1.png").is_file()
