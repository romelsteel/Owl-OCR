"""Building blocks of the engine installer: constants, the injectable dependencies, the stage
context, file and command helpers. The stages themselves are in `stages.py`.

Everything that touches the outside world goes through `Deps`, which the tests replace with fakes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import registry, store, uvtool
from owlocr.hardware import Tier, free_vram_mib

PYTHON_VERSION = "3.11"
WORKER_FILES = ("owl_worker.py", "device_patch.py")
REQUIREMENTS_REL = "worker/requirements-engine.txt"
APACHE_REL = "licenses/Apache-2.0.txt"
SELFTEST_IMAGE_REL = "owlocr/web/static/selftest.png"
PATCH_TARGET = "modeling_unlimitedocr.py"
PATCH_SENTINEL = "# --- owl-ocr device patch v1 applied ---"    # same text as worker/device_patch.py
APACHE_NAME = "LICENSE-Apache-2.0.txt"
NOTICE_NAME = "NOTICE-OwlOCR.txt"
TORCH_DOWNLOAD_BYTES = {"cu128": 2_876_740_161, "cpu": 117_675_311}   # torch + torchvision wheels
SELFTEST_WORDS = ("Vážená", "doktorko", "lékařské", "Dvořáka", "rehabilitaci")
SELFTEST_MIN_WORDS = 3
SELFTEST_MAX_NEW_TOKENS = 1500
SELFTEST_TIME_LIMIT_S = {"cuda": 180.0, "cpu": 1800.0}
INSTALL_FORMAT = 1

MODEL_NOTICE = """Owl OCR notice for this folder

The files in this folder come from https://huggingface.co/baidu/Unlimited-OCR
at revision 07dea832e22aefee32ad281d4b80551282e1c168.

- The model and most files are published by Baidu under the MIT License; see LICENSE.
- modeling_deepseekv2.py carries a header of the Apache License, Version 2.0
  (Copyright 2023 DeepSeek-AI and The HuggingFace Inc. team). The full licence text is in
  LICENSE-Apache-2.0.txt.
- On computers without a suitable NVIDIA graphics card Owl OCR modifies
  modeling_unlimitedocr.py so that it runs on the processor. The modified file starts with a
  comment that says so, and the unmodified original is kept next to it as
  modeling_unlimitedocr.py.orig.
"""


class BootstrapError(RuntimeError):
    """Installation failed. The message starts with a code: `<code>: <details>`."""


@dataclass
class Deps:
    pins: dict
    resource: Callable[[str], Path] = field(default=lambda rel: paths.resource_path(rel))
    run_cmd: Callable = uvtool.run_command
    download_file: Callable = uvtool.download_file
    engine_factory: Callable[[Tier], object] = field(default=lambda tier: default_engine(tier))
    store_is_ready: Callable[[], bool] = field(default=lambda: store.is_ready())
    store_download: Callable = field(default=lambda on_progress, cancel: store.download(
        registry.UNLIMITED_OCR, on_progress=on_progress, cancel=cancel))
    free_vram: Callable[[], int | None] = field(default=lambda: free_vram_mib())
    free_bytes: Callable[[Path], int] = field(default=lambda path: disk_free(path))


class StageContext:
    """What a stage needs: tier, dependencies, cancel flag, progress reporting and the log."""

    def __init__(self, tier: Tier, deps: Deps, cancel: threading.Event | None,
                 emit: Callable[[int, int, str], None], log: Callable[[str], None]) -> None:
        self.tier, self.deps, self.cancel, self.log = tier, deps, cancel, log
        self._emit = emit
        self.done, self.total, self.message = 0, 0, ""
        self._last = 0.0
        self._lock = threading.Lock()

    def cancelled(self) -> bool:
        return self.cancel is not None and self.cancel.is_set()

    def report(self, done: int | None = None, total: int | None = None, message: str | None = None) -> None:
        with self._lock:
            changed_text = message is not None and message != self.message
            if done is not None:
                self.done = done
            if total is not None:
                self.total = total
            if message is not None:
                self.message = message
            now = time.monotonic()
            finished = self.total > 0 and self.done >= self.total
            if not (changed_text or finished or now - self._last >= 0.25):
                return
            self._last = now
            snapshot = (self.done, self.total, self.message)
        self._emit(*snapshot)


# ---------------------------------------------------------------- paths and small helpers

def uv_exe() -> Path:
    return paths.engine_dir() / "tools" / "uv.exe"


def python_dir() -> Path:
    return paths.engine_dir() / "python"


def venv_dir() -> Path:
    return paths.engine_dir() / "venv"


def uv_cache_dir() -> Path:
    return paths.engine_dir() / "uv-cache"


def stamps_dir() -> Path:
    return paths.engine_dir() / "stamps"


def install_file() -> Path:
    return paths.engine_dir() / "install.json"


def state_file() -> Path:
    return paths.engine_dir() / "install_state.json"


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_stamp(name: str) -> dict | None:
    return read_json(stamps_dir() / f"{name}.json")


def write_stamp(name: str, data: dict) -> None:
    paths.atomic_write_text(stamps_dir() / f"{name}.json", json.dumps(data, indent=1, ensure_ascii=False))


def is_link(path: Path | str) -> bool:
    """True for a junction or symbolic link. Looks at the entry itself and never follows it.
    Other reparse points (OneDrive / cloud placeholder folders) are ordinary folders here."""
    try:
        st = os.lstat(path)
        return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and             st.st_reparse_tag in (stat.IO_REPARSE_TAG_MOUNT_POINT, stat.IO_REPARSE_TAG_SYMLINK)
    except (OSError, AttributeError):
        return False


_PYTHON_FOLDER = re.compile(rf"cpython-{re.escape(PYTHON_VERSION)}\.(\d+)-.+")


def managed_python() -> Path | None:
    """The newest real `cpython-3.11.<patch>-*` folder's python.exe. Links are ignored: under
    WebView2's RedirectionGuard even looking inside a user-created junction fails."""
    found: list[tuple[int, str, Path]] = []
    try:
        entries = list(os.scandir(python_dir()))
    except OSError:
        return None
    for entry in entries:
        match = _PYTHON_FOLDER.fullmatch(entry.name)
        if not match or is_link(entry.path):
            continue
        exe = Path(entry.path) / "python.exe"
        if exe.is_file():
            found.append((int(match.group(1)), entry.name, exe))
    return max(found)[2] if found else None          # highest patch, then name


