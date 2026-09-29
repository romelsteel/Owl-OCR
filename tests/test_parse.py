from owlocr.pipeline.document import Block
from owlocr.pipeline.parse import html_table_to_rows, parse_raw
from tests.conftest import RAW


def test_letter_fixture():
    blocks = parse_raw((RAW / "01_letter_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    assert len(blocks) == 7
    assert all(isinstance(b, Block) for b in blocks)
    assert blocks[0] == Block(label="text", box=(101, 73, 365, 91), text="Vážená paní doktorko Šťastná,",
                              raw_text="Vážená paní doktorko Šťastná,", flags=[])
    assert blocks[-1].text == "Ústí nad Labem, 28. září 2026"
    assert all(b.text == b.raw_text and b.flags == [] for b in blocks)


def test_labels_titles_and_header():
    textbook = parse_raw((RAW / "02_textbook_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    assert [b.label for b in textbook][:2] == ["title", "text"]
    screenshot = parse_raw((RAW / "08_screenshot.gundam.raw.txt").read_text(encoding="utf-8"))
    assert screenshot[0].label == "header" and screenshot[0].text == "Nastavení účtu"


def test_table_fixture():
    blocks = parse_raw((RAW / "04_table_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    table = blocks[1]
    assert table.label == "table" and table.box == (102, 121, 898, 313)
    rows = html_table_to_rows(table.text)
    assert rows[0] == ["Jméno", "Obec", "Částka", "Splatnost"]
    assert len(rows) == 6 and all(len(r) == 4 for r in rows)


def test_blank_page_fixture():
    blocks = parse_raw((RAW / "10_blank_page.gundam.raw.txt").read_text(encoding="utf-8"))
    assert blocks == [Block(label="image", box=(0, 0, 999, 999), text="", raw_text="", flags=[])]


def test_old_form_and_unknown_label():
    raw = ("<|ref|>title<|/ref|><|det|>[[10, 20, 300, 40]]<|/det|>\nNadpis\n"
           "<|ref|>sidebar<|/ref|><|det|>[[5,5,50,50], [60,60,90,999]]<|/det|>Okraj")
    blocks = parse_raw(raw)
    assert [(b.label, b.box, b.text) for b in blocks] == [
        ("title", (10, 20, 300, 40), "Nadpis"),
        ("text", (5, 5, 90, 999), "Okraj"),
    ]


def test_text_without_tags_and_special_tokens():
    assert parse_raw("") == []
    blocks = parse_raw("plain words<｜end▁of▁sentence｜>")
    assert [(b.label, b.box, b.text) for b in blocks] == [("text", None, "plain words")]


def test_coordinates_are_clamped_and_ordered():
    (block,) = parse_raw("<|det|>text [900, 1200, 100, -5]<|/det|>x")
    assert block.box == (100, 0, 900, 999)


def test_multiline_block_text_is_kept():
    (block,) = parse_raw("<|det|>list [1, 2, 3, 4]<|/det|>- jedna\n- dvě\n")
    assert block.text == "- jedna\n- dvě"


def test_html_table_merged_cells_and_entities():
    assert html_table_to_rows('<table><tr><td colspan="2">A</td></tr></table>') is None
    assert html_table_to_rows("<table><tr><td rowspan=2>A</td></tr></table>") is None
    rows = html_table_to_rows("<table><tr><th>a &amp; b</th><td>x<br>y</td></tr><tr><td> c </td></tr></table>")
    assert rows == [["a & b", "x y"], ["c"]]
    assert html_table_to_rows("no table here") == []
