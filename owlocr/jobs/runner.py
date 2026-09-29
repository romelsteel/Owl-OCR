"""Worker thread that drives the job queue (design 5.6, 5.7, 10.2).

One job at a time, one page at a time. After every page the partial Document is saved to
`paths.work_dir(job_id)/document.owl.json`, so a job continues where it stopped after pause,
manual engine stop, app restart or crash.
"""
from __future__ import annotations

import shutil
import threading
import time
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from owlocr import __version__, hardware, paths
from owlocr.engine import registry
from owlocr.engine.protocol import EngineError
from owlocr.export import export_all
from owlocr.jobs.formats import available_formats
from owlocr.jobs.queue import Job, JobQueue
from owlocr.pipeline import pages
from owlocr.pipeline.document import Document, Page, load_sidecar, save_sidecar
from owlocr.pipeline.process import ProcessOptions, process_page

RESUME_FILE = "document.owl.json"
OOM_WARNING = "out_of_memory_fast"   # same code as plan A's process.py / cli.py, inserted first
_TICK_S = 0.5


class _Interrupted(Exception):
    """The page was abandoned: cancel, manual engine stop or shutdown."""


class _VramShort(Exception):
    def __init__(self, mode: str, need: int, free: int) -> None:
        super().__init__(f"{need - free} MiB of graphics memory missing for {mode} mode")
        self.info = {"code": "vram_short", "mode": mode, "need_mib": need, "free_mib": free,
                     "missing_mib": need - free}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resume_file(job_id: str) -> Path:
    """Partial Document of an unfinished job (does not create the folder)."""
    return paths.data_root() / "work" / job_id / RESUME_FILE


def discard_work(job_id: str) -> None:
    shutil.rmtree(paths.data_root() / "work" / job_id, ignore_errors=True)


