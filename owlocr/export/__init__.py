"""Exports: Markdown, plain text, Word and searchable PDF."""
from pathlib import Path

from owlocr.export.markdown import export_markdown
from owlocr.export.text import export_text
from owlocr.pipeline.document import Document
from owlocr.export.docx import export_docx
from owlocr.export.searchable_pdf import export_searchable_pdf

FORMATS = ("md", "txt", "docx", "pdf")
FORMATS_AVAILABLE = ("md", "txt", "docx", "pdf")   # all four work; plan B enables the checkboxes from it


def export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]:
    """Write every requested format into out_dir, named after the source file (design 10.6).
    Returns format -> path actually written (existing files are never overwritten). Never writes
    the .owl.json sidecar (the CLI and the plan B runner do)."""
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:                                  # checked before anything is written
        raise ValueError(f"unknown export formats: {unknown}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    stem = source.stem
    keep = bool(settings.get("keep_page_furniture", False))
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "md":
            written["md"] = export_markdown(doc, out_dir / f"{stem}.md", keep_furniture=keep,
                                            suspicious_appendix=bool(settings.get("append_suspicious_list", False)),
                                            image_links=settings.get("image_links", "markdown"))
        elif fmt == "txt":
            written["txt"] = export_text(doc, out_dir / f"{stem}.txt", keep_furniture=keep)
        elif fmt == "docx":
            written["docx"] = export_docx(doc, out_dir / f"{stem}.docx", keep_furniture=keep)
        elif fmt == "pdf":
            written["pdf"] = export_searchable_pdf(doc, source, out_dir / f"{stem}.ocr.pdf")
    return written
