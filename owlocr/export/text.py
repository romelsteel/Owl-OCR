"""Plain text export (design 11): blocks in order, one blank line between blocks, tables as
tab-separated rows. The same text goes to the clipboard."""
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Document, plain_text


def document_text(doc: Document, keep_furniture: bool = False) -> str:
    pages = [plain_text(page, keep_furniture) for page in doc.pages]
    text = "\n\n".join(p for p in pages if p)
    return text + "\n" if text else ""


def export_text(doc: Document, out: Path, keep_furniture: bool = False) -> Path:
    target = paths.unique_path(Path(out))
    paths.atomic_write_text(target, document_text(doc, keep_furniture))
    return target
