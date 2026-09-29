"""How the app builds its engine.

Normally `owlocr.engine.client.default_engine()`. For development and the HTTP smoke test the
environment variable OWLOCR_ENGINE_WORKER can name a worker script (tests/fake_worker.py); the
engine then runs that script with the app's own Python on the CPU and counts as installed.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from owlocr import paths
from owlocr.engine import bootstrap
from owlocr.engine.client import SubprocessEngine, default_engine
from owlocr.engine.protocol import EngineError

WORKER_ENV = "OWLOCR_ENGINE_WORKER"
_CACHE_S = 5.0
_cache: dict = {"at": -1e9, "value": False}


def engine_factory() -> SubprocessEngine:
    worker = os.environ.get(WORKER_ENV)
    if not worker:
        if not bootstrap.is_installed():
            raise EngineError("not_installed", "the engine is missing or must be repaired in the setup wizard")
        return default_engine()
    # device "cpu": the runner skips the free-VRAM check for it
    return SubprocessEngine(python=Path(sys.executable), worker_script=Path(worker),
                            model_dir=paths.model_dir(), device="cpu", dtype="float32",
                            log_file=paths.logs_dir() / "engine.log")


def engine_installed() -> bool:
    """True when the engine is installed: bootstrap.is_installed() checks install.json against
    the app's pins, the venv and the model (sizes only, no network). OWLOCR_ENGINE_WORKER still
    counts as installed. Cached for 5 s because the UI asks every second."""
    now = time.monotonic()
    if now - _cache["at"] < _CACHE_S:
        return _cache["value"]
    if os.environ.get(WORKER_ENV):
        value = True
    else:
        try:
            value = bootstrap.is_installed()
        except Exception:  # an unreadable install record counts as not installed
            value = False
    _cache.update(at=now, value=value)
    return value


def forget_installed() -> None:
    """Drop the cached answer (after the wizard installs or removes the engine)."""
    _cache["at"] = -1e9
