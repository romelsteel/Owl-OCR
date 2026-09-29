"""One-time installation of the OCR engine (design 6.2 and 6.3).

`run()` walks the STAGES in order. Every stage has its own check and is skipped when the check
passes, so an interrupted installation continues where it stopped. The stages live in
`owlocr/engine/stages.py`, their building blocks in `owlocr/engine/install_kit.py`; this module
holds the public API of the interface contract.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import registry, stages, store
from owlocr.engine.install_kit import BootstrapError, Deps, StageContext
from owlocr.hardware import Tier

__all__ = ["STAGES", "StageEvent", "install_path", "is_installed", "read_install", "run",
           "remove_engine", "reset_install", "sync_worker_files", "was_interrupted",
           "required_free_bytes", "BootstrapError"]

STAGES = ("tools", "python", "venv", "torch", "deps", "model", "worker", "patch", "selftest", "mark")
REQUIRED_FREE_BYTES = 16 * 1024**3        # design 6.3 rule 6
PINS_REL = "owlocr/engine/pins.json"

_RUN_LOCK = threading.Lock()


@dataclass
class StageEvent:
    stage: str
    state: str      # 'start' | 'progress' | 'done' | 'skipped' | 'failed'
    done: int
    total: int
    message: str


def install_path() -> Path:
    return kit.install_file()


def read_install() -> dict | None:
    return kit.read_json(install_path())


def is_installed() -> bool:
    """install.json matches the app's pins and the model passes the fast readiness check.
    A development record written by plan A's scripts/dev_engine.py (tier "development") counts
    as installed when its Python and worker exist and the model is ready."""
    record = read_install()
    if not record:
        return False
    if record.get("tier") == "development":
        python = Path(record.get("python") or paths.engine_python())
        worker = Path(record.get("worker_script") or paths.worker_dir() / "owl_worker.py")
        return python.is_file() and worker.is_file() and store.is_ready()
    spec = registry.UNLIMITED_OCR
    expected = {
        "format": kit.INSTALL_FORMAT, "python_version": kit.PYTHON_VERSION, "engine_id": spec.engine_id,
        "revision": spec.revision, "torch": spec.torch, "torchvision": spec.torchvision,
        "transformers": spec.transformers,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        return False
    try:
        if record.get("requirements_sha256") != kit.requirements_sha256():
            return False
    except OSError:
        return False
    if not paths.engine_python().is_file() or not kit.venv_home_ok():
        return False
    return store.is_ready()


def was_interrupted() -> bool:
    """True when an installation was started and has not finished (resume after restart)."""
    return kit.state_file().exists()


def load_pins() -> dict:
    pins_file = paths.resource_path(PINS_REL)
    try:
        pins = json.loads(pins_file.read_text(encoding="utf-8"))
        uv = pins["uv"]
        if len(uv["sha256"]) != 64 or not uv["url"].startswith("https://") or not uv["version"]:
            raise ValueError("incomplete uv pin")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BootstrapError(f"internal: {pins_file} is missing or invalid: {exc}") from exc
    return pins


def required_free_bytes(already_present: int) -> int:
    return max(0, REQUIRED_FREE_BYTES - already_present)


class _InstallLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")


def run(tier: Tier, on_event: Callable[[StageEvent], None],
        cancel: threading.Event | None = None) -> None:
    _run(tier, on_event, cancel, Deps(pins=load_pins()))


def _run(tier: Tier, on_event: Callable[[StageEvent], None], cancel: threading.Event | None,
         deps: Deps) -> None:
    if tier.name == "unsupported":
        raise BootstrapError(f"unsupported: {tier.reason}")
    if not _RUN_LOCK.acquire(blocking=False):
        raise BootstrapError("already_running: an installation is already running")
    try:
        paths.engine_dir().mkdir(parents=True, exist_ok=True)
        log = _InstallLog(paths.logs_dir() / "install.log")
        log.write(f"=== Owl OCR engine installation, tier {tier.name}, {time.strftime('%Y-%m-%d %H:%M:%S')}")
        present = kit.dir_size(paths.engine_dir()) + kit.dir_size(paths.model_dir())
        need, free = required_free_bytes(present), deps.free_bytes(paths.data_root())
        if free < need:
            log.write(f"not enough space: {need} needed, {free} free")
            raise BootstrapError(f"not_enough_space: {need} bytes needed on the data drive, {free} free")
        paths.atomic_write_text(kit.state_file(), json.dumps({"tier": tier.name, "started": time.time()}))
        for stage in STAGES:
            _run_stage(stage, tier, deps, cancel, on_event, log)
        kit.state_file().unlink(missing_ok=True)
        log.write("=== installation finished")
    finally:
        _RUN_LOCK.release()


def _run_stage(stage: str, tier: Tier, deps: Deps, cancel: threading.Event | None,
               on_event: Callable[[StageEvent], None], log: _InstallLog) -> None:
    ctx = StageContext(tier, deps, cancel,
                       lambda d, t, m: on_event(StageEvent(stage, "progress", d, t, m)), log.write)

    def fail(message: str) -> None:
        log.write(f"--- stage {stage} failed: {message}")
        on_event(StageEvent(stage, "failed", ctx.done, ctx.total, message))

    if ctx.cancelled():
        fail("cancelled")
        raise BootstrapError("cancelled")
    log.write(f"--- stage {stage}")
    on_event(StageEvent(stage, "start", 0, 0, "checking"))
    try:
        if stages.CHECKS[stage](ctx):
            log.write(f"--- stage {stage} already done, skipped")
            on_event(StageEvent(stage, "skipped", 0, 0, ""))
            return
        stages.ACTIONS[stage](ctx)
        if ctx.cancelled():
            raise BootstrapError("cancelled")
        if not stages.CHECKS[stage](ctx):
            raise BootstrapError(f"check_failed: the {stage} stage finished but its check does not pass")
    except BootstrapError as exc:
        fail(str(exc))
        raise
    except Exception as exc:
        log.write(traceback.format_exc())
        fail(f"internal: {type(exc).__name__}: {exc}")
        raise BootstrapError(f"internal: {type(exc).__name__}: {exc}") from exc
    log.write(f"--- stage {stage} done")
    on_event(StageEvent(stage, "done", ctx.done, ctx.total, ctx.message))


def _refuse_development() -> None:
    if (read_install() or {}).get("tier") == "development":
        raise BootstrapError("development: this data root holds a development engine "
                             "(scripts/dev_engine.py); remove or reinstall it by hand")


def remove_engine() -> None:
    """Deletes the engine runtime, the model and the Hugging Face caches. The queue stays."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise BootstrapError("already_running: an installation is running")
    try:
        _refuse_development()
        for folder in (paths.engine_dir(), paths.model_dir(), paths.hf_home()):
            kit.rmtree(folder)
    finally:
        _RUN_LOCK.release()


