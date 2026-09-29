"""Low-level helpers of the engine installer: HTTPS download and running a console tool.

Both are injected into `bootstrap._run` through `install_kit.Deps`, so tests can replace them.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from owlocr import __version__
from owlocr.engine.lifetime import JobObject

CREATE_NO_WINDOW = 0x08000000
CANCELLED = -999            # return code of run_command when the cancel event stopped the tool
USER_AGENT = f"OwlOCR/{__version__}"
log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def sha256_file(path: Path, bufsize: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, on_progress: Callable[[int, int], None] | None = None,
                  cancel: threading.Event | None = None, timeout_s: float = 60.0) -> None:
    """Downloads `url` to `dest` through `<dest>.part`, resuming a previous partial download."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=timeout_s)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:            # the partial file is already complete
            os.replace(part, dest)
            return
        raise
    with response:
        if have and response.status == 206:
            mode = "ab"
        else:
            have, mode = 0, "wb"
        length = response.headers.get("Content-Length")
        total = have + int(length) if length and length.isdigit() else 0
        with open(part, mode) as fh:
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                have += len(chunk)
                if on_progress:
                    on_progress(have, total)
    if total and have != total:
        raise OSError(f"download of {url} ended at {have} of {total} bytes")
    os.replace(part, dest)


def run_command(args: list[str], env: dict[str, str], on_line: Callable[[str], None],
                cancel: threading.Event | None = None, cwd: Path | None = None) -> int:
    """Runs a console program without a window, feeding each output line to `on_line`.

    stdout and stderr are merged. The process and its children live in a Job Object, so
    cancelling (or the app dying) ends all of them. Returns the exit code, or CANCELLED.
    """
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, cwd=str(cwd) if cwd else None,
                            creationflags=CREATE_NO_WINDOW)
    job = JobObject()
    try:
        try:
            job.assign(proc.pid)
        except OSError:
            pass                                # already finished: nothing left to supervise

        def pump() -> None:
            assert proc.stdout is not None
            failed = False
            for raw in proc.stdout:             # always drain, or the tool blocks on a full pipe
                if failed:
                    continue
                try:
                    on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))
                except Exception:               # e.g. the install log hit a full disk
                    failed = True
                    log.warning("output handler failed; the rest of the output is discarded", exc_info=True)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                job.close()                     # kills the whole process tree
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=30)
                reader.join(timeout=5)
                return CANCELLED
            time.sleep(0.2)
        reader.join(timeout=5)
        return proc.returncode
    finally:
        job.close()                             # closing twice is harmless (plan A)
