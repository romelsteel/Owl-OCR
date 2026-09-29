"""Document, Page, Block, Flag (design section 8) and the sidecar <name>.owl.json."""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from owlocr import paths

FURNITURE_LABELS = ("page_number", "header", "footer")
_NO_TEXT_LABELS = ("image", "figure")


@dataclass
class Flag:
    kind: str          # 'repaired' | 'suspicious' | 'foreign_letter'
    start: int         # character offsets in Block.text
    end: int
    original: str      # text before repair, or the suspicious word
    note: str


@dataclass
class Block:
    label: str
    box: tuple[int, int, int, int] | None   # 0..999, None for text-layer blocks without geometry
    text: str          # after repair
    raw_text: str      # exactly as read
    flags: list[Flag]


@dataclass
class Page:
    index: int                  # 0-based
    source: str                 # 'ocr' | 'text_layer' | 'blank'
    mode: str | None            # 'quality' | 'fast'
    width_px: int
    height_px: int
    rotation_applied: int       # 0, 90, 180, 270
    blocks: list[Block]
    raw: str
    warnings: list[str]
    seconds: float


@dataclass
class Document:
    source_path: str
    engine_id: str
    engine_revision: str
    app_version: str
    created: str                # ISO 8601
    pages: list[Page]


def to_json(doc: Document) -> str:
    return json.dumps(asdict(doc), ensure_ascii=False, indent=1)


def _block(data: dict) -> Block:
    box = data.get("box")
    return Block(label=data["label"], box=tuple(box) if box is not None else None, text=data["text"],
                 raw_text=data["raw_text"], flags=[Flag(**f) for f in data.get("flags", [])])


def _page(data: dict) -> Page:
    values = dict(data)
    values["blocks"] = [_block(b) for b in data["blocks"]]
    return Page(**values)


def from_json(text: str) -> Document:
    data = json.loads(text)
    values = dict(data)
    values["pages"] = [_page(p) for p in data["pages"]]
    return Document(**values)


def save_sidecar(doc: Document, path: Path) -> None:
    paths.atomic_write_text(Path(path), to_json(doc) + "\n")


def load_sidecar(path: Path) -> Document:
    return from_json(Path(path).read_text(encoding="utf-8"))


def _table_text(html: str) -> str:
    from owlocr.pipeline.parse import html_table_to_rows

    rows = html_table_to_rows(html)
    if rows is None:            # merged cells: flatten the HTML row by row
        rows = []
        for row in re.split(r"</tr\s*>", html, flags=re.I):
            cells = [re.sub(r"<[^>]+>", " ", c) for c in re.split(r"</t[dh]\s*>", row, flags=re.I)]
            cells = [" ".join(c.split()) for c in cells]
            if any(cells):
                rows.append([c for c in cells if c])
    return "\n".join("\t".join(row) for row in rows)


def _block_text(block: Block) -> str:
    """Text of one block as plain text; tables become tab-separated rows."""
    if block.label in _NO_TEXT_LABELS:
        return ""
    if block.label == "table" and "<t" in block.text.lower():
        return _table_text(block.text)
    return block.text.strip()


def plain_text(page: Page, keep_furniture: bool = False) -> str:
    parts = []
    for block in page.blocks:
        if block.label in FURNITURE_LABELS and not keep_furniture:
            continue
        text = _block_text(block)
        if text:
            parts.append(text)
    return "\n\n".join(parts)
