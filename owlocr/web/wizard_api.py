"""HTTP routes of the setup wizard and of the engine actions in Settings (plan D).

Registered by `owlocr/web/server.py:create_app` with
`app.register_blueprint(make_blueprint(runner, queue=queue))`.
"""
from __future__ import annotations

import contextlib
import dataclasses
import functools
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from flask import Blueprint, jsonify, request

from owlocr import hardware, paths
from owlocr.engine import bootstrap, registry, relocate, store
from owlocr.engine.bootstrap import BootstrapError, StageEvent
from owlocr.engine.relocate import LocationError
from owlocr.jobs import engines

log = logging.getLogger(__name__)


def demo_install(tier: hardware.Tier, on_event: Callable[[StageEvent], None],
                 cancel: threading.Event) -> None:
    """Used when OWLOCR_DEMO_INSTALL=1: walks through the stages without installing anything,
    so the wizard can be tried out and smoke-tested without downloading 10 GB."""
    for stage in bootstrap.STAGES:
        on_event(StageEvent(stage, "start", 0, 0, "checking"))
        for step in range(1, 11):
            if cancel.is_set():
                on_event(StageEvent(stage, "failed", step, 10, "cancelled"))
                raise BootstrapError("cancelled")
            time.sleep(0.25)
            on_event(StageEvent(stage, "progress", step * 100_000_000, 1_000_000_000, f"demo {stage}"))
        on_event(StageEvent(stage, "done", 1_000_000_000, 1_000_000_000, ""))


class InstallController:
    """Runs `bootstrap.run` in a background thread and keeps its events for polling."""

    def __init__(self, run_fn: Callable | None = None) -> None:
        if run_fn is None:
            run_fn = demo_install if os.environ.get("OWLOCR_DEMO_INSTALL") == "1" else bootstrap.run
        self._run_fn = run_fn
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, tier: hardware.Tier) -> bool:
        with self._lock:
            if self.running:
                return False
            self._events, self._error = [], None
            self._cancel = threading.Event()
            self._thread = threading.Thread(target=self._work, args=(tier, self._cancel),
                                            name="owl-install", daemon=True)
            self._thread.start()
            return True

    def _work(self, tier: hardware.Tier, cancel: threading.Event) -> None:
        try:
            self._run_fn(tier, self._on_event, cancel)
        except BootstrapError as exc:
            with self._lock:
                self._error = str(exc)
        except Exception as exc:        # never let the thread die silently
            with self._lock:
                self._error = f"internal: {type(exc).__name__}: {exc}"
        finally:
            engines.forget_installed()  # /api/status must see the new state at once

    def _on_event(self, event: StageEvent) -> None:
        data = dataclasses.asdict(event)
        with self._lock:
            last = self._events[-1] if self._events else None
            if (data["state"] == "progress" and last is not None
                    and last["stage"] == data["stage"] and last["state"] == "progress"):
                self._events[-1] = data           # keep one progress event per stage run
            else:
                self._events.append(data)

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def snapshot(self) -> dict:
        with self._lock:
            return {"events": list(self._events), "running": self.running, "error": self._error}


def _default_probe() -> tuple[list[hardware.Gpu], int]:
    return hardware.probe_gpus(), hardware.ram_total_mib()


def _error(message: str, status: int):
    return jsonify({"error": message}), status


BUSY = "busy: another engine action is running"
INSTALL_RUNNING = "install_running: wait until the installation finishes or pause it"
QUEUE_RUNNING = "queue_running: pause the queue first"


