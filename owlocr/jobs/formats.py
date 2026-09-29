"""Which export formats this build can write.

Plan C adds Word and searchable PDF to `owlocr.export.export_all`. Until then those formats raise
NotImplementedError. The UI shows them disabled; the runner skips them.
"""
from __future__ import annotations

import functools
import tempfile
from pathlib import Path

from PIL import Image

from owlocr import __version__, export, settings
from owlocr.pipeline.document import Document, Page


@functools.lru_cache(maxsize=1)
def available_formats() -> tuple[str, ...]:
    declared = getattr(export, "FORMATS_AVAILABLE", None)
    if declared is not None:
        return tuple(f for f in export.FORMATS if f in declared)
    found: list[str] = []
    with tempfile.TemporaryDirectory(prefix="owl-probe-", ignore_cleanup_errors=True) as tmp:
        folder = Path(tmp)
        source = folder / "probe.png"
        Image.new("RGB", (32, 32), "white").save(source)
        page = Page(index=0, source="blank", mode=None, width_px=32, height_px=32,
                    rotation_applied=0, blocks=[], raw="", warnings=[], seconds=0.0)
        doc = Document(source_path=str(source), engine_id="unlimited_ocr", engine_revision="probe",
                       app_version=__version__, created="1970-01-01T00:00:00", pages=[page])
        for fmt in export.FORMATS:
            try:
                export.export_all(doc, source, [fmt], folder, dict(settings.DEFAULTS))
            except NotImplementedError:
                continue
            except Exception:  # the exporter exists; it just disliked the empty probe page
                pass
            found.append(fmt)
    return tuple(found)
