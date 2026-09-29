"""Raw model output -> blocks (design 7.4).

Current form:  <|det|>label [x1, y1, x2, y2]<|/det|>text
Older form:    <|ref|>label<|/ref|><|det|>[[x1, y1, x2, y2]]<|/det|>text
Coordinates are 0..999 relative to the page image. Tables arrive as HTML.
"""
import re
from html.parser import HTMLParser

from owlocr.pipeline.document import Block

KNOWN_LABELS = ("title", "header", "text", "image", "figure", "image_caption", "table",
                "table_caption", "list", "formula", "page_number", "footer")

_NUM = r"\s*(-?\d+)\s*"
_BOX = rf"\[{_NUM},{_NUM},{_NUM},{_NUM}\]"
_TAG = re.compile(
    rf"<\|det\|>\s*(?P<label>[\w-]+)\s*(?P<box>{_BOX})\s*<\|/det\|>"
    rf"|<\|ref\|>\s*(?P<oldlabel>[^<]*?)\s*<\|/ref\|>\s*<\|det\|>\s*\[(?P<oldboxes>.*?)\]\s*<\|/det\|>",
    re.S,
)
_BOX_RE = re.compile(_BOX)
_SPECIAL = re.compile(r"<\|[^|<>]*\|>|<｜[^｜<>]*｜>")


def _clamp(v: int) -> int:
    return max(0, min(999, v))


def _box(numbers: list[int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = (_clamp(n) for n in numbers)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _clean(text: str) -> str:
    return _SPECIAL.sub("", text).strip()


def _label(raw: str) -> str:
    label = raw.strip().lower()
    return label if label in KNOWN_LABELS else "text"


def parse_raw(raw: str) -> list[Block]:
    blocks: list[Block] = []
    matches = list(_TAG.finditer(raw))
    head = _clean(raw[: matches[0].start()] if matches else raw)
    if head:
        blocks.append(Block(label="text", box=None, text=head, raw_text=head, flags=[]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        text = _clean(raw[m.end():end])
        if m.group("label") is not None:
            label = _label(m.group("label"))
            box = _box([int(n) for n in _BOX_RE.match(m.group("box")).groups()])
        else:
            label = _label(m.group("oldlabel"))
            box = _union([_box([int(n) for n in b.groups()]) for b in _BOX_RE.finditer(m.group("oldboxes"))])
        blocks.append(Block(label=label, box=box, text=text, raw_text=text, flags=[]))
    return blocks


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.merged = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._close_row()
            self.row = []
        elif tag in ("td", "th"):
            if any(name in ("rowspan", "colspan") for name, _ in attrs):
                self.merged = True
            self._close_cell()
            if self.row is None:
                self.row = []
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def _close_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
        self.cell = None

    def _close_row(self):
        self._close_cell()
        if self.row:
            self.rows.append(self.row)
        self.row = None


def html_table_to_rows(html: str) -> list[list[str]] | None:
    """Rows of cell texts; None when the table has merged cells (rowspan/colspan)."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    parser._close_row()
    if parser.merged:
        return None
    return parser.rows
