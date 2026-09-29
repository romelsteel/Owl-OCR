from owlocr.export.text import document_text, export_text
from tests.samples import sample_document


def test_document_text_and_export(tmp_path):
    doc = sample_document()
    assert document_text(doc) == "Buněčné dýchání\n\nBuňka získává energii.\n\nJméno\tObec\nŽaneta\tTřebíč\n"
    assert document_text(doc, keep_furniture=True).startswith("Kapitola 1\n\n")
    first = export_text(doc, tmp_path / "kniha.txt")
    second = export_text(doc, tmp_path / "kniha.txt")
    assert first == tmp_path / "kniha.txt" and second == tmp_path / "kniha_1.txt"
    assert first.read_text(encoding="utf-8") == document_text(doc)


def test_document_text_of_empty_document():
    doc = sample_document()
    doc.pages = doc.pages[1:]
    assert document_text(doc) == ""
