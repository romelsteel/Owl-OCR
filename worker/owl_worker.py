"""Owl OCR engine worker. Runs inside the engine's own Python (torch + transformers + model).

    python owl_worker.py --parent-pid <pid>

Protocol (design 5.4): one JSON object per line. Requests arrive on stdin, events leave on stdout.
Nothing else may reach stdout: main() points sys.stdout at stderr, so prints of the model code and
of libraries land in the app's engine.log.

The worker exits on stdin EOF, on `shutdown`, and when the parent process is gone (checked every
2 s). The app also starts it inside a Job Object, so it dies with the app in every case.

This file must not import owlocr: it is copied on its own into <data root>\\engine\\worker.
torch and transformers are imported inside functions so the control logic can be unit-tested
without them.
"""
import argparse
import ctypes
import gc
import json
import msvcrt
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

PROMPT = "<image>document parsing."
MODES = {
    "quality": {"base_size": 1024, "image_size": 640, "crop_mode": True},
    "fast": {"base_size": 1024, "image_size": 1024, "crop_mode": False},
}
NO_REPEAT_NGRAM_SIZE = 35
NGRAM_WINDOW = 128
PLACEHOLDER_MAX_LENGTH = 8192     # replaced per page by prefix_tokens + max_new_tokens
PROGRESS_INTERVAL_S = 0.5
WATCHDOG_INTERVAL_S = 2.0

_proto = None                     # the protocol stream, set by _claim_stdout() in main()
_proto_lock = threading.Lock()


def send(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False) + "\n"
    with _proto_lock:
        stream = _proto or sys.__stdout__
        stream.write(line)
        stream.flush()


def log(text: str) -> None:
    print(f"[worker] {text}", file=sys.stderr, flush=True)


def _claim_stdout() -> None:
    """Keep the real stdout for the protocol (UTF-8, bare \\n) and point sys.stdout at stderr:
    prints of the model code and of libraries must not corrupt the protocol."""
    global _proto
    _proto = sys.stdout
    _proto.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout = sys.stderr


# ---- scratch folders and exit ---------------------------------------------------------------

_scratch_lock = threading.Lock()
_SCRATCH: list[Path] = []         # temp folders of every Engine, removed on exit


def _remove_scratch() -> None:
    with _scratch_lock:
        folders = list(_SCRATCH)
        _SCRATCH.clear()
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


def _exit(code: int) -> None:
    """Every way out of the worker (shutdown, stdin EOF, parent gone): remove the scratch
    folders, then end the process at once (os._exit: the other threads may be mid-generation)."""
    try:
        _remove_scratch()
    finally:
        os._exit(code)


# ---- parent watchdog (design 5.6, safeguard 3) -----------------------------------------------

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.restype = wintypes.BOOL
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.SetStdHandle.restype = wintypes.BOOL
_k32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
_STD_INPUT_HANDLE = 0xFFFFFFF6        # (DWORD)-10


def parent_alive(pid: int) -> bool:
    handle = _k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5                # access denied: it exists
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        _k32.CloseHandle(handle)


def watchdog(parent_pid: int) -> None:
    while True:
        time.sleep(WATCHDOG_INTERVAL_S)
        if not parent_alive(parent_pid):
            log(f"parent {parent_pid} is gone, exiting")
            _exit(0)


# ---- control shared between the stdin reader and generation ---------------------------------

