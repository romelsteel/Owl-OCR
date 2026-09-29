"""Plan C additions to the Markdown export: foreign letters in the appendix, crops of turned pages,
image names and link styles (ruling R9)."""
import pytest
from PIL import Image, ImageDraw

from owlocr.export import export_all
from owlocr.export.markdown import _UNSAFE_NAME, export_markdown
from owlocr.pipeline.document import Block, Document, Flag, Page

TEXT = "Rostlina je bylinny strom a także list."


def _doc(source, blocks, rotation=0, size=(1000, 1400)):
    page = Page(index=0, source="ocr", mode="quality", width_px=size[0], height_px=size[1],
                rotation_applied=rotation, blocks=blocks, raw="", warnings=[], seconds=1.0)
    return Document(str(source), "unlimited_ocr", "x", "0.1.0", "2026-09-28T10:00:00", [page])


def _figure_doc(source):
    Image.new("RGB", (1000, 1400), "white").save(source)
    return _doc(source, [Block("image", (100, 100, 500, 500), "", "", [])])


def test_appendix_lists_foreign_letters_too(tmp_path):
    flags = [Flag("suspicious", 12, 19, "bylinny", "not in the dictionary"),
             Flag("foreign_letter", 28, 33, "także", "letter does not exist in Czech")]
    doc = _doc(tmp_path / "gone.png", [Block("text", (100, 100, 900, 200), TEXT, TEXT, flags)])
    text = export_markdown(doc, tmp_path / "a.md", suspicious_appendix=True).read_text(
        encoding="utf-8")
    assert text.endswith("**Suspicious words / Podezřelá slova**\n\n"
                         "- page 1: `bylinny`\n- page 1: `także`\n")
    assert text.startswith(TEXT)                       # words are not marked inside the text


def test_image_is_cut_from_the_turned_page(tmp_path):
    upright = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(upright).rectangle((200, 700, 600, 1000), fill=(200, 30, 30))
    source = tmp_path / "sideways.png"
    upright.rotate(90, expand=True).save(source)        # scanned sideways (counter-clockwise)
    doc = _doc(source, [Block("image", (200, 500, 600, 714), "", "", [])], rotation=90)
    out = export_markdown(doc, tmp_path / "out" / "sideways.md")
    with Image.open(tmp_path / "out" / "sideways_images" / "sideways-s001-obr1.png") as crop:
        assert crop.width > crop.height                           # upright, not sideways
        assert crop.getpixel((crop.width // 2, crop.height // 2)) == (200, 30, 30)
    assert out.read_text(encoding="utf-8") == "![](sideways_images/sideways-s001-obr1.png)\n"


def test_obsidian_links_name_only_the_file(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    out = export_markdown(doc, tmp_path / "My notes (1).md", image_links="obsidian")
    assert out.read_text(encoding="utf-8") == "![[My notes (1)-s001-obr1.png]]\n"
    assert (tmp_path / "My notes (1)_images" / "My notes (1)-s001-obr1.png").is_file()


def test_markdown_links_follow_the_output_name_not_the_source(tmp_path):
    doc = _figure_doc(tmp_path / "plain.png")            # no space in the source name
    out = export_markdown(doc, tmp_path / "Moje (2) poznámky.md")
    assert out.read_text(encoding="utf-8") == \
        "![](<Moje (2) poznámky_images/Moje (2) poznámky-s001-obr1.png>)\n"


def test_image_names_are_unique_per_output_and_count_per_document(tmp_path):
    source = tmp_path / "kniha.png"
    Image.new("RGB", (1000, 1400), "white").save(source)
    doc = _doc(source, [Block("image", (100, 100, 500, 500), "", "", []),
                        Block("figure", (500, 500, 900, 900), "", "", [])])
    out = export_markdown(doc, tmp_path / "vystup.md", image_links="obsidian")
    assert out.read_text(encoding="utf-8") == \
        "![[vystup-s001-obr1.png]]\n\n![[vystup-s001-obr2.png]]\n"
    again = export_markdown(doc, tmp_path / "vystup.md", image_links="obsidian")   # same folder
    assert again.name == "vystup_1.md"
    assert again.read_text(encoding="utf-8") == \
        "![[vystup_1-s001-obr1.png]]\n\n![[vystup_1-s001-obr2.png]]\n"
    assert sorted(p.name for p in (tmp_path / "vystup_images").iterdir()) == \
        ["vystup-s001-obr1.png", "vystup-s001-obr2.png"]
    assert sorted(p.name for p in (tmp_path / "vystup_1_images").iterdir()) == \
        ["vystup_1-s001-obr1.png", "vystup_1-s001-obr2.png"]


def test_unsafe_characters_in_the_output_stem_are_replaced(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    out = export_markdown(doc, tmp_path / "a[1]#b^c.md", image_links="obsidian")
    assert out.read_text(encoding="utf-8") == "![[a_1__b_c-s001-obr1.png]]\n"
    assert (tmp_path / "a[1]#b^c_images" / "a_1__b_c-s001-obr1.png").is_file()


def test_unsafe_name_pattern_covers_every_character():
    assert _UNSAFE_NAME.sub("_", r'x[]#^|\/:*?"<>y') == "x" + "_" * 13 + "y"
    assert _UNSAFE_NAME.sub("_", "Moje poznámky (1)-ok.") == "Moje poznámky (1)-ok."


def test_unknown_image_link_style_is_refused(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    with pytest.raises(ValueError):
        export_markdown(doc, tmp_path / "vystup.md", image_links="wiki")
    assert not (tmp_path / "vystup.md").exists()


def test_export_all_forwards_the_image_links_setting(tmp_path):
    doc = _figure_doc(tmp_path / "scan.png")
    written = export_all(doc, tmp_path / "scan.png", ["md"], tmp_path / "out",
                         {"image_links": "obsidian"})
    assert written["md"].read_text(encoding="utf-8") == "![[scan-s001-obr1.png]]\n"
    written = export_all(doc, tmp_path / "scan.png", ["md"], tmp_path / "out2", {})
    assert written["md"].read_text(encoding="utf-8") == "![](scan_images/scan-s001-obr1.png)\n"


# ---- final review T18: '#' and '%' in the output name must not break Markdown links ------------

def test_hash_in_the_output_name_is_percent_encoded_in_markdown_links(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    out = export_markdown(doc, tmp_path / "Faktura #12.md")
    assert out.read_text(encoding="utf-8") == \
        "![](<Faktura %2312_images/Faktura _12-s001-obr1.png>)\n"
    assert (tmp_path / "Faktura #12_images" / "Faktura _12-s001-obr1.png").is_file()


def test_percent_in_the_output_name_is_percent_encoded_in_markdown_links(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    out = export_markdown(doc, tmp_path / "sleva_50%.md")
    assert out.read_text(encoding="utf-8") == \
        "![](sleva_50%25_images/sleva_50%25-s001-obr1.png)\n"
    assert (tmp_path / "sleva_50%_images" / "sleva_50%-s001-obr1.png").is_file()


def test_obsidian_links_are_not_percent_encoded(tmp_path):
    doc = _figure_doc(tmp_path / "kniha.png")
    out = export_markdown(doc, tmp_path / "sleva_50%.md", image_links="obsidian")
    assert out.read_text(encoding="utf-8") == "![[sleva_50%-s001-obr1.png]]\n"