def output_dir(source: Path, settings: dict) -> Path:
    if settings.get("output_location") == "folder" and settings.get("output_folder"):
        folder = Path(settings["output_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    return Path(source).parent


def export_document(doc: Document, source: Path, formats: list[str], settings: dict) -> dict[str, str]:
    """Writes the chosen formats that this build supports; returns format -> path written."""
    wanted = [f for f in formats if f in available_formats()]
    if not wanted:
        return {}
    written = export_all(doc, Path(source), wanted, output_dir(source, settings), settings)
    return {fmt: str(path) for fmt, path in written.items()}


class _EngineProxy:
    """Handed to process_page instead of the engine: starts the engine lazily on first OCR.
    With force_mode every read uses that mode (the out-of-memory fallback reads only in Fast,
    also process_page's internal retry of an empty page)."""

    engine_id = "unlimited_ocr"

    def __init__(self, runner: "Runner", force_mode: str | None = None) -> None:
        self._runner = runner
        self._force_mode = force_mode

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        return self._runner._ocr(image, self._force_mode or mode, max_new_tokens, time_limit_s,
                                 on_progress, cancel)

    def __getattr__(self, name):
        engine = self._runner._engine
        if engine is None:
            raise AttributeError(name)
        return getattr(engine, name)


class Runner:
    def __init__(self, queue: JobQueue, engine_factory: Callable[[], object],
                 settings_get: Callable[[], dict]) -> None:
        self._queue = queue
        self._engine_factory = engine_factory
        self._settings_get = settings_get
        self._lock = threading.RLock()          # guards the state flags
        self._engine_lock = threading.RLock()   # guards self._engine
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._cancel = threading.Event()        # interrupts the page being read
        self._cancel_reason: str | None = None  # 'cancel' | 'stop_engine' | 'shutdown'
        self._job_idle = threading.Event()
        self._job_idle.set()
        self._thread: threading.Thread | None = None
        self._engine = None
        self._engine_pid: int | None = None
        self._engine_state = "stopped"
        self._running = False
        self._paused = False
        self._pause_requested = False
        self._current_job: str | None = None
        self._tokens = 0
        self._vram_used: int | None = None
        self._error: dict | None = None
        self._last_work = time.monotonic()
        self._idle_unit_s = 60.0                # one idle_stop_minutes unit; tests shorten it
        self._proxy = _EngineProxy(self)
        self._fast_proxy = _EngineProxy(self, force_mode="fast")

    # ---- public API --------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._stopping.is_set():
                return
            for job in self._queue.all():
                if job.state == "paused":
                    self._queue.update(job.id, state="pending")
            self._running = True
            self._paused = False
            self._pause_requested = False
            self._error = None
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="owl-runner", daemon=True)
                self._thread.start()
        self._wake.set()

    def pause(self) -> None:
        with self._lock:
            if self._running:
                self._pause_requested = True
            else:
                self._paused = True
            self._settle_pause()
        self._wake.set()

    def cancel(self, job_id: str) -> None:
        # One lock block: _loop picks jobs under the same lock, so a job cannot start between
        # the check and the update and then be marked cancelled while it runs.
        with self._lock:
            if self._current_job == job_id:
                self._cancel_reason = "cancel"
                self._cancel.set()
                return
            if self._queue.get(job_id).state in ("pending", "paused"):
                self._queue.update(job_id, state="cancelled", finished=_now())

    def remove(self, job_id: str) -> bool:
        """Removes a job that is not being read and discards its unfinished work. Returns False
        (and changes nothing) for the job being read; raises KeyError for an unknown job.
        Checked and removed under one lock, as in cancel(): _loop picks jobs under the same lock,
        so it cannot start a job that is then removed under it (its next queue.update would raise
        KeyError and end the runner thread)."""
        with self._lock:
            if self._current_job == job_id:
                return False
            self._queue.remove(job_id)
        discard_work(job_id)
        return True

    def unless_current(self, job_id: str, action) -> bool:
        """Calls action() unless job_id is the job being read; returns whether it was called.
        Checked and called under one lock, as in remove(): _loop picks jobs under the same lock,
        so the job cannot start while action() runs (e.g. an edit of its unfinished document).
        action() must be short and must not take _engine_lock (lock order _engine_lock -> _lock)."""
        with self._lock:
            if self._current_job == job_id:
                return False
            action()
            return True

    def stop_engine(self) -> None:
        """Pauses the queue, abandons the page being read (read again on resume) and stops the
        engine; returns once the worker is gone. The engine starts again on the next start()."""
        with self._lock:
            if self._running:
                self._pause_requested = True
            if self._current_job is not None:
                self._cancel_reason = "stop_engine"
                self._cancel.set()
        self._drop_engine()                 # stop first (a loading worker too), then wait
        self._job_idle.wait(timeout=5.0)
        with self._lock:
            self._settle_pause()
        self._wake.set()

    def shutdown(self) -> None:
        with self._lock:
            self._stopping.set()
            self._running = False
            if self._current_job is not None:
                self._cancel_reason = "shutdown"
                self._cancel.set()
        self._wake.set()
        self._drop_engine()                 # stop first (a loading worker too), then wait
        self._job_idle.wait(timeout=3.0)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)

    def status(self) -> dict:
        with self._lock:
            return {"engine": self._engine_state, "running": self._running,
                    "paused": self._paused, "current_job": self._current_job,
                    "current_page_tokens": self._tokens, "vram_used_mib": self._vram_used,
                    "engine_pid": self._engine_pid,
                    "error": dict(self._error) if self._error else None}

    # ---- thread ------------------------------------------------------
    def _settle_pause(self) -> None:
        """Called with self._lock held: a requested pause takes effect once no job is running."""
        if self._pause_requested and self._current_job is None:
            self._pause_requested = False
            self._running = False
            self._paused = True

    def _loop(self) -> None:
        while not self._stopping.is_set():
            job = None
            with self._lock:
                self._settle_pause()
                if self._running:
                    job = self._queue.next_pending()
                    if job is None:
                        self._running = False
                    else:
                        self._current_job = job.id
                        self._tokens = 0
                        self._cancel.clear()
                        self._cancel_reason = None
                        self._job_idle.clear()
            if job is not None:
                try:
                    self._run_job(job)
                except Exception as exc:     # e.g. the queue file cannot be written (disk, AV)
                    self._internal_error(job.id, exc)
                finally:
                    with self._lock:
                        self._current_job = None
                        self._tokens = 0
                        self._settle_pause()
                    self._last_work = time.monotonic()
                    self._job_idle.set()
                continue
            self._idle_check()
            self._wake.wait(_TICK_S)
            self._wake.clear()

    def _internal_error(self, job_id: str, exc: BaseException) -> None:
        """An unexpected error outside a job's own error handling: stop the queue and say so,
        instead of letting the runner thread die silently. The job goes back to pending."""
        with self._lock:
            self._running = False
            self._pause_requested = False
            self._error = {"code": "internal"}
        try:
            with open(paths.logs_dir() / "runner.log", "a", encoding="utf-8") as log:
                log.write(f"{_now()} job {job_id}\n")
                log.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            pass
        try:
            self._queue.update(job_id, state="pending")
        except Exception:
            pass    # the queue turns 'running' into 'pending' at the next app start anyway

    def _idle_check(self) -> None:
        try:
            minutes = int(self._settings_get().get("idle_stop_minutes", 10))
        except Exception:
            minutes = 10
        if minutes <= 0 or self._engine is None:
            return
        if time.monotonic() - self._last_work >= minutes * self._idle_unit_s:
            self._drop_engine()

    # ---- one job -----------------------------------------------------
    def _run_job(self, job: Job) -> None:
        settings = self._settings_get()
        mode = job.mode or settings.get("mode_default") or "quality"
        options = self._options(settings, mode)
        source = Path(job.source)
        self._queue.update(job.id, state="running", error=None, finished=None)
        try:
            if not source.is_file():
                raise FileNotFoundError(f"source file not found: {source}")
            sources = pages.list_pages(source)
            self._queue.update(job.id, pages_total=len(sources))
            resume = resume_file(job.id)
            doc = load_sidecar(resume) if resume.exists() else self._new_document(source)
            done = {p.index for p in doc.pages}
            self._queue.update(job.id, pages_done=len(done))
            scratch = paths.work_dir(job.id) / "scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            deaths = [0]
            for page_source in sources:
                if page_source.index in done:
                    continue
                if self._stop_before_page(job.id):
                    return
                page = self._read_page(source, page_source, options, scratch, deaths)
                if page is None:
                    self._finish_interrupted(job.id)
                    return
                doc.pages.append(page)
                doc.pages.sort(key=lambda p: p.index)
                save_sidecar(doc, resume)
                current = self._queue.get(job.id)
                self._queue.update(job.id, pages_done=current.pages_done + 1,
                                   warnings=current.warnings + len(page.warnings),
                                   seconds=current.seconds + page.seconds)
                self._last_work = time.monotonic()
            outputs = self._export(doc, source, settings)
            self._queue.update(job.id, state="done", outputs=outputs, finished=_now(), error=None)
            discard_work(job.id)
        except _VramShort as exc:
            self._queue.update(job.id, state="pending")
            with self._lock:
                self._running = False
                self._error = exc.info
        except EngineError as exc:
            if exc.kind == "not_installed":
                self._queue.update(job.id, state="pending")
                with self._lock:
                    self._running = False
                    self._error = {"code": "not_installed"}
                return
            if exc.kind == "died":
                self._drop_engine()
            self._queue.update(job.id, state="failed", error=str(exc), finished=_now())
        except Exception as exc:
            self._queue.update(job.id, state="failed", error=f"{type(exc).__name__}: {exc}",
                               finished=_now())

    def _stop_before_page(self, job_id: str) -> bool:
        with self._lock:
            if not (self._cancel.is_set() or self._stopping.is_set() or self._pause_requested):
                return False
        self._finish_interrupted(job_id)
        return True

    def _finish_interrupted(self, job_id: str) -> None:
        with self._lock:
            if self._stopping.is_set():
                reason = "shutdown"
            elif self._cancel.is_set():
                reason = self._cancel_reason or "cancel"
            else:
                reason = "pause"
        if reason == "cancel":
            self._queue.update(job_id, state="cancelled", finished=_now())
        elif reason == "shutdown":
            self._queue.update(job_id, state="pending")
        else:  # 'pause' or 'stop_engine'
            self._queue.update(job_id, state="paused")

    def _read_page(self, source: Path, page_source, options: ProcessOptions, scratch: Path,
                   deaths: list[int]) -> Page | None:
        opts = options
        oom_retried = False
        while True:
            if self._cancel.is_set() or self._stopping.is_set():
                return None
            try:
                engine = self._fast_proxy if oom_retried else self._proxy
                page = process_page(source, page_source, engine, opts, scratch,
                                    on_progress=self._on_tokens, cancel=self._cancel)
            except _Interrupted:
                return None
            except EngineError as exc:
                if self._cancel.is_set() or self._stopping.is_set():
                    return None
                # Also in Fast mode: process_page retries an empty page in Quality internally.
                if exc.kind == "out_of_memory" and not oom_retried:
                    oom_retried = True
                    opts = replace(opts, mode="fast")
                    continue
                if exc.kind == "died" and deaths[0] == 0:
                    deaths[0] += 1
                    self._drop_engine()
                    continue
                raise
            if self._cancel.is_set():
                return None
            if oom_retried:
                page.warnings.insert(0, OOM_WARNING)
                if page.mode is not None:   # process_page records its internal retry's mode
                    page.mode = "fast"
            return page

    def _on_tokens(self, tokens: int) -> None:
        with self._lock:
            self._tokens = int(tokens)

    def _options(self, settings: dict, mode: str) -> ProcessOptions:
        return ProcessOptions(mode=mode, dpi=int(settings.get("pdf_dpi", 200)),
                              use_text_layer=settings.get("use_text_layer", "born_digital"),
                              language=settings.get("document_language", "auto"),
                              repairs_enabled=bool(settings.get("repairs_enabled", True)),
                              time_limit_s=float(settings.get("time_limit_s", 300)),
                              personal_words=frozenset(settings.get("personal_words") or []))

    def _new_document(self, source: Path) -> Document:
        spec = registry.UNLIMITED_OCR
        return Document(source_path=str(source), engine_id=spec.engine_id,
                        engine_revision=spec.revision, app_version=__version__,
                        created=datetime.now().astimezone().isoformat(timespec="seconds"),
                        pages=[])

    def _export(self, doc: Document, source: Path, settings: dict) -> dict[str, str]:
        outputs = export_document(doc, source, settings.get("formats") or ["md"], settings)
        sidecar = paths.unique_path(output_dir(source, settings) / f"{source.stem}.owl.json")
        save_sidecar(doc, sidecar)
        outputs["owl"] = str(sidecar)
        return outputs

    # ---- engine ------------------------------------------------------
    def _set_engine_state(self, state: str) -> None:
        with self._lock:
            self._engine_state = state

    def _ocr(self, image, mode, max_new_tokens, time_limit_s, on_progress, cancel):
        cancel = cancel or self._cancel
        if cancel.is_set():
            raise _Interrupted()
        engine = self._ensure_engine(mode)
        if cancel.is_set():
            raise _Interrupted()
        with self._lock:
            if self._engine is engine:   # not if shutdown() dropped it a moment ago
                self._engine_state = "busy"
        try:
            result = engine.ocr_page(image, mode, max_new_tokens, time_limit_s,
                                     on_progress=on_progress, cancel=cancel)
        finally:
            with self._lock:
                if self._engine is engine and self._engine_state == "busy":
                    self._engine_state = "ready"
        if not engine.is_running():   # plan A note 24: the worker ended itself (engine_exiting)
            with self._engine_lock:
                if self._engine is engine:
                    self._drop_engine()
        if result.peak_vram_mib:
            with self._lock:
                self._vram_used = int(result.peak_vram_mib)
        return result

    def _ensure_engine(self, mode: str):
        with self._engine_lock:
            self._raise_if_interrupted(None)
            if self._engine is not None and not self._engine.is_running():
                self._drop_engine()
            if self._engine is None:
                try:
                    self._engine = self._engine_factory()
                except EngineError as exc:
                    if exc.kind == "not_installed":
                        self._set_engine_state("not_installed")
                    raise
            engine = self._engine
            if engine.loaded:
                self._set_engine_state("ready")
                return engine
        # The free-VRAM probe (nvidia-smi, up to 15 s) runs without _engine_lock, so that
        # stop_engine() and shutdown() are never kept waiting by it.
        self._check_vram(engine, mode)
        with self._engine_lock:
            self._raise_if_interrupted(engine)   # stopped, closed or cancelled during the probe
            self._set_engine_state("loading")
        # start() and load() run without _engine_lock: stop_engine() and shutdown()
        # must be able to stop a loading worker at once from their own thread (plan A note 7).
        try:
            if not engine.is_running():
                info = engine.start()
                with self._engine_lock:
                    if self._interrupted(engine):   # stopped while the worker was starting
                        raise _Interrupted()        # the except below stops this worker
                    with self._lock:
                        self._engine_pid = info.pid
            engine.load()
        except Exception:
            with self._engine_lock:
                if self._engine is engine:
                    self._drop_engine()
                else:   # already dropped, possibly before start() spawned the worker: end it
                    try:
                        engine.stop(timeout_s=5.0)
                    except Exception:
                        pass
            if self._cancel.is_set() or self._stopping.is_set():
                raise _Interrupted() from None
            raise
        with self._engine_lock:
            if self._engine is not engine:      # dropped by stop_engine()/shutdown() while loading
                engine.stop(timeout_s=5.0)      # plan A load() restarts a stopped worker: end it
                raise _Interrupted()
            self._set_engine_state("ready")
        return engine

    def _interrupted(self, engine) -> bool:
        """True when the page must be abandoned: cancel, stopping, or (engine given) the engine
        was dropped by stop_engine()/shutdown() meanwhile."""
        return (self._cancel.is_set() or self._stopping.is_set()
                or (engine is not None and self._engine is not engine))

    def _raise_if_interrupted(self, engine) -> None:
        if self._interrupted(engine):
            raise _Interrupted()

    def _check_vram(self, engine, mode: str) -> None:
        """Called without _engine_lock: the probe can take seconds."""
        if getattr(engine, "device", "cuda") == "cpu":
            return
        free = hardware.free_vram_mib()
        if free is None:
            return
        need = hardware.REQUIRED_FREE_VRAM_MIB[mode]
        if free < need:
            with self._engine_lock:
                if self._engine is engine:
                    self._drop_engine()
            self._raise_if_interrupted(None)   # a stop or cancel meanwhile wins over the notice
            raise _VramShort(mode, need, free)

    def _drop_engine(self) -> None:
        with self._engine_lock:
            engine, self._engine = self._engine, None
            if engine is not None:
                try:
                    engine.stop(timeout_s=5.0)
                except Exception:
                    pass
            with self._lock:
                self._engine_pid = None
                self._vram_used = None
                if self._engine_state != "not_installed" or engine is not None:
                    self._engine_state = "stopped"
