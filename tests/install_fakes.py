"""Fakes for testing the engine installer without uv, Python downloads, torch or the model."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import uvtool
from owlocr.engine.install_kit import Deps

LETTER = ("Vážená paní doktorko Šťastná, dovoluji si Vás požádat o vystavení lékařské zprávy "
          "pro pana Řehoře Dvořáka. Doporučujeme pokračovat v rehabilitaci.")


def make_uv_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("uv.exe", b"fake uv binary")
        zf.writestr("uvx.exe", b"fake uvx binary")
    return buf.getvalue()


UV_ZIP = make_uv_zip()
UV_PINS = {"uv": {"version": "0.0.0-test", "url": "https://example.invalid/uv-x86_64-pc-windows-msvc.zip",
                  "sha256": hashlib.sha256(UV_ZIP).hexdigest()}}


def make_junction(link: Path, target: Path) -> None:
    """Creates a real directory junction, the way uv links the minor-version folder."""
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True,
                   capture_output=True)


PYTHON_448_LINES = (
    "Downloading cpython-3.11.9-windows-x86_64-none (download) (24.1MiB)",
    " Downloaded cpython-3.11.9-windows-x86_64-none (download)",
    "error: Failed to create Python minor version link directory",
    "  cause: The path cannot be traversed because it contains an untrusted mount point. (os error 448)",
)


def make_resources(root: Path) -> Path:
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "owl_worker.py").write_text("# fake worker\n", encoding="utf-8")
    (root / "worker" / "device_patch.py").write_text("# fake patcher\n", encoding="utf-8")
    (root / "worker" / "requirements-engine.txt").write_text("transformers==4.57.1\n", encoding="utf-8")
    (root / "licenses").mkdir()
    (root / "licenses" / "Apache-2.0.txt").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (root / "owlocr" / "web" / "static").mkdir(parents=True)
    (root / "owlocr" / "web" / "static" / "selftest.png").write_bytes(b"\x89PNG fake")
    return root


class FakeEngine:
    def __init__(self, tools: "FakeTools", tier) -> None:
        self.tools, self.tier = tools, tier
        tools.engines.append(self)
        self.stopped = False

    def start(self):
        return SimpleNamespace(pid=1, torch="2.10.0", transformers="4.57.1", cuda_available=False, gpu_name=None)

    def load(self) -> float:
        return 0.1

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0, on_progress=None, cancel=None):
        self.tools.ocr_calls.append((Path(image).name, mode, max_new_tokens, time_limit_s))
        if on_progress:
            on_progress(10)
        return SimpleNamespace(text=self.tools.ocr_text, seconds=12.34, prefix_tokens=277, output_tokens=300,
                               hit_token_cap=False, cancelled=False, timed_out=False, peak_vram_mib=0)

    def stop(self, timeout_s: float = 5.0) -> None:
        self.stopped = True


class FakeTools:
    """Plays uv, the managed Python, the venv Python, device_patch.py, the store and the engine."""

    def __init__(self, resources: Path) -> None:
        self.resources = resources
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []
        self.torch: str | None = None
        self.deps = False
        self.model = False
        self.block_torch = False
        self.fail_when = None            # callable(args) -> bool
        self.patch_code = 0              # exit code of the fake device_patch.py
        self.free_vram: int | None = 16000
        self.free_bytes = 100 * 1024**3
        self.ocr_text = LETTER
        self.engines: list[FakeEngine] = []
        self.ocr_calls: list[tuple] = []
        self.downloads: list[str] = []
        # "448": `uv python install` unpacks Python, creates the minor-version junction and then
        # fails on it as under WebView2's RedirectionGuard; "448-empty": the same error without
        # a usable Python; "link": uv succeeds and leaves the junction, as without the guard.
        self.python_install_fault: str | None = None

    # --- Deps ----------------------------------------------------------------
    def deps_for_test(self) -> Deps:
        return Deps(pins=json.loads(json.dumps(UV_PINS)), resource=lambda rel: self.resources / rel,
                    run_cmd=self.run_cmd, download_file=self.download_file,
                    engine_factory=lambda tier: FakeEngine(self, tier),
                    store_is_ready=lambda: self.model, store_download=self.store_download,
                    free_vram=lambda: self.free_vram, free_bytes=lambda path: self.free_bytes)

    def download_file(self, url, dest, on_progress=None, cancel=None):
        self.downloads.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(UV_ZIP)
        if on_progress:
            on_progress(len(UV_ZIP), len(UV_ZIP))

    def store_download(self, on_progress, cancel):
        target = paths.model_dir()
        target.mkdir(parents=True, exist_ok=True)
        (target / "modeling_unlimitedocr.py").write_text("x = 1\n", encoding="utf-8")
        (target / "manifest.json").write_text("{}", encoding="utf-8")
        on_progress(6_672_547_120, 6_672_547_120)
        self.model = True

    # --- commands -------------------------------------------------------------
    def run_cmd(self, args, env, on_line, cancel):
        self.calls.append(list(args))
        self.envs.append(dict(env))
        if self.fail_when and self.fail_when(args):
            on_line("error: simulated failure")
            return 1
        name = Path(args[0]).name.lower()
        if name == "uv.exe":
            return self._uv(args[1:], env, on_line, cancel)
        if name == "python.exe":
            return self._python(args, on_line)
        raise AssertionError(f"unexpected command {args}")

    def _uv(self, a, env, on_line, cancel):
        assert env["UV_PYTHON_INSTALL_DIR"] == str(kit.python_dir())
        assert env["UV_CACHE_DIR"] == str(kit.uv_cache_dir())
        if a[:2] == ["python", "install"]:
            folder = kit.python_dir() / "cpython-3.11.9-windows-x86_64-none"
            folder.mkdir(parents=True, exist_ok=True)
            if self.python_install_fault != "448-empty":
                (folder / "python.exe").write_bytes(b"")
            if self.python_install_fault:
                make_junction(kit.python_dir() / "cpython-3.11-windows-x86_64-none", folder)
            if self.python_install_fault in ("448", "448-empty"):
                for line in PYTHON_448_LINES:
                    on_line(line)
                return 2
            on_line("Installed Python 3.11.9 in 1.2s")
            return 0
        if a[0] == "venv":
            base, venv = Path(a[a.index("--python") + 1]), Path(a[-1])
            (venv / "Scripts").mkdir(parents=True, exist_ok=True)
            (venv / "Scripts" / "python.exe").write_bytes(b"")
            (venv / "pyvenv.cfg").write_text(f"home = {base.parent}\nversion_info = 3.11.9\n", encoding="utf-8")
            self.torch, self.deps = None, False          # a new venv is empty
            return 0
        if a[:2] == ["pip", "install"] and "--index-url" in a:
            if self.block_torch:
                while cancel is not None and not cancel.is_set():
                    time.sleep(0.01)
                return uvtool.CANCELLED
            self.torch = a[a.index("--index-url") + 1].rstrip("/").rsplit("/", 1)[-1]
            on_line("Downloading torch (2.7GiB)")
            on_line("Installed 14 packages in 20.1s")
            return 0
        if a[:2] == ["pip", "install"] and "-r" in a:
            self.deps = True
            on_line("Installed 30 packages in 5.0s")
            return 0
        raise AssertionError(f"unexpected uv call {a}")

    def _python(self, args, on_line):
        if args[1:] == ["--version"]:
            on_line("Python 3.11.9")
            return 0
        if args[1] == "-c" and "import torch" in args[2]:
            if not self.torch:
                on_line("ModuleNotFoundError: No module named 'torch'")
                return 1
            on_line(f"OWL 2.10.0+{self.torch} 0.25.0+{self.torch}")
            return 0
        if args[1] == "-c" and "import transformers" in args[2]:
            if not self.deps:
                on_line("ModuleNotFoundError: No module named 'transformers'")
                return 1
            on_line("OWL 4.57.1")
            return 0
        if args[1].endswith("device_patch.py"):
            if self.patch_code:
                on_line("REFUSED: modeling_unlimitedocr.py is not the expected upstream code")
                return self.patch_code
            target = Path(args[args.index("--model-dir") + 1]) / "modeling_unlimitedocr.py"
            if "--restore" in args:
                target.write_text("x = 1\n", encoding="utf-8")
                on_line("restored")
            else:
                target.write_text(kit.PATCH_SENTINEL + "\nx = 1\n", encoding="utf-8")
                on_line("patched")
            return 0
        raise AssertionError(f"unexpected python call {args}")

    def uv_calls(self) -> list[list[str]]:
        return [c[1:] for c in self.calls if Path(c[0]).name.lower() == "uv.exe"]


def collect_events():
    events = []
    lock = threading.Lock()

    def on_event(ev):
        with lock:
            events.append(ev)

    return events, on_event
