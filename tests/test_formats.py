from owlocr import export
from owlocr.jobs import formats


def test_markdown_and_text_always_available():
    formats.available_formats.cache_clear()
    found = formats.available_formats()
    assert {"md", "txt"} <= set(found)
    assert set(found) <= set(export.FORMATS)


def test_not_implemented_formats_are_left_out(monkeypatch):
    def fake_export_all(doc, source, fmts, out_dir, settings):
        if fmts[0] in ("docx", "pdf"):
            raise NotImplementedError(fmts[0])
        return {}
    monkeypatch.delattr(export, "FORMATS_AVAILABLE", raising=False)
    monkeypatch.setattr(export, "export_all", fake_export_all)
    formats.available_formats.cache_clear()
    try:
        assert formats.available_formats() == ("md", "txt")
    finally:
        formats.available_formats.cache_clear()


def test_declared_capability_list_wins(monkeypatch):
    monkeypatch.setattr(export, "FORMATS_AVAILABLE", ("md", "txt", "docx"), raising=False)
    formats.available_formats.cache_clear()
    try:
        assert formats.available_formats() == ("md", "txt", "docx")
    finally:
        formats.available_formats.cache_clear()