def reset_install() -> None:
    """For 'Reinstall': forgets what was installed and rebuilds the venv. Downloads are kept
    (uv cache, Python, intact model files), so a reinstall downloads only damaged model files."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise BootstrapError("already_running: an installation is running")
    try:
        _refuse_development()
        model = paths.model_dir().resolve()
        problems = store.verify() if store.manifest_path().exists() else {}
        for rel in problems:
            damaged = (model / rel).resolve()
            if damaged.is_relative_to(model) and damaged.is_file():
                damaged.unlink()
        if problems:
            store.manifest_path().unlink(missing_ok=True)      # the model stage downloads them again
        install_path().unlink(missing_ok=True)
        for name in ("deps", "selftest"):
            (kit.stamps_dir() / f"{name}.json").unlink(missing_ok=True)
        kit.rmtree(kit.venv_dir())
    finally:
        _RUN_LOCK.release()


def sync_worker_files() -> bool:
    """Copies the app's worker scripts into an installed engine when they differ.
    Returns True when something was copied. Called once when the server starts."""
    if not paths.worker_dir().is_dir():
        return False
    copied = False
    for name in kit.WORKER_FILES:
        src, dst = paths.resource_path(f"worker/{name}"), paths.worker_dir() / name
        if src.is_file() and (not dst.is_file() or dst.read_bytes() != src.read_bytes()):
            kit.copy_atomic(src, dst)
            copied = True
    return copied
