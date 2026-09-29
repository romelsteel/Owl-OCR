"""Fake engine worker: same command line and protocol as worker/owl_worker.py, no torch.

    python fake_worker.py --parent-pid <pid>

Behaviour is chosen with the environment variable FAKE_WORKER, a comma-separated list of:
  slow              2 s per page with progress events (cancel and time limit work)
  crash_on_ocr      the process exits with code 3 when it receives `ocr`
  oom_on_quality    `ocr` in quality mode answers error out_of_memory
  ignore_shutdown   `shutdown` is ignored (the client must terminate the process)
  ignore_stdin_eof  stdin EOF does not end the process (only the parent watchdog does)
  empty             every page returns empty text
  runaway           every page returns a long repetition and hit_token_cap = true
  stuck_first_pass  every page times out before its first token: an empty result with
                    engine_exiting = true, then the process exits (the real worker on a stuck GPU)
`ocr` answers with the content of "<image path>.raw.txt" when that file exists, else with
"<|det|>text [100, 100, 900, 200]<|/det|>fake text for <image name>".
"""
import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

FLAGS = {f.strip() for f in os.environ.get("FAKE_WORKER", "").split(",") if f.strip()}

_out = sys.stdout
_out_lock = threading.Lock()
_requests: "queue.Queue[dict]" = queue.Queue()
_cancelled: set[str] = set()
_cancel_all = threading.Event()        # set by `shutdown`: the page being read stops, as in the real worker
_cancel_lock = threading.Lock()


def send(message: dict) -> None:
    with _out_lock:
        _out.write(json.dumps(message, ensure_ascii=False) + "\n")
        _out.flush()


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def parent_alive(pid: int) -> bool:
    handle = _k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5           # access denied = exists
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        _k32.CloseHandle(handle)


def watchdog(parent_pid: int) -> None:
    while True:
        time.sleep(2.0)
        if not parent_alive(parent_pid):
            os._exit(0)


def reader() -> None:
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            send({"event": "error", "id": None, "kind": "internal", "message": "bad JSON"})
            continue
        if message.get("cmd") == "cancel":
            with _cancel_lock:
                _cancelled.add(str(message.get("id")))
            continue
        if message.get("cmd") == "shutdown" and "ignore_shutdown" not in FLAGS:
            _cancel_all.set()
        _requests.put(message)
    if "ignore_stdin_eof" not in FLAGS:
        os._exit(0)


def is_cancelled(request_id: str) -> bool:
    with _cancel_lock:
        return request_id in _cancelled or _cancel_all.is_set()


def page_text(image: Path) -> str:
    if "empty" in FLAGS:
        return ""
    if "runaway" in FLAGS:
        return "<|det|>text [100, 100, 900, 900]<|/det|>" + "opakuji se pořád dokola " * 1000
    raw = Path(str(image) + ".raw.txt")
    if raw.is_file():
        return raw.read_text(encoding="utf-8")
    return f"<|det|>text [100, 100, 900, 200]<|/det|>fake text for {image.name}"


def ocr(message: dict, loaded: bool) -> None:
    rid = message["id"]
    if not loaded:
        send({"event": "error", "id": rid, "kind": "not_loaded", "message": "load the model first"})
        return
    if "crash_on_ocr" in FLAGS:
        os._exit(3)
    if "oom_on_quality" in FLAGS and message["mode"] == "quality":
        send({"event": "error", "id": rid, "kind": "out_of_memory", "message": "fake CUDA out of memory"})
        return
    image = Path(message["image"])
    if not image.is_file():
        send({"event": "error", "id": rid, "kind": "bad_image", "message": f"no such file: {image}"})
        return
    t0 = time.monotonic()
    if "stuck_first_pass" in FLAGS:
        send({"event": "result", "id": rid, "text": "", "seconds": float(message["time_limit_s"]),
              "prefix_tokens": 907, "output_tokens": 0, "hit_token_cap": False, "cancelled": False,
              "timed_out": True, "peak_vram_mib": 0, "engine_exiting": True})
        os._exit(0)
    text = page_text(image)
    cancelled = timed_out = False
    if "slow" in FLAGS:
        steps = 20                                      # 20 x 0.1 s = 2 s
        for step in range(1, steps + 1):
            time.sleep(0.1)
            if step % 5 == 0:
                send({"event": "progress", "id": rid, "tokens": step * 10})
            if is_cancelled(rid):
                cancelled = True
            elif time.monotonic() - t0 > float(message["time_limit_s"]):
                timed_out = True
            if cancelled or timed_out:
                text = text[: max(1, len(text) * step // steps)]
                break
    elif is_cancelled(rid):
        cancelled, text = True, ""
    send({
        "event": "result", "id": rid, "text": text, "seconds": round(time.monotonic() - t0, 3),
        "prefix_tokens": 907 if message["mode"] == "quality" else 277,
        "output_tokens": len(text) // 3,
        "hit_token_cap": "runaway" in FLAGS,
        "cancelled": cancelled, "timed_out": timed_out, "peak_vram_mib": 0,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    threading.Thread(target=watchdog, args=(args.parent_pid,), daemon=True).start()
    threading.Thread(target=reader, daemon=True).start()
    send({"event": "ready", "pid": os.getpid(), "torch": "fake", "transformers": "fake",
          "cuda_available": False, "gpu_name": None})
    loaded = False
    while True:
        message = _requests.get()
        cmd, rid = message.get("cmd"), message.get("id")
        if cmd == "load":
            loaded = True
            send({"event": "loaded", "id": rid, "seconds": 0.01, "vram_mib": 0})
        elif cmd == "unload":
            loaded = False
            send({"event": "unloaded", "id": rid})
        elif cmd == "ping":
            send({"event": "pong", "id": rid})
        elif cmd == "ocr":
            ocr(message, loaded)
        elif cmd == "shutdown":
            if "ignore_shutdown" in FLAGS:
                continue
            send({"event": "bye", "id": rid})
            os._exit(0)
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"unknown cmd {cmd!r}"})


if __name__ == "__main__":
    sys.exit(main())