class Control:
    """Cancel flag, time limit and progress throttle for the page being read."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.request_id: str | None = None
        self.pending_cancels: set[str] = set()   # cancels that arrived before their ocr started
        self.shutting_down = False               # a shutdown arrived: every page from now on stops
        self.cancel_requested = False
        self.started = 0.0
        self.time_limit_s = 0.0
        self.prefix_tokens = 0
        self.cancelled = False
        self.timed_out = False
        self.last_progress = 0.0
        self.last_tokens = -1
        self.decoding = False                    # set by the first should_stop(): a token exists

    def begin(self, request_id: str, time_limit_s: float) -> None:
        with self.lock:
            self.request_id = request_id
            self.cancel_requested = self.shutting_down or request_id in self.pending_cancels
            self.pending_cancels.discard(request_id)
            self.cancelled = self.timed_out = False
            self.started = time.monotonic()
            self.time_limit_s = float(time_limit_s)
            self.prefix_tokens = 0
            self.last_progress = self.started
            self.last_tokens = -1
            self.decoding = False

    def end(self) -> None:
        with self.lock:
            self.request_id = None

    def cancel(self, request_id: str | None = None) -> None:
        """request_id None cancels whatever is running (used on shutdown)."""
        with self.lock:
            if request_id is None:
                self.shutting_down = True        # also stops an ocr dequeued but not yet begun
            if self.request_id is not None and (request_id is None or request_id == self.request_id):
                self.cancel_requested = True
            elif request_id is not None:
                self.pending_cancels.add(request_id)

    def prefill_should_stop(self) -> bool:
        """Called before every module of the model runs. Before the first token exists the
        stopping criteria never run, and the first forward pass (vision encoder + the whole
        prompt) can take minutes when VRAM spills into shared memory; this is the only check
        that ends such a page. Once tokens exist it answers False: should_stop() ends the page
        between tokens, so the text read so far is kept."""
        if self.decoding or self.request_id is None:     # fast path, runs for every module
            return False
        with self.lock:
            if self.request_id is None or self.decoding:
                return False
            if self.cancel_requested:
                self.cancelled = True
            elif time.monotonic() - self.started > self.time_limit_s:
                self.timed_out = True
            return self.cancelled or self.timed_out

    def should_stop(self, total_tokens: int) -> bool:
        """Called after every generated token with the length of the whole sequence."""
        now = time.monotonic()
        with self.lock:
            self.decoding = True
            generated = max(0, total_tokens - self.prefix_tokens)
            if self.cancel_requested:
                self.cancelled = True
            elif now - self.started > self.time_limit_s:
                self.timed_out = True
            emit = (self.request_id is not None and generated != self.last_tokens
                    and now - self.last_progress >= PROGRESS_INTERVAL_S)
            if emit:
                self.last_progress, self.last_tokens = now, generated
            request_id, stop = self.request_id, self.cancelled or self.timed_out
        if emit:
            send({"event": "progress", "id": request_id, "tokens": generated})
        return stop


class PageStopped(Exception):
    """Raised inside the forward pass when the page is cancelled or out of time before its
    first token. Engine.ocr() catches it: the page ends with no text."""


CONTROL = Control()
REQUESTS: "queue.Queue[dict]" = queue.Queue()


def detach_stdin():
    """Move the request pipe away from the standard input handle and return it as a stream.

    Windows serialises synchronous I/O per file object: while the reader thread waits in
    ReadFile on the pipe, any GetFileType() on the same handle blocks. Every DLL with its own C
    runtime calls GetFileType() on the standard handles when it loads, and torch loads many (at
    import and lazily on first CUDA use), so a reader on the real stdin deadlocks the worker.
    After this call the standard input handle is NUL and only the reader touches the pipe."""
    pipe_fd = os.dup(0)
    null_fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_fd, 0)
    os.close(null_fd)
    _k32.SetStdHandle(_STD_INPUT_HANDLE, msvcrt.get_osfhandle(0))
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    return os.fdopen(pipe_fd, "rb")


def reader(stream) -> None:
    """Reads requests. `cancel` is handled here at once; everything else is queued for the main
    thread. EOF means the app is gone or closed the pipe: exit immediately."""
    for raw in stream:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or "cmd" not in message:
                raise ValueError("no cmd")
        except ValueError:
            send({"event": "error", "id": None, "kind": "internal", "message": f"bad request: {line[:200]}"})
            continue
        if message["cmd"] == "cancel":
            CONTROL.cancel(str(message.get("id")))
            continue
        if message["cmd"] == "shutdown":
            CONTROL.cancel()
        REQUESTS.put(message)
    log("stdin closed, exiting")
    _exit(0)


# ---- the model --------------------------------------------------------------------------

class Engine:
    def __init__(self) -> None:
        self.tokenizer = None
        self.model = None
        self.device = "cuda"
        self.max_new_tokens = 6000
        self.last: dict = {}
        self.gpu_stuck = False            # set by ocr(): handle() exits after the reply
        with _scratch_lock:           # an exit in between would otherwise miss the new folder
            self.scratch = Path(tempfile.mkdtemp(prefix="owl_worker_"))
            _SCRATCH.append(self.scratch)

    def load(self, model_dir: str, device: str, dtype: str) -> tuple[float, int]:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.unload()
        t0 = time.perf_counter()
        folder = str(Path(model_dir).resolve())
        tokenizer = AutoTokenizer.from_pretrained(folder, trust_remote_code=True, local_files_only=True)
        # AutoModel, not the class itself: only AutoModel injects generate() into the remote code.
        # Never pass attn_implementation (design 5.2).
        model = AutoModel.from_pretrained(folder, trust_remote_code=True, use_safetensors=True,
                                          dtype=getattr(torch, dtype), local_files_only=True).eval()
        if device == "cuda":
            model = model.cuda()
        self._wrap_generate(model)
        self.tokenizer, self.model, self.device = tokenizer, model, device
        vram = torch.cuda.memory_allocated() // 2**20 if device == "cuda" else 0
        return time.perf_counter() - t0, int(vram)

    def _wrap_generate(self, model) -> None:
        """infer() only knows max_length (prompt + output) and reports nothing. The wrapper learns
        the prompt length, turns max_new_tokens into max_length and adds the stopping criteria."""
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        class _Stop(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                stop = CONTROL.should_stop(int(input_ids.shape[1]))
                return torch.full((input_ids.shape[0],), stop, dtype=torch.bool, device=input_ids.device)

        def _check_before_module(module, args):
            if CONTROL.prefill_should_stop():
                raise PageStopped()

        for module in model.modules():
            module.register_forward_pre_hook(_check_before_module)

        original = model.generate
        engine = self

        def generate(*args, **kwargs):
            prefix = int(kwargs["input_ids"].shape[1])
            with CONTROL.lock:
                CONTROL.prefix_tokens = prefix
            kwargs["max_length"] = prefix + engine.max_new_tokens
            criteria = StoppingCriteriaList(list(kwargs.get("stopping_criteria") or []))
            criteria.append(_Stop())
            kwargs["stopping_criteria"] = criteria
            engine.last = {"prefix_tokens": prefix, "output_tokens": 0, "hit_token_cap": False}
            out = original(*args, **kwargs)   # PageStopped passes through to Engine.ocr()
            engine.last = {"prefix_tokens": prefix, "output_tokens": int(out.shape[1]) - prefix,
                           "hit_token_cap": int(out.shape[1]) >= kwargs["max_length"]}
            return out

        model.generate = generate

    def unload(self) -> None:
        if self.model is None:
            return
        import torch

        self.model = self.tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def ocr(self, request_id: str, image: str, mode: str, max_new_tokens: int, time_limit_s: float) -> dict:
        import torch

        self.max_new_tokens = int(max_new_tokens)
        self.last = {"prefix_tokens": 0, "output_tokens": 0, "hit_token_cap": False}
        self.gpu_stuck = False
        cuda = self.device == "cuda"
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        config = getattr(self.model, "config", None)
        sliding_window = getattr(config, "sliding_window", None)
        CONTROL.begin(request_id, time_limit_s)
        t0 = time.perf_counter()
        try:
            # eval_mode=True returns the text. NEVER save_results=True: that path runs Python
            # eval() on model output. The n-gram guard defaults to 0 and must be passed.
            text = self.model.infer(self.tokenizer, prompt=PROMPT, image_file=image,
                                    output_path=str(self.scratch), max_length=PLACEHOLDER_MAX_LENGTH,
                                    no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE, ngram_window=NGRAM_WINDOW,
                                    eval_mode=True, **MODES[mode])
        except PageStopped:
            # Stopped before the first token. Leave infer() at once: what it does after generate()
            # copies tensors to and from the GPU, which waits until every kernel already queued
            # there has run - minutes when VRAM has spilled into shared memory (GPU run
            # 2026-09-28). infer() clears config.sliding_window for generate() and puts it back
            # only on success, so put it back here.
            text = ""
            if config is not None:
                config.sliding_window = sliding_window
            # A time limit hit before the first token means the GPU is far behind (a normal first
            # pass takes about a second). Queued GPU work cannot be cancelled; only ending the
            # process discards it, so handle() exits after sending the result.
            self.gpu_stuck = cuda and CONTROL.timed_out
        finally:
            CONTROL.end()
        seconds = time.perf_counter() - t0
        peak = torch.cuda.max_memory_allocated() // 2**20 if cuda else 0
        stopped = CONTROL.cancelled or CONTROL.timed_out
        return {"event": "result", "id": request_id, "text": text or "", "seconds": round(seconds, 3),
                "prefix_tokens": self.last["prefix_tokens"], "output_tokens": self.last["output_tokens"],
                "hit_token_cap": bool(self.last["hit_token_cap"]) and not stopped,
                "cancelled": CONTROL.cancelled, "timed_out": CONTROL.timed_out, "peak_vram_mib": int(peak)}


def _is_out_of_memory(error: BaseException) -> bool:
    if isinstance(error, MemoryError):
        return True
    torch = sys.modules.get("torch")
    if torch is not None and isinstance(error, torch.cuda.OutOfMemoryError):
        return True
    text = str(error).lower()
    return isinstance(error, RuntimeError) and ("out of memory" in text or "can't allocate memory" in text)


def _check_image(image: str) -> str | None:
    from PIL import Image

    path = Path(image)
    if not path.is_file():
        return f"no such file: {image}"
    try:
        with Image.open(path) as im:
            im.load()
    except Exception as e:  # noqa: BLE001 - any decoder error means the page cannot be read
        return f"cannot read image {path.name}: {e}"
    return None


def _free_cuda_cache() -> None:
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


# Required fields per request, as in design 5.4 (owlocr.engine.protocol.REQUEST_FIELDS; this file
# must not import owlocr). cancel never reaches handle(): the reader deals with it.
REQUEST_FIELDS = {
    "load": ("id", "model_dir", "device", "dtype"),
    "ocr": ("id", "image", "mode", "max_new_tokens", "time_limit_s"),
    "unload": ("id",),
    "ping": ("id",),
    "shutdown": ("id",),
}


def handle(engine: Engine, message: dict) -> None:
    cmd, rid = message.get("cmd"), message.get("id")
    missing = [name for name in REQUEST_FIELDS.get(cmd, ()) if name not in message]
    if missing:
        # Checked up front: a KeyError from inside load/ocr is an engine failure, not a bad request.
        send({"event": "error", "id": rid, "kind": "internal", "message": f"missing field {missing[0]!r}"})
        return
    try:
        if cmd == "ping":
            send({"event": "pong", "id": rid})
        elif cmd == "load":
            seconds, vram = engine.load(message["model_dir"], message["device"], message["dtype"])
            send({"event": "loaded", "id": rid, "seconds": round(seconds, 2), "vram_mib": vram})
        elif cmd == "unload":
            engine.unload()
            send({"event": "unloaded", "id": rid})
        elif cmd == "ocr":
            if engine.model is None:
                send({"event": "error", "id": rid, "kind": "not_loaded", "message": "load the model first"})
                return
            if message["mode"] not in MODES:
                send({"event": "error", "id": rid, "kind": "internal",
                      "message": f"unknown mode {message['mode']!r}"})
                return
            problem = _check_image(message["image"])
            if problem:
                send({"event": "error", "id": rid, "kind": "bad_image", "message": problem})
                return
            result = engine.ocr(rid, message["image"], message["mode"], message["max_new_tokens"],
                                message["time_limit_s"])
            if engine.gpu_stuck:
                result["engine_exiting"] = True
            send(result)
            if engine.gpu_stuck:
                log("page timed out before its first token; the GPU is still busy with it, "
                    "exiting so its queued work is discarded (the app restarts the engine)")
                _exit(0)
            else:
                # expandable_segments is not supported on Windows, so the allocator cache
                # fragments from page to page; without this the eighth test page grew past the
                # dedicated VRAM and spilled into shared memory (GPU run 2026-09-28).
                _free_cuda_cache()
        elif cmd == "shutdown":
            send({"event": "bye", "id": rid})
            _exit(0)
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"unknown cmd {cmd!r}"})
    except Exception as e:  # noqa: BLE001 - the worker must answer, whatever happened
        log(traceback.format_exc())
        if _is_out_of_memory(e):
            _free_cuda_cache()
            send({"event": "error", "id": rid, "kind": "out_of_memory", "message": str(e)[:500]})
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"{type(e).__name__}: {e}"[:500]})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    _claim_stdout()
    threading.Thread(target=watchdog, args=(args.parent_pid,), name="watchdog", daemon=True).start()
    threading.Thread(target=reader, args=(detach_stdin(),), name="stdin", daemon=True).start()

    import torch
    import transformers

    cuda = torch.cuda.is_available() and torch.cuda.device_count() > 0
    gpu_name = None
    if cuda:
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001 - a name is nice to have, not required
            cuda = False
    engine = Engine()                 # before ready: its scratch folder exists once the app sees ready
    send({"event": "ready", "pid": os.getpid(), "torch": torch.__version__,
          "transformers": transformers.__version__, "cuda_available": cuda, "gpu_name": gpu_name})
    while True:
        handle(engine, REQUESTS.get())


if __name__ == "__main__":
    sys.exit(main())
