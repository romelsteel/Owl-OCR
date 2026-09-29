import pytest

from owlocr import export
from tests.samples import sample_document


def test_export_all(tmp_path):
    doc = sample_document()
    written = export.export_all(doc, tmp_path / "in" / "kniha.pdf", ["md", "txt"], tmp_path / "out",
                                {"keep_page_furniture": True, "append_suspicious_list": False})
    assert written == {"md": tmp_path / "out" / "kniha.md", "txt": tmp_path / "out" / "kniha.txt"}
    assert written["txt"].read_text(encoding="utf-8").startswith("Kapitola 1")
    assert export.FORMATS == ("md", "txt", "docx", "pdf")


def test_export_all_rejects_unknown_formats(tmp_path):
    doc = sample_document()
    with pytest.raises(ValueError):
        export.export_all(doc, tmp_path / "k.pdf", ["md", "html"], tmp_path / "out", {})
    assert not (tmp_path / "out" / "k.md").exists()


def test_export_all_never_writes_the_sidecar(tmp_path):
    """Contract note 6: the .owl.json sidecar is the caller's job, never export_all's."""
    export.export_all(sample_document(), tmp_path / "in" / "kniha.pdf", ["md", "txt"], tmp_path / "out", {})
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["kniha.md", "kniha.txt"]