def make_blueprint(runner, controller: InstallController | None = None,
                   probe_fn: Callable[[], tuple[list[hardware.Gpu], int]] | None = None,
                   queue=None) -> Blueprint:
    """The wizard and engine routes. `bp.file_ops_busy()` tells whether a file operation
    (location change, adopt, verify, remove, reinstall, move) is running right now,
    `bp.install_running()` whether the installer runs, and `with bp.try_file_ops() as got:`
    holds the file-operations lock without waiting (`got` is False when it is taken)."""
    bp = Blueprint("owl_wizard", __name__)
    installer = controller or InstallController()
    probe_hw = probe_fn or _default_probe
    file_ops = threading.Lock()     # one engine file operation at a time, and none during start
    bp.file_ops_busy = file_ops.locked
    bp.install_running = lambda: installer.running

    @contextlib.contextmanager
    def try_file_ops():
        got = file_ops.acquire(blocking=False)
        try:
            yield got
        finally:
            if got:
                file_ops.release()
    bp.try_file_ops = try_file_ops
    try:
        bootstrap.sync_worker_files()   # an app update may bring newer worker scripts
    except OSError:
        pass

    def exclusive(view):
        """Runs the route while holding the file-operations lock; 409 busy when it is taken."""
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if not file_ops.acquire(blocking=False):
                return _error(BUSY, 409)
            try:
                return view(*args, **kwargs)
            finally:
                file_ops.release()
        return wrapper

    def queue_busy() -> bool:
        status = runner.status()
        return status.get("engine") == "busy" or (bool(status.get("running")) and not status.get("paused"))

    def blocked():
        """Response when the engine files must not be touched now, else None."""
        if installer.running:
            return _error(INSTALL_RUNNING, 409)
        if queue_busy():
            return _error(QUEUE_RUNNING, 409)
        return None

    def body_path() -> str | None:
        body = request.get_json(silent=True) or {}
        value = body.get("path")
        return value if isinstance(value, str) and value.strip() else None

    def _follow(old: Path) -> None:
        """After the data root changed: the queue saves to the new queue.json, the old one goes.
        Best effort: the data root has already moved, so a failure here is only logged."""
        if queue is None:
            return
        try:
            queue.relocate(paths.queue_file())
            if paths.data_root().resolve() != old.resolve():
                (old / "queue.json").unlink(missing_ok=True)
        except Exception:
            log.exception("the queue could not follow the data root from %s", old)

    def _probe_value(errors: list[str], code: str, fn: Callable, default):
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{code}: {type(exc).__name__}: {exc}")
            return default

    @bp.get("/api/wizard/probe")
    def wizard_probe():
        errors: list[str] = []
        gpus, ram = _probe_value(errors, "hardware_probe_failed", probe_hw, ([], 0))
        tier = hardware.choose_tier(gpus, ram)
        root = paths.data_root()
        # An unplugged data drive must not break the probe: the wizard is where a new folder is chosen.
        free = _probe_value(errors, "disk_unreadable", lambda: relocate.free_bytes(root), 0)
        return jsonify({
            "gpus": [dataclasses.asdict(g) for g in gpus], "ram_mib": ram,
            "tier": dataclasses.asdict(tier), "data_root": str(root),
            "free_bytes": free, "required_bytes": bootstrap.REQUIRED_FREE_BYTES,
            "interrupted": _probe_value(errors, "install_unreadable", bootstrap.was_interrupted, False),
            "installed": _probe_value(errors, "install_unreadable", bootstrap.is_installed, False),
            "model_ready": _probe_value(errors, "model_check_failed", store.is_ready, False),
            "install": _probe_value(errors, "install_unreadable", bootstrap.read_install, None),
            "env_override": bool(os.environ.get("OWLOCR_HOME")),
            "logs_dir": str(paths.logs_dir()), "cpu_tier_enabled": hardware.CPU_TIER_ENABLED,
            "probe_error": errors[0] if errors else None,
        })

    @bp.post("/api/wizard/location")
    @exclusive
    def wizard_location():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        old = paths.data_root()
        if relocate.has_data(old):
            refusal = blocked()
            if refusal:
                return refusal
            runner.stop_engine()
        elif installer.running:
            return _error(INSTALL_RUNNING, 409)
        try:
            folder = relocate.choose_location(Path(path))
        except LocationError as exc:
            return _error(str(exc), 400)
        finally:
            engines.forget_installed()
        _follow(old)
        return jsonify({"data_root": str(folder), "free_bytes": relocate.free_bytes(folder)})

    @bp.post("/api/wizard/adopt")
    @exclusive
    def wizard_adopt():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        if installer.running:
            return _error(INSTALL_RUNNING, 409)
        copy = bool((request.get_json(silent=True) or {}).get("copy", False))
        try:
            store.adopt(Path(path), registry.UNLIMITED_OCR, move=not copy)
        except (store.StoreError, OSError) as exc:
            return _error(f"adopt_failed: {exc}", 400)
        finally:
            engines.forget_installed()
        return jsonify({"ok": True})

    @bp.post("/api/wizard/install")
    def wizard_install():
        gpus, ram = probe_hw()
        tier = hardware.choose_tier(gpus, ram)
        if tier.name == "unsupported":
            return _error(f"unsupported: {tier.reason}", 400)
        with try_file_ops() as got:
            if not got:
                return _error(BUSY, 409)
            if installer.running:
                return jsonify({"started": False})
            if queue_busy():
                return _error(QUEUE_RUNNING, 409)
            runner.stop_engine()        # the installer may replace the venv and runs its own engine
            started = installer.start(tier)
        return jsonify({"started": started})

    @bp.post("/api/wizard/cancel")
    def wizard_cancel():
        installer.cancel()
        return jsonify({})

    @bp.get("/api/wizard/progress")
    def wizard_progress():
        return jsonify(installer.snapshot())

    @bp.post("/api/engine/verify")
    @exclusive
    def engine_verify():
        if installer.running:
            return _error(INSTALL_RUNNING, 409)
        try:
            problems = store.verify()
        except (store.StoreError, OSError) as exc:
            return _error(f"verify_failed: {exc}", 500)
        return jsonify({"problems": problems})

    @bp.post("/api/engine/remove")
    @exclusive
    def engine_remove():
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        try:
            bootstrap.remove_engine()
        except BootstrapError as exc:
            return _error(str(exc), 409)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        finally:
            engines.forget_installed()
        return jsonify({})

    @bp.post("/api/engine/reinstall")
    @exclusive
    def engine_reinstall():
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        try:
            bootstrap.reset_install()
        except BootstrapError as exc:
            return _error(str(exc), 409)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        finally:
            engines.forget_installed()
        return jsonify({})

    @bp.post("/api/engine/move")
    @exclusive
    def engine_move():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        old = paths.data_root()
        try:
            folder = relocate.move_data_root(Path(path))
        except LocationError as exc:
            return _error(str(exc), 400)
        finally:
            engines.forget_installed()
        leftovers = [str(item) for item in relocate.last_leftovers]
        _follow(old)
        return jsonify({"data_root": str(folder), "free_bytes": relocate.free_bytes(folder),
                        "leftovers": leftovers})

    return bp
