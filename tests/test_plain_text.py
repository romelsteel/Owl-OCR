"""plain_text(): the page as plain text (needs parse.html_table_to_rows for tables)."""
from owlocr.pipeline import document
from owlocr.pipeline.document import Block
from tests.samples import sample_document


def test_plain_text():
    page = sample_document().pages[0]
    assert document.plain_text(page) == (
        "Buněčné dýchání\n\nBuňka získává energii.\n\nJméno\tObec\nŽaneta\tTřebíč")
    with_furniture = document.plain_text(page, keep_furniture=True)
    assert with_furniture.startswith("Kapitola 1\n\n")
    assert with_furniture.endswith("Třebíč\n\n7")


def test_plain_text_of_merged_table_and_blank_page():
    doc = sample_document()
    merged = '<table><tr><td colspan="2">Souhrn</td></tr><tr><td>a</td><td>b</td></tr></table>'
    doc.pages[0].blocks = [Block(label="table", box=None, text=merged, raw_text=merged, flags=[])]
    assert document.plain_text(doc.pages[0]) == "Souhrn\na\tb"
    assert document.plain_text(doc.pages[1]) == ""
