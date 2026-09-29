"""Shared helpers for the plan-B tests (not a test module)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
FAKE_WORKER = REPO / "tests" / "fake_worker.py"
STATIC = REPO / "owlocr" / "web" / "static"


def make_tiff(path: Path, pages: int = 1) -> Path:
    """A multi-page TIFF whose pages carry dark bars, so the blank-page guard does not skip them."""
    frames = []
    for n in range(pages):
        img = Image.new("L", (600, 800), 255)
        draw = ImageDraw.Draw(img)
        for row in range(8):
            y = 80 + row * 70
            draw.rectangle([60, y, 540 - n * 10, y + 22], fill=0)
        frames.append(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], compression="tiff_deflate")
    return path


def fake_engine_factory(tmp: Path, behaviour: str = ""):
    """Engine factory that builds a SubprocessEngine running tests/fake_worker.py on the CPU.

    The behaviour reaches the worker through the environment variable FAKE_WORKER, which the
    tests set with monkeypatch before the engine starts; `behaviour` is only documentation here."""
    from owlocr.engine.client import SubprocessEngine

    model = tmp / "fake_model"
    model.mkdir(parents=True, exist_ok=True)

    def make():
        return SubprocessEngine(python=Path(sys.executable), worker_script=FAKE_WORKER,
                                model_dir=model, device="cpu", dtype="float32",
                                log_file=tmp / "engine.log")
    return make


def settings_for(tmp: Path, **overrides) -> dict:
    from owlocr import settings

    values = dict(settings.DEFAULTS)
    values.update({"mode_default": "quality", "formats": ["md", "txt"],
                   "output_location": "folder", "output_folder": str(tmp / "out"),
                   "idle_stop_minutes": 0})
    values.update(overrides)
    return values


def engine_error(kind: str):
    """An EngineError with the given kind (and the kind as its message)."""
    from owlocr.engine.protocol import EngineError

    return EngineError(kind, kind)


def wait_until(predicate, timeout: float = 10.0, step: float = 0.05) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(step)
    return bool(predicate())


def static_text(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def between(text: str, begin: str, end: str) -> str:
    start = text.index(begin) + len(begin)
    return text[start:text.index(end, start)]


def ui_strings() -> dict:
    """The Czech and English tables of i18n.js (strict JSON between the STRINGS markers)."""
    import json

    return json.loads(between(static_text("i18n.js"), "/*STRINGS-BEGIN*/", "/*STRINGS-END*/"))
