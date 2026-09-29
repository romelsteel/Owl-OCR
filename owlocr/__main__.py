"""Entry point: python -m owlocr [--web] [--server-only] [--port N]

Default: Flask on a free 127.0.0.1 port in a background thread and the pywebview window in the
main thread. --web opens the system browser instead of the window, --server-only runs only the
server (tests, smoke checks). Closing the window shuts the engine down (design 5.6, safeguard 4).
"""
from __future__ import annotations

import sys


class _NullStream:
    """Stand-in for stdout/stderr in the windowed build, where both are None."""

    def write(self, *args, **kwargs):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

import argparse  # noqa: E402
import atexit  # noqa: E402
import ctypes  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
import webbrowser  # noqa: E402
from ctypes import wintypes  # noqa: E402
from pathlib import Path  # noqa: E402

from owlocr import paths, settings  # noqa: E402
from owlocr.engine.client import sweep_stale_worker  # noqa: E402
from owlocr.jobs.engines import engine_factory  # noqa: E402
from owlocr.jobs.queue import JobQueue  # noqa: E402
from owlocr.jobs.runner import Runner  # noqa: E402
from owlocr.pipeline import pages  # noqa: E402
from owlocr.web.bridge import Bridge  # noqa: E402
from owlocr.web.server import create_app  # noqa: E402

ERROR_ALREADY_EXISTS = 183
_mutex_handle = None  # kept for the life of the process; Windows frees it when we exit


def pick_port(preferred: int = 0) -> int:
    """Returns `preferred` when it is free, otherwise any free port on 127.0.0.1."""
    for candidate in (preferred, 0) if preferred else (0,):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", candidate))
            return sock.getsockname()[1]
        except OSError:
            continue
        finally:
            sock.close()
    raise OSError("no free port")


def mutex_name() -> str:
    digest = hashlib.sha1(str(paths.config_dir()).lower().encode("utf-8")).hexdigest()[:16]
    return f"Local\\OwlOCR-{digest}"


def acquire_single_instance() -> bool:
    """True for the first instance. The mutex name depends on the config folder, so tests with
    their own OWLOCR_CONFIG never collide with the owner's running app."""
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateMutexW(None, False, mutex_name())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def instance_file() -> Path:
    return paths.config_dir() / "instance.json"


def write_instance(port: int) -> None:
    paths.atomic_write_text(instance_file(), json.dumps({"port": port, "pid": os.getpid()}))


def focus_existing() -> bool:
    """Asks the running instance to raise its window (POST /api/focus)."""
    try:
        port = int(json.loads(instance_file().read_text(encoding="utf-8"))["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/focus", data=b"{}",
                                     method="POST",
                                     headers={"Content-Type": "application/json", "X-Owl": "1"})
    try:
        urllib.request.urlopen(request, timeout=3).close()
        return True
    except OSError:
        return False


def wait_until_up(port: int, timeout: float = 15.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _run_window(url: str, app, queue: JobQueue) -> bool:
    """Shows the window until it is closed. False when no window could be opened."""
    try:
        import webview
        from webview.dom import DOMEventHandler
    except ImportError:
        return False
    bridge = Bridge()
    try:
        window = webview.create_window("Owl OCR", url, width=1100, height=820,
                                       min_size=(760, 560), js_api=bridge)
    except Exception:
        return False
    bridge.attach(window)

    def focus() -> None:
        window.restore()
        window.show()
        window.on_top = True
        window.on_top = False

    app.config["OWL_FOCUS"] = focus
    drop_ready = {"done": False}

    def on_drop(event) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        dropped = [Path(f["pywebviewFullPath"]) for f in files if f.get("pywebviewFullPath")]
        found = pages.find_inputs(dropped) if dropped else []
        if found:
            queue.add(found)

    def on_loaded() -> None:
        if not drop_ready["done"]:
            window.dom.document.on("drop", DOMEventHandler(on_drop, True, True))
            drop_ready["done"] = True

    window.events.loaded += on_loaded
    try:
        webview.start()
    except Exception:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="owlocr")
    parser.add_argument("--web", action="store_true", help="use the system browser, not a window")
    parser.add_argument("--server-only", action="store_true", help="run only the local server")
    parser.add_argument("--port", type=int, default=0, help="port for the local server")
    args = parser.parse_args(argv)

    if not acquire_single_instance():
        focus_existing()
        return 0
    try:
        sweep_stale_worker()
    except Exception:
        pass

    queue = JobQueue(paths.queue_file())
    runner = Runner(queue, engine_factory, settings.load)
    atexit.register(runner.shutdown)
    app = create_app(runner, queue)
    port = pick_port(args.port)
    write_instance(port)

    def serve() -> None:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)

    if args.server_only:
        print(f"OWLOCR_PORT={port}", flush=True)
        try:
            serve()
        finally:
            runner.shutdown()
        return 0

    threading.Thread(target=serve, name="owl-flask", daemon=True).start()
    if not wait_until_up(port):
        # The server never came up (e.g. the port was taken before Flask bound it): opening a
        # window on that port would show a dead page or someone else's server.
        print(f"Owl OCR: the local server did not start on port {port}", file=sys.stderr, flush=True)
        runner.shutdown()
        return 1
    url = f"http://127.0.0.1:{port}/"
    try:
        if not args.web and _run_window(url, app, queue):
            return 0
        webbrowser.open(url)
        print(f"Owl OCR: {url}  (Ctrl+C to quit)", flush=True)
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        runner.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
