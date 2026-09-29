"""Markdown export (design 11).

title -> '#' when its box is at least 1.6 times as tall as the page's typical text line, else '##';
text -> paragraph; list -> list items; table -> pipe table, or the HTML when cells are merged;
formula -> $$ ... $$; image/figure -> cut from the page into <name>_images/ and linked;
captions in italics; page_number/header/footer left out unless keep_furniture.
"""
import re
import statistics
import tempfile
from pathlib import Path

from PIL import Image

from owlocr import paths
from owlocr.pipeline.document import FURNITURE_LABELS, Block, Document, Page
from owlocr.pipeline.pages import render_page
from owlocr.pipeline.parse import html_table_to_rows

_BULLET = re.compile(r"^\s*(?:[-*+•·▪–]|\d+[.)])\s+")
_CROP_DPI = 200


def _line_height(page: Page) -> float | None:
    """Typical height of one text line, from the text blocks' boxes (a block may hold many lines,
    so the smallest boxes are the best estimate)."""
    heights = sorted(b.box[3] - b.box[1] for b in page.blocks if b.label == "text" and b.box)
    if not heights:
        return None
    return statistics.median(heights[: max(1, len(heights) // 2)])


def _heading(block: Block, line: float | None) -> str:
    level = "##"
    if block.box and line:
        if (block.box[3] - block.box[1]) >= 1.6 * line:
            level = "#"
    return f"{level} {' '.join(block.text.split())}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _table(block: Block) -> str:
    rows = html_table_to_rows(block.text) if "<t" in block.text.lower() else None
    if not rows:
        return block.text.strip()
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |",
             "|" + "---|" * width]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _list(block: Block) -> str:
    items = [line.strip() for line in block.text.splitlines() if line.strip()]
    return "\n".join("- " + _BULLET.sub("", item) for item in items)


def _formula(block: Block) -> str:
    body = block.text.strip()
    for opening, closing in (("$$", "$$"), ("\\[", "\\]"), ("$", "$")):
        if body.startswith(opening) and body.endswith(closing) and len(body) > len(opening) + len(closing):
            body = body[len(opening):-len(closing)].strip()
            break
    return f"$$\n{body}\n$$"


_UNSAFE_NAME = re.compile(r'[\[\]#^|\\/:*?"<>]')


def _url_escape(part: str) -> str:
    """'%' and '#' percent-encoded, so a link target never ends at a URL fragment (final review
    T18: "Faktura #12"). Only for Markdown links; Obsidian embeds take the plain file name."""
    return part.replace("%", "%25").replace("#", "%23")


class _ImageCutter:
    """Cuts image blocks out of the source pages into <out stem>_images/. The page is rendered
    again and turned clockwise by Page.rotation_applied, so the boxes (which refer to the image
    the model read) fit. Files are named <safe stem of the .md>-s<page>-obr<n>.png (n counts per
    document, and the .md name is already unique), so they stay unique inside one Obsidian vault;
    the link is a Markdown link to the folder or, with image_links="obsidian", an Obsidian embed
    of the file name (ruling R9)."""

    def __init__(self, doc: Document, out: Path, image_links: str = "markdown") -> None:
        if image_links not in ("markdown", "obsidian"):
            raise ValueError(f"image_links must be 'markdown' or 'obsidian', not {image_links!r}")
        self.source = Path(doc.source_path)
        self.stem = _UNSAFE_NAME.sub("_", out.stem)
        self.folder = out.with_name(out.stem + "_images")
        self.style = image_links
        self.count = 0
        self._rendered: dict[int, Image.Image | None] = {}

    def link(self, page: Page, block: Block) -> str | None:
        if block.box is None or not self.source.is_file():
            return None
        image = self._page_image(page)
        if image is None:
            return None
        x1, y1, x2, y2 = block.box
        w, h = image.size
        box = (x1 * w // 999, y1 * h // 999, max(x2 * w // 999, x1 * w // 999 + 1),
               max(y2 * h // 999, y1 * h // 999 + 1))
        self.count += 1
        self.folder.mkdir(parents=True, exist_ok=True)
        name = f"{self.stem}-s{page.index + 1:03d}-obr{self.count}.png"
        image.crop(box).save(self.folder / name, "PNG")
        if self.style == "obsidian":
            return f"![[{name}]]"
        target = f"{_url_escape(self.folder.name)}/{_url_escape(name)}"
        if any(c in target for c in " ()"):     # CommonMark needs <...> around such a destination
            target = f"<{target}>"
        return f"![]({target})"

    def _page_image(self, page: Page) -> Image.Image | None:
        if page.index not in self._rendered:
            with tempfile.TemporaryDirectory() as tmp:
                png = Path(tmp) / "page.png"
                try:
                    render_page(self.source, page.index, _CROP_DPI, png)
                except (OSError, ValueError, IndexError, EOFError):
                    self._rendered[page.index] = None
                    return None
                with Image.open(png) as im:
                    # rotate() returns a new image, also for 0 degrees
                    self._rendered[page.index] = im.rotate(-page.rotation_applied, expand=True)
        return self._rendered[page.index]


def _page_markdown(page: Page, keep_furniture: bool, images: _ImageCutter) -> list[str]:
    parts = []
    line = _line_height(page)
    for block in page.blocks:
        if block.label in FURNITURE_LABELS and not keep_furniture:
            continue
        if block.label in ("image", "figure"):
            link = images.link(page, block)
            if link:
                parts.append(link)
            continue
        if not block.text.strip():
            continue
        if block.label == "title":
            parts.append(_heading(block, line))
        elif block.label == "table":
            parts.append(_table(block))
        elif block.label == "list":
            parts.append(_list(block))
        elif block.label == "formula":
            parts.append(_formula(block))
        elif block.label in ("image_caption", "table_caption"):
            parts.append(f"*{' '.join(block.text.split())}*")
        else:
            parts.append(block.text.strip())
    return parts


_LISTED_FLAGS = ("suspicious", "foreign_letter")


def _appendix(doc: Document) -> str | None:
    """Design 9.1 point 4: the flagged words, page by page. Words with a letter that does not
    exist in Czech (plan C's 'foreign_letter' flags) are listed like the suspicious ones."""
    lines = []
    for page in doc.pages:
        for block in page.blocks:
            for flag in block.flags:
                if flag.kind in _LISTED_FLAGS:
                    lines.append(f"- page {page.index + 1}: `{flag.original}`")
    if not lines:
        return None
    return "---\n\n**Suspicious words / Podezřelá slova**\n\n" + "\n".join(lines)


def export_markdown(doc: Document, out: Path, page_comments: bool = False,
                    keep_furniture: bool = False, suspicious_appendix: bool = False, *,
                    image_links: str = "markdown") -> Path:
    target = paths.unique_path(Path(out))
    images = _ImageCutter(doc, target, image_links)
    chunks = []
    for page in doc.pages:
        parts = _page_markdown(page, keep_furniture, images)
        if page_comments:
            parts.insert(0, f"<!-- page {page.index + 1} -->")
        if parts:
            chunks.append("\n\n".join(parts))
    if suspicious_appendix and (appendix := _appendix(doc)):
        chunks.append(appendix)
    text = "\n\n".join(chunks)
    paths.atomic_write_text(target, text + "\n" if text else "")
    return target
