"""SubprocessEngine: runs the engine worker as a child process and talks JSON lines to it.

The worker runs in the engine's own Python (with torch). It is started inside a Windows Job
Object, gets the app's pid for its watchdog, and exits on stdin EOF (design 5.6). Its stderr goes
to logs/engine.log. One request is in flight at a time.
"""
import itertools
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.protocol import MODES, EngineError, EngineInfo, PageResult, ProtocolError, decode, encode

_CREATE_NO_WINDOW = 0x08000000
_START_TIMEOUT_S = 180.0      # importing torch on a cold disk can take a minute
_LOAD_TIMEOUT_S = 900.0
_OCR_GRACE_S = 120.0          # on top of the page's own time limit
_EXIT_WAIT_S = 10.0           # for a worker that announced engine_exiting
_SMALL_TIMEOUT_S = 60.0
_ANY = object()               # _cleanup(): clean up whatever worker is current


class SubprocessEngine:
    engine_id = "unlimited_ocr"

    def __init__(self, python: Path, worker_script: Path, model_dir: Path,
                 device: str, dtype: str, log_file: Path, env: dict | None = None) -> None:
        self.python = Path(python)
        self.worker_script = Path(worker_script)
        self.model_dir = Path(model_dir)
        self.device = device
        self.dtype = dtype
        self.log_file = Path(log_file)
        self.env = dict(env or {})
        self._proc: subprocess.Popen | None = None
        self._job: lifetime.JobObject | None = None
        self._log = None
        self._events: queue.Queue = queue.Queue()
        self._request_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()   # stop() and a dying request may clean up at once
        self._ids = itertools.count(1)
        self._loaded = False
        self._died = False
        self._info: EngineInfo | None = None

    # ---- process -------------------------------------------------------------------------

    def _worker_env(self) -> dict:
        env = dict(os.environ)
        env.update({
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "HF_HOME": str(paths.hf_home()),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        })
        env.update(self.env)
        return env

    def start(self) -> EngineInfo:
        if self.is_running() and self._info is not None:
            return self._info
        self._cleanup()
        self._died = False
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_file, "ab")
        self._log.write(f"\n--- engine start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode("utf-8"))
        self._log.flush()
        cmd = [str(self.python), "-u", str(self.worker_script), "--parent-pid", str(os.getpid())]
        try:
            self._job = lifetime.JobObject()   # before Popen: a failure here leaves no worker behind
        except OSError as e:
            self._cleanup()
            raise EngineError("internal", f"cannot create the engine's job object: {e}") from e
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
                                    cwd=str(self.worker_script.parent), env=self._worker_env(),
                                    creationflags=_CREATE_NO_WINDOW)
        except OSError as e:
            self._cleanup()
            raise EngineError("not_installed", f"cannot start {self.python}: {e}") from e
        self._proc = proc
        try:
            # The venv launcher may start its child before this assign; accepted: the launcher kills
            # its child when it dies, and the parent-alive watchdog and stdin EOF also end the worker.
            self._job.assign(proc.pid)
        except OSError as e:
            # A live worker outside the job would break design 5.6: kill it and report.
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            self._cleanup()
            raise EngineError("internal", f"cannot put the engine into its job object: {e}") from e
        self._events = queue.Queue()
        threading.Thread(target=self._read_events, args=(proc, self._events),
                         name="owl-engine-reader", daemon=True).start()
        ready = self._wait(proc, self._events, None, {"ready"}, _START_TIMEOUT_S)
        self._info = EngineInfo(pid=int(ready["pid"]), torch=str(ready["torch"]),
                                transformers=str(ready["transformers"]),
                                cuda_available=bool(ready["cuda_available"]), gpu_name=ready["gpu_name"])
        _write_pid_file(self._info.pid)
        return self._info

    def _read_events(self, proc: subprocess.Popen, events: queue.Queue) -> None:
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    events.put(decode(line))
                except ProtocolError as e:
                    self._log_line(f"[client] ignored bad line from worker: {e}")
        except (OSError, ValueError):
            pass
        events.put(None)

    def _log_line(self, text: str) -> None:
        log = self._log
        if log is not None and not log.closed:
            try:
                log.write((text + "\n").encode("utf-8"))
                log.flush()
            except (OSError, ValueError):
                pass

    def _send(self, message: dict, proc: subprocess.Popen | None = None) -> None:
        if proc is None:
            proc = self._proc
        if proc is None or proc.stdin is None:
            raise EngineError("died", "engine is not running")
        with self._send_lock:
            try:
                proc.stdin.write(encode(message).encode("utf-8"))
                proc.stdin.flush()
            except (OSError, ValueError) as e:
                raise EngineError("died", f"cannot write to the engine: {e}") from e

    def _wait(self, proc: subprocess.Popen, events: queue.Queue, request_id: str | None,
              done: set[str], timeout: float,
              on_progress: Callable[[int], None] | None = None,
              cancel: threading.Event | None = None) -> dict:
        """Wait for the answer of the worker `proc` (not whatever worker is current by then)."""
        deadline = time.monotonic() + timeout
        cancel_sent = False
        while True:
            if cancel is not None and cancel.is_set() and not cancel_sent and request_id is not None:
                self._send({"cmd": "cancel", "id": request_id}, proc)
                cancel_sent = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._die(proc, f"no answer within {timeout:.0f} s")
            try:
                event = events.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue
            if event is None:
                self._die(proc, f"worker exited (code {proc.poll()}); see {self.log_file}")
            if request_id is not None and event.get("id") != request_id:
                continue          # late event of an earlier request
            kind = event["event"]
            if kind == "progress":
                if on_progress is not None:
                    on_progress(int(event["tokens"]))
                continue
            if kind == "error":
                raise EngineError(str(event["kind"]), str(event["message"]))
            if kind in done:
                return event

    def _die(self, proc: subprocess.Popen, message: str):
        if proc.poll() is None:
            proc.kill()
        self._cleanup(expected=proc, died=True)
        raise EngineError("died", message)

    def _request(self, cmd: str, fields: dict, done: set[str], timeout: float,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> dict:
        with self._request_lock:
            proc, events = self._proc, self._events
            if proc is None or proc.poll() is not None:
                raise EngineError("died" if self._died else "not_loaded", "engine is not running")
            request_id = str(next(self._ids))
            self._send({"cmd": cmd, "id": request_id, **fields}, proc)
            event = self._wait(proc, events, request_id, done, timeout, on_progress, cancel)
            if event.get("engine_exiting"):
                # The worker answered and is ending itself (a page timed out before its first
                # token: the GPU work queued for it cannot be cancelled). Wait for it and clean
                # up here, so the next request finds a stopped engine instead of racing the exit.
                try:
                    proc.wait(timeout=_EXIT_WAIT_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self._cleanup(expected=proc)
            return event

    # ---- public API ----------------------------------------------------------------------

    def load(self) -> float:
        if not self.is_running():
            self.start()
        event = self._request("load", {"model_dir": str(self.model_dir), "device": self.device,
                                       "dtype": self.dtype}, {"loaded"}, _LOAD_TIMEOUT_S)
        self._loaded = True
        return float(event["seconds"])

    def ocr_page(self, image: Path, mode: str, max_new_tokens: int = 6000,
                 time_limit_s: float = 300.0,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> PageResult:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        event = self._request("ocr", {"image": str(Path(image).resolve()), "mode": mode,
                                      "max_new_tokens": int(max_new_tokens),
                                      "time_limit_s": float(time_limit_s)},
                              {"result"}, float(time_limit_s) + _OCR_GRACE_S, on_progress, cancel)
        return PageResult(text=str(event["text"]), seconds=float(event["seconds"]),
                          prefix_tokens=int(event["prefix_tokens"]),
                          output_tokens=int(event["output_tokens"]),
                          hit_token_cap=bool(event["hit_token_cap"]), cancelled=bool(event["cancelled"]),
                          timed_out=bool(event["timed_out"]), peak_vram_mib=int(event["peak_vram_mib"]))

    def unload(self) -> None:
        if self.is_running():
            self._request("unload", {}, {"unloaded"}, _SMALL_TIMEOUT_S)
        self._loaded = False

    def stop(self, timeout_s: float = 5.0) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                self._send({"cmd": "shutdown", "id": "stop"}, proc)
            except EngineError:
                pass
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        # Only the worker this call stopped: a runner may already have started a new one.
        self._cleanup(expected=proc)

    def is_running(self) -> bool:
        proc = self._proc                  # read once: stop() may clear it from another thread
        return proc is not None and proc.poll() is None

    @property
    def loaded(self) -> bool:
        return self._loaded and self.is_running()

    def _cleanup(self, expected=_ANY, died: bool = False) -> None:
        # Take everything out under the lock, so a second concurrent caller finds only None
        # and nothing (above all the Job Object handle) is closed twice. With `expected`, clean up
        # only if that worker is still the current one (a newer worker is left alone).
        with self._cleanup_lock:
            if expected is not _ANY and self._proc is not expected:
                if died and self._proc is None:
                    self._died = True      # stop() cleaned up first; later calls still say "died"
                return
            if died:
                self._died = True
            proc, self._proc = self._proc, None
            job, self._job = self._job, None
            info, self._info = self._info, None
            log, self._log = self._log, None
            self._loaded = False
            if proc is not None and proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            if job is not None:
                job.close()                # kills whatever is left of the worker
            if info is not None:
                _remove_pid_file(info.pid)
            if log is not None:
                try:
                    log.close()
                except OSError:
                    pass


# ---- worker.pid (read by sweep_stale_worker) ------------------------------------------------

def _pid_file() -> Path:
    return paths.engine_dir() / "worker.pid"


def _write_pid_file(pid: int) -> None:
    """The worker and its owner (this process), each with its creation time: the sweep of another
    Owl OCR process must leave a worker alone while the process that started it still runs."""
    owner = os.getpid()
    paths.atomic_write_text(_pid_file(), json.dumps({
        "pid": pid, "created": lifetime._process_create_time(pid),
        "owner": owner, "owner_created": lifetime._process_create_time(owner)}))


def _remove_pid_file(pid: int) -> None:
    try:
        if json.loads(_pid_file().read_text(encoding="utf-8")).get("pid") == pid:
            _pid_file().unlink()
    except (OSError, ValueError, AttributeError):
        pass


# ---- stale worker sweep and the installed engine (design 5.6, 6.3) ------------------------

def sweep_stale_worker() -> None:
    """Terminate a worker left over from an earlier run of the app, if it is still alive.
    A worker whose owner (the app or CLI that started it) still runs is not stale: it and its
    pid file are left alone. A pid file without owner fields (older format) counts as stale."""
    path = _pid_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid, created = int(data["pid"]), data.get("created")
        owner, owner_created = data.get("owner"), data.get("owner_created")
        owner = None if owner is None else int(owner)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        path.unlink(missing_ok=True)
        return
    if owner is not None and _owner_alive(owner, owner_created):
        return
    # The creation time proves it is the same process and not a new one that reused the pid.
    if created is not None and lifetime._process_create_time(pid) == created:
        lifetime._terminate(pid)
    path.unlink(missing_ok=True)


def _owner_alive(owner: int, owner_created) -> bool:
    if owner_created is None:                   # creation time unreadable when it was written
        return lifetime.process_alive(owner)
    return lifetime._process_create_time(owner) == owner_created   # same process, pid not reused


# ---- the engine as installed ----------------------------------------------------------------

def default_engine() -> SubprocessEngine:
    """Engine described by <engine dir>/install.json (written by plan D's bootstrap, or by
    scripts/dev_engine.py in development). Optional keys python, worker_script, model_dir and
    env override the standard locations."""
    install = paths.engine_dir() / "install.json"
    try:
        data = json.loads(install.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise EngineError("not_installed", f"{install} is missing or unreadable") from e
    if not isinstance(data, dict):
        raise EngineError("not_installed", f"{install} is not a JSON object")
    engine_id = str(data.get("engine_id") or "unlimited_ocr")
    python = Path(data.get("python") or paths.engine_python())
    worker = Path(data.get("worker_script") or paths.worker_dir() / "owl_worker.py")
    model = Path(data.get("model_dir") or paths.model_dir(engine_id))
    for required in (python, worker):
        if not required.is_file():
            raise EngineError("not_installed", f"missing {required}")
    device = str(data.get("device") or "cuda")
    dtype = str(data.get("dtype") or ("bfloat16" if device == "cuda" else "float32"))
    engine = SubprocessEngine(python, worker, model, device, dtype,
                              paths.logs_dir() / "engine.log", env=data.get("env") or None)
    engine.engine_id = engine_id
    return engine
