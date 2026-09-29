"""Small PDFs built on the fly for the tests (no PDF library needed)."""
from pathlib import Path

from PIL import Image, ImageDraw


def make_text_pdf(path: Path, pages: list[list[str]]) -> Path:
    """A born-digital PDF: each page shows its lines in Helvetica (plain ASCII only)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = len(objects) + 2 * len(pages) + 1     # the /Pages object comes after all pages
    kids = []
    for lines in pages:
        ops = ["BT", "/F1 14 Tf", "72 740 Td", "18 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({escaped}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                        b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                        % (pages_id, font, content)))
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>"
               % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    Path(path).write_bytes(bytes(out))
    return Path(path)


def make_scan_pdf(path: Path, pages: int = 1) -> Path:
    """A scanned PDF: every page is one full-page image with some dark 'text' bars."""
    images = []
    for n in range(pages):
        im = Image.new("RGB", (850, 1100), "white")
        draw = ImageDraw.Draw(im)
        for row in range(10):
            draw.rectangle([100, 100 + row * 60 + n * 5, 700, 120 + row * 60 + n * 5], fill="black")
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=100)
    return Path(path)
