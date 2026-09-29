"""A small Document used by the document and export tests."""
from owlocr.pipeline.document import Block, Document, Flag, Page


def sample_document() -> Document:
    table = "<table><tr><td>Jméno</td><td>Obec</td></tr><tr><td>Žaneta</td><td>Třebíč</td></tr></table>"
    blocks = [
        Block(label="header", box=(10, 5, 300, 20), text="Kapitola 1", raw_text="Kapitola 1", flags=[]),
        Block(label="title", box=(100, 50, 400, 80), text="Buněčné dýchání", raw_text="Buněčné dýchání", flags=[]),
        Block(label="text", box=(100, 90, 900, 200), text="Buňka získává energii.",
              raw_text="Buňka ziskává energii.",
              flags=[Flag(kind="repaired", start=6, end=13, original="ziskává", note="R1")]),
        Block(label="image", box=(100, 210, 500, 400), text="", raw_text="", flags=[]),
        Block(label="table", box=(100, 410, 900, 600), text=table, raw_text=table, flags=[]),
        Block(label="page_number", box=(480, 960, 520, 980), text="7", raw_text="7", flags=[]),
    ]
    page = Page(index=0, source="ocr", mode="quality", width_px=1700, height_px=2200, rotation_applied=0,
                blocks=blocks, raw="<|det|>...", warnings=["runaway"], seconds=12.5)
    blank = Page(index=1, source="blank", mode=None, width_px=1700, height_px=2200, rotation_applied=0,
                 blocks=[], raw="", warnings=[], seconds=0.1)
    return Document(source_path="C:\\scans\\kniha.pdf", engine_id="unlimited_ocr",
                    engine_revision="07dea832e22aefee32ad281d4b80551282e1c168", app_version="0.1.0",
                    created="2026-09-28T12:00:00+02:00", pages=[page, blank])