def remove_python_links(log: Callable[[str], None] = lambda line: None) -> list[str]:
    """Deletes every junction or symbolic link directly inside `python_dir()` without following it.

    uv links `cpython-3.11-windows-x86_64-none` to the full-version folder. WebView2 turns on
    RedirectionGuard in OwlOCR.exe and every child process inherits it, so any later traversal
    of that user-created junction fails with os error 448. Nothing of ours needs the link."""
    removed: list[str] = []
    try:
        entries = list(os.scandir(python_dir()))
    except OSError:
        return removed
    for entry in entries:
        if not is_link(entry.path):
            continue
        try:
            if os.lstat(entry.path).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
                os.rmdir(entry.path)            # removes the junction itself, never its target
            else:
                os.unlink(entry.path)
        except OSError as exc:
            log(f"could not remove the link {entry.path}: {exc}")
            continue
        removed.append(entry.name)
        log(f"removed the link {entry.path} (RedirectionGuard: links in the engine folder are not used)")
    return removed


def venv_home_ok() -> bool:
    """False when the venv was created for a Python in another place (e.g. after a move)."""
    cfg = venv_dir() / "pyvenv.cfg"
    try:
        lines = cfg.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip().lower() == "home":
            try:
                return Path(value.strip()).resolve().is_relative_to(python_dir().resolve())
            except OSError:
                return False
    return False


def torch_flavor(tier: Tier) -> str:
    return tier.torch_index.rstrip("/").rsplit("/", 1)[-1]


def requirements_sha256(resource: Callable[[str], Path] | None = None) -> str:
    resource = resource or paths.resource_path
    return hashlib.sha256(resource(REQUIREMENTS_REL).read_bytes()).hexdigest()


def disk_free(path: Path) -> int:
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def rmtree(path: Path) -> None:
    """Deletes a folder tree, including files marked read-only."""
    def clear_readonly(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=clear_readonly)


def copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".owltmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("UV_") and k.upper() not in
           ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX", "PYTHONSTARTUP")}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONNOUSERSITE="1", NO_COLOR="1")
    return env


def uv_env() -> dict[str, str]:
    env = clean_env()
    env.update(
        UV_CACHE_DIR=str(uv_cache_dir()),
        UV_PYTHON_INSTALL_DIR=str(python_dir()),
        UV_PYTHON_PREFERENCE="only-managed",
        UV_NO_CONFIG="1",
    )
    return env


def probe_tool(ctx: StageContext, args: list) -> tuple[int, list[str]]:
    """Runs a quick check command. Never raises for a non-zero exit code."""
    lines: list[str] = []

    def on_line(line: str) -> None:
        lines.append(line)
        ctx.log(line)

    ctx.log("$ " + " ".join(str(a) for a in args))
    try:
        code = ctx.deps.run_cmd([str(a) for a in args], clean_env(), on_line, None)
    except OSError as exc:
        ctx.log(f"cannot start: {exc}")
        return -1, lines
    return code, lines


def run_tool(ctx: StageContext, args: list, env: dict[str, str] | None = None,
             lines: list[str] | None = None) -> list[str]:
    """Runs an installation command. Raises BootstrapError when it fails or is cancelled.
    `lines`, when given, collects the output (also when the command fails)."""
    lines = [] if lines is None else lines

    def on_line(line: str) -> None:
        lines.append(line)
        ctx.log(line)
        if line.strip():
            ctx.report(message=line.strip()[:200])

    ctx.log("$ " + " ".join(str(a) for a in args))
    try:
        code = ctx.deps.run_cmd([str(a) for a in args], env or uv_env(), on_line, ctx.cancel)
    except OSError as exc:
        raise BootstrapError(f"command_failed: cannot start {args[0]}: {exc}") from exc
    if code == uvtool.CANCELLED or ctx.cancelled():
        raise BootstrapError("cancelled")
    if code != 0:
        last = next((line for line in reversed(lines) if line.strip()), "")
        raise BootstrapError(f"command_failed: {Path(str(args[0])).name} {' '.join(str(a) for a in args[1:3])} "
                             f"exited with {code}: {last}")
    return lines


def python_is_311(ctx: StageContext, exe: Path) -> bool:
    code, lines = probe_tool(ctx, [exe, "--version"])
    return code == 0 and any(line.strip().startswith(f"Python {PYTHON_VERSION}.") for line in lines)


def default_engine(tier: Tier):
    from owlocr.engine.client import SubprocessEngine
    return SubprocessEngine(python=paths.engine_python(), worker_script=paths.worker_dir() / "owl_worker.py",
                            model_dir=paths.model_dir(), device=tier.device, dtype=tier.dtype,
                            log_file=paths.logs_dir() / "engine.log")
