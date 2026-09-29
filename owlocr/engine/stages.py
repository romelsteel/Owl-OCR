"""The ten stages of the engine installation (design 6.2): one check and one action each.

`bootstrap.py` runs them in order. A stage whose check passes is skipped, so an interrupted
installation continues where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import registry, store, uvtool
from owlocr.engine.install_kit import (
    APACHE_NAME, APACHE_REL, BootstrapError, INSTALL_FORMAT, MODEL_NOTICE, NOTICE_NAME,
    PATCH_SENTINEL, PATCH_TARGET, PYTHON_VERSION, REQUIREMENTS_REL, SELFTEST_IMAGE_REL,
    SELFTEST_MAX_NEW_TOKENS, SELFTEST_MIN_WORDS, SELFTEST_TIME_LIMIT_S, SELFTEST_WORDS,
    StageContext, TORCH_DOWNLOAD_BYTES, WORKER_FILES, clean_env, copy_atomic, dir_size,
    install_file, managed_python, probe_tool, python_is_311, read_json, read_stamp,
    remove_python_links, requirements_sha256, rmtree, run_tool, torch_flavor, uv_cache_dir, uv_exe, venv_dir,
    venv_home_ok, write_stamp,
)
from owlocr.hardware import REQUIRED_FREE_VRAM_MIB

# Filled below, stage by stage: name -> check, name -> action.
CHECKS: dict[str, Callable[[StageContext], bool]] = {}
ACTIONS: dict[str, Callable[[StageContext], None]] = {}


# ---------------------------------------------------------------- stage: tools

def check_tools(ctx: StageContext) -> bool:
    pin = ctx.deps.pins["uv"]
    return uv_exe().is_file() and read_stamp("tools") == {"version": pin["version"], "sha256": pin["sha256"]}


def do_tools(ctx: StageContext) -> None:
    pin = ctx.deps.pins["uv"]
    archive = uv_exe().parent / "uv.zip"
    try:
        ctx.deps.download_file(pin["url"], archive, lambda d, t: ctx.report(done=d, total=t), ctx.cancel)
    except uvtool.Cancelled as exc:
        raise BootstrapError("cancelled") from exc
    except OSError as exc:
        raise BootstrapError(f"download_failed: {pin['url']}: {exc}") from exc
    digest = uvtool.sha256_file(archive)
    if digest != pin["sha256"]:
        archive.unlink(missing_ok=True)
        raise BootstrapError(f"checksum_mismatch: uv archive has sha256 {digest}, expected {pin['sha256']}")
    with zipfile.ZipFile(archive) as zf:
        member = next((n for n in zf.namelist() if n.replace("\\", "/").rsplit("/", 1)[-1].lower() == "uv.exe"), None)
        if member is None:
            raise BootstrapError("download_failed: uv.exe is not in the uv archive")
        tmp = uv_exe().with_name("uv.exe.owltmp")
        with zf.open(member) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.replace(tmp, uv_exe())
    archive.unlink(missing_ok=True)
    write_stamp("tools", {"version": pin["version"], "sha256": pin["sha256"]})


# ---------------------------------------------------------------- stage: python

# WebView2 turns on RedirectionGuard (ProcessRedirectionTrustPolicy) in OwlOCR.exe and every child
# process inherits it: traversing a user-created junction fails with os error 448. uv links
# `cpython-3.11-windows-x86_64-none` to the full-version folder and then fails on its own link,
# after Python itself is complete. The installer removes such links (without following them) and
# always names the full-version python.exe.
REDIRECTION_GUARD_MARKS = ("os error 448", "minor version link")


def check_python(ctx: StageContext) -> bool:
    remove_python_links(ctx.log)             # heals an engine folder left by an earlier attempt
    exe = managed_python()
    return exe is not None and python_is_311(ctx, exe)


def do_python(ctx: StageContext) -> None:
    lines: list[str] = []
    try:
        run_tool(ctx, [uv_exe(), "python", "install", PYTHON_VERSION, "--no-bin", "--no-registry"],
                 lines=lines)
    except BootstrapError as exc:
        output = "\n".join(lines).lower()
        if not (str(exc).startswith("command_failed:") and any(m in output for m in REDIRECTION_GUARD_MARKS)):
            raise
        exe = managed_python()
        if exe is None or not python_is_311(ctx, exe):
            raise
        remove_python_links(ctx.log)
        ctx.log(f"uv could not use its minor-version link (Windows RedirectionGuard, inherited from "
                f"WebView2); {exe} is complete and is used directly")
        return
    remove_python_links(ctx.log)


# ---------------------------------------------------------------- stage: venv

def check_venv(ctx: StageContext) -> bool:
    remove_python_links(ctx.log)
    exe = paths.engine_python()
    return exe.is_file() and venv_home_ok() and python_is_311(ctx, exe)


def do_venv(ctx: StageContext) -> None:
    remove_python_links(ctx.log)
    base = managed_python()
    if base is None:
        raise BootstrapError("check_failed: the managed Python 3.11 is missing")
    rmtree(venv_dir())
    run_tool(ctx, [uv_exe(), "venv", "--python", base, "--no-project", venv_dir()])


CHECKS.update(tools=check_tools, python=check_python, venv=check_venv)
ACTIONS.update(tools=do_tools, python=do_python, venv=do_venv)


# ---------------------------------------------------------------- stage: torch

def installed_torch(ctx: StageContext) -> tuple[str, str] | None:
    code, lines = probe_tool(ctx, [paths.engine_python(), "-c",
                                   "import torch, torchvision; print('OWL', torch.__version__, torchvision.__version__)"])
    for line in lines:
        parts = line.split()
        if code == 0 and len(parts) == 3 and parts[0] == "OWL":
            return parts[1], parts[2]
    return None


def _torch_ok(ctx: StageContext) -> bool:
    spec, flavor = registry.UNLIMITED_OCR, torch_flavor(ctx.tier)
    return installed_torch(ctx) == (f"{spec.torch}+{flavor}", f"{spec.torchvision}+{flavor}")


def check_torch(ctx: StageContext) -> bool:
    return paths.engine_python().is_file() and _torch_ok(ctx)


class _CacheGrowth:
    """Reports the download progress of torch by watching the uv cache grow (uv prints no byte
    counts when it is not attached to a console)."""

    def __init__(self, ctx: StageContext, total: int) -> None:
        self.ctx, self.total = ctx, total
        self.base = dir_size(uv_cache_dir()) if uv_cache_dir().exists() else 0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self.stop_event.wait(2.0):
            grown = max(0, dir_size(uv_cache_dir()) - self.base)
            self.ctx.report(done=min(grown, self.total), total=self.total)

    def __enter__(self):
        if self.total:
            self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)


def do_torch(ctx: StageContext) -> None:
    spec = registry.UNLIMITED_OCR
    remove_python_links(ctx.log)
    with _CacheGrowth(ctx, TORCH_DOWNLOAD_BYTES.get(torch_flavor(ctx.tier), 0)):
        run_tool(ctx, [uv_exe(), "pip", "install", "--python", paths.engine_python(),
                       f"torch=={spec.torch}", f"torchvision=={spec.torchvision}",
                       "--index-url", ctx.tier.torch_index])


# ---------------------------------------------------------------- stage: deps

DEPS_IMPORT_TEST = ("import transformers, tokenizers, huggingface_hub, safetensors, accelerate, einops, "
                    "easydict, addict, matplotlib, PIL, psutil, numpy, requests, tqdm; "
                    "print('OWL', transformers.__version__)")


def check_deps(ctx: StageContext) -> bool:
    stamp = read_stamp("deps")
    if not stamp or stamp.get("requirements_sha256") != requirements_sha256(ctx.deps.resource):
        return False
    code, lines = probe_tool(ctx, [paths.engine_python(), "-c", DEPS_IMPORT_TEST])
    if code != 0 or f"OWL {registry.UNLIMITED_OCR.transformers}" not in [line.strip() for line in lines]:
        return False
    return _torch_ok(ctx)          # the dependencies must not have replaced torch


def do_deps(ctx: StageContext) -> None:
    remove_python_links(ctx.log)
    # `-r` is the short form of `--requirement`, which pin_uv.REQUIRED_FLAGS verifies.
    run_tool(ctx, [uv_exe(), "pip", "install", "--python", paths.engine_python(),
                   "-r", ctx.deps.resource(REQUIREMENTS_REL)])
    write_stamp("deps", {"requirements_sha256": requirements_sha256(ctx.deps.resource)})


CHECKS.update(torch=check_torch, deps=check_deps)
ACTIONS.update(torch=do_torch, deps=do_deps)


# ---------------------------------------------------------------- stage: model

def check_model(ctx: StageContext) -> bool:
    # store.is_ready() reads the folder's own manifest, so the manifest a CPU patch leaves behind
    # (extra `.orig` entry, patched entry with git_sha1 None) counts as ready.
    return bool(ctx.deps.store_is_ready())


def do_model(ctx: StageContext) -> None:
    try:
        ctx.deps.store_download(lambda d, t: ctx.report(done=d, total=t), ctx.cancel)
    except store.StoreError as exc:
        if str(exc) == "cancelled" or ctx.cancelled():
            raise BootstrapError("cancelled") from exc
        raise BootstrapError(f"model_download_failed: {exc}") from exc
    except OSError as exc:
        raise BootstrapError(f"model_download_failed: {exc}") from exc
    if ctx.cancelled():
        raise BootstrapError("cancelled")


# ---------------------------------------------------------------- stage: worker

def _worker_pairs(resource: Callable[[str], Path]) -> list[tuple[Path, Path]]:
    pairs = [(resource(f"worker/{n}"), paths.worker_dir() / n) for n in WORKER_FILES]
    pairs.append((resource(APACHE_REL), paths.model_dir() / APACHE_NAME))
    return pairs


def check_worker(ctx: StageContext) -> bool:
    for src, dst in _worker_pairs(ctx.deps.resource):
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            return False
    notice = paths.model_dir() / NOTICE_NAME
    return notice.is_file() and notice.read_text(encoding="utf-8") == MODEL_NOTICE


def do_worker(ctx: StageContext) -> None:
    for src, dst in _worker_pairs(ctx.deps.resource):
        copy_atomic(src, dst)                       # byte for byte: the worker is never modified
    paths.atomic_write_text(paths.model_dir() / NOTICE_NAME, MODEL_NOTICE)


# ---------------------------------------------------------------- stage: patch

def model_is_patched() -> bool:
    target = paths.model_dir() / PATCH_TARGET
    try:
        return PATCH_SENTINEL in target.read_text(encoding="utf-8")
    except OSError:
        return False


def check_patch(ctx: StageContext) -> bool:
    return model_is_patched() == (ctx.tier.device == "cpu")


def do_patch(ctx: StageContext) -> None:
    cpu = ctx.tier.device == "cpu"
    if not cpu and not model_is_patched():
        return                                       # pristine model on a GPU tier: nothing to restore
    args = [paths.engine_python(), paths.worker_dir() / "device_patch.py", "--model-dir", paths.model_dir()]
    args += ["--device", ctx.tier.device, "--dtype", ctx.tier.dtype] if cpu else ["--restore"]
    lines: list[str] = []
    ctx.log("$ " + " ".join(str(a) for a in args))
    try:
        code = ctx.deps.run_cmd([str(a) for a in args], clean_env(),
                                lambda s: (lines.append(s), ctx.log(s)), ctx.cancel)
    except OSError as exc:
        raise BootstrapError(f"command_failed: cannot start device_patch.py: {exc}") from exc
    if code == uvtool.CANCELLED or ctx.cancelled():
        raise BootstrapError("cancelled")
    last = next((line for line in reversed(lines) if line.strip()), "")
    if code == 2:
        raise BootstrapError(f"patch_refused: {last}")
    if code != 0:
        raise BootstrapError(f"command_failed: device_patch.py exited with {code}: {last}")


CHECKS.update(model=check_model, worker=check_worker, patch=check_patch)
ACTIONS.update(model=do_model, worker=do_worker, patch=do_patch)


# ---------------------------------------------------------------- stage: selftest

def fingerprint(ctx: StageContext) -> str:
    spec = registry.UNLIMITED_OCR
    data = {"tier": ctx.tier.name, "device": ctx.tier.device, "dtype": ctx.tier.dtype,
            "torch_index": ctx.tier.torch_index, "python": PYTHON_VERSION, "revision": spec.revision,
            "torch": spec.torch, "torchvision": spec.torchvision, "transformers": spec.transformers,
            "requirements_sha256": requirements_sha256(ctx.deps.resource)}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def selftest_words_found(text: str) -> list[str]:
    haystack = unicodedata.normalize("NFC", text).casefold()
    return [w for w in SELFTEST_WORDS if unicodedata.normalize("NFC", w).casefold() in haystack]


def check_selftest(ctx: StageContext) -> bool:
    stamp = read_stamp("selftest")
    return bool(stamp) and stamp.get("ok") is True and stamp.get("fingerprint") == fingerprint(ctx)


def do_selftest(ctx: StageContext) -> None:
    from owlocr.engine.protocol import EngineError

    mode = ctx.tier.default_mode
    if ctx.tier.device == "cuda":
        free, need = ctx.deps.free_vram(), REQUIRED_FREE_VRAM_MIB[mode]
        if free is not None and free < need:
            raise BootstrapError(f"not_enough_vram: {need} MiB of free graphics memory needed, {free} MiB free")
    image = ctx.deps.resource(SELFTEST_IMAGE_REL)
    engine = ctx.deps.engine_factory(ctx.tier)
    try:
        ctx.report(message="starting")
        engine.start()
        ctx.report(message="loading")
        engine.load()
        ctx.report(done=0, total=SELFTEST_MAX_NEW_TOKENS, message="reading")
        result = engine.ocr_page(image, mode, max_new_tokens=SELFTEST_MAX_NEW_TOKENS,
                                 time_limit_s=SELFTEST_TIME_LIMIT_S[ctx.tier.device],
                                 on_progress=lambda n: ctx.report(done=n), cancel=ctx.cancel)
    except EngineError as exc:
        if ctx.cancelled():
            raise BootstrapError("cancelled") from exc
        raise BootstrapError(f"selftest_failed: {exc}") from exc
    finally:
        engine.stop()
    if result.cancelled or ctx.cancelled():
        raise BootstrapError("cancelled")
    if result.timed_out:
        raise BootstrapError(f"selftest_failed: timed_out after {SELFTEST_TIME_LIMIT_S[ctx.tier.device]:.0f} s")
    found = selftest_words_found(result.text)
    if len(found) < SELFTEST_MIN_WORDS:
        raise BootstrapError(f"selftest_failed: expected words not found (found {found}); "
                             f"output began {result.text[:80]!r}")
    write_stamp("selftest", {"fingerprint": fingerprint(ctx), "ok": True, "mode": mode,
                             "seconds": round(result.seconds, 1), "words_found": len(found)})
    ctx.report(done=SELFTEST_MAX_NEW_TOKENS, message=f"{result.seconds:.1f} s")


# ---------------------------------------------------------------- stage: mark

def check_mark(ctx: StageContext) -> bool:
    record = read_json(install_file())
    return bool(record) and record.get("fingerprint") == fingerprint(ctx)


def do_mark(ctx: StageContext) -> None:
    from owlocr import __version__, settings

    spec = registry.UNLIMITED_OCR
    first_install = not install_file().exists()
    selftest = read_stamp("selftest") or {}
    # No `python` key on purpose: plan A's default_engine() would read it as the interpreter path.
    record = {
        "format": INSTALL_FORMAT, "fingerprint": fingerprint(ctx),
        "tier": ctx.tier.name, "device": ctx.tier.device, "dtype": ctx.tier.dtype,
        "default_mode": ctx.tier.default_mode, "torch_index": ctx.tier.torch_index,
        "python_version": PYTHON_VERSION, "uv": ctx.deps.pins["uv"]["version"],
        "engine_id": spec.engine_id, "revision": spec.revision, "torch": spec.torch,
        "torchvision": spec.torchvision, "transformers": spec.transformers,
        "requirements_sha256": requirements_sha256(ctx.deps.resource),
        "patched": model_is_patched(), "selftest_seconds": selftest.get("seconds"),
        "app_version": __version__, "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    paths.atomic_write_text(install_file(), json.dumps(record, indent=1, ensure_ascii=False))
    try:
        import contextlib
        import sys
        # The web server's settings lock, found without importing Flask into the engine layer.
        server = sys.modules.get("owlocr.web.server")
        lock = getattr(server, "SETTINGS_LOCK", None) or contextlib.nullcontext()
        with lock:
            # Design 10.3: the default mode follows the tier, unless the user already changed it.
            if first_install and settings.get("mode_default") == settings.DEFAULTS["mode_default"]:
                settings.update({"mode_default": ctx.tier.default_mode})
    except Exception as exc:            # a settings problem must not undo a finished installation
        ctx.log(f"could not set mode_default: {exc}")


CHECKS.update(selftest=check_selftest, mark=check_mark)
ACTIONS.update(selftest=do_selftest, mark=do_mark)
