"""Owl OCR device patch: lets the Unlimited-OCR model code run on devices other than CUDA.

The upstream model code (revision 07dea832e22aefee32ad281d4b80551282e1c168) is hard-wired to
CUDA: 17 `.cuda()` calls (one of them in `forward()`, the rest in `infer()` and `infer_multi()`),
3 `torch.autocast("cuda", dtype=torch.bfloat16)` blocks and forced `.to(torch.bfloat16)` casts.
This script rewrites `modeling_unlimitedocr.py` so that device and dtype come from the patch
arguments (or the OWLOCR_DEVICE / OWLOCR_DTYPE environment variables at run time), and checks
that `modeling_deepseekv2.py` and `deepencoder.py` contain no CUDA-only code.

Standard library only: it runs with the engine's Python, before or without torch.

    python device_patch.py --model-dir <dir> [--device cpu] [--dtype float32]
    python device_patch.py --model-dir <dir> --restore
    python device_patch.py --model-dir <dir> --check

Exit codes: 0 done (or nothing to do), 1 error, 2 refused because the upstream code is not the
code this patch was written for, 3 (--check only) not patched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SENTINEL = "# --- owl-ocr device patch v1 applied ---"
TARGET = "modeling_unlimitedocr.py"
CHECKED = ("modeling_deepseekv2.py", "deepencoder.py")
MANIFEST = "manifest.json"

MASKED_SCATTER_OLD = "images_seq_mask[idx].unsqueeze(-1).cuda()"
MASKED_SCATTER_NEW = "images_seq_mask[idx].unsqueeze(-1).to(inputs_embeds.device)"
CUDA_CALL_OLD = ".cuda()"
CUDA_CALL_NEW = ".to(_OWL_DEVICE)"
AUTOCAST_OLD = 'torch.autocast("cuda", dtype=torch.bfloat16)'
AUTOCAST_NEW = "torch.autocast(_OWL_DEVICE_TYPE, dtype=_OWL_DTYPE, enabled=_OWL_AUTOCAST)"
BF16_CAST_OLD = ".to(torch.bfloat16)"
BF16_CAST_NEW = ".to(_OWL_DTYPE)"

# Exact number of occurrences in the pristine upstream file. Anything else means upstream changed.
EXPECTED_COUNTS = {
    MASKED_SCATTER_OLD: 1,
    CUDA_CALL_OLD: 17,
    AUTOCAST_OLD: 3,
    BF16_CAST_OLD: 5,      # 4 in code, 1 in a comment
}
# Must not occur in the files that are checked but not modified.
FORBIDDEN_IN_CHECKED = (".cuda()", '"cuda"', "'cuda'", ".to(torch.bfloat16)")

DEVICES = ("cpu", "cuda")
DTYPES = ("float32", "bfloat16", "float16")


class PatchRefused(Exception):
    """The model code is not what this patch expects. Nothing was changed."""


def header(device: str, dtype: str) -> str:
    return (
        "# NOTICE: this file was modified by Owl OCR (worker/device_patch.py); see NOTICE-OwlOCR.txt.\n"
        "# Changes: every call of the tensor method cuda() became .to(<device>); the three CUDA-only\n"
        "# bfloat16 autocast blocks became autocast blocks whose device and dtype are configurable\n"
        "# and which are off on the processor; forced bfloat16 casts became .to(<dtype>).\n"
        f"# The unmodified original is kept next to this file as {TARGET}.orig.\n"
        f"{SENTINEL}\n"
        "import os as _owl_os\n"
        "import torch as _owl_torch\n"
        f"_OWL_DEVICE = _owl_os.environ.get(\"OWLOCR_DEVICE\", \"{device}\")\n"
        f"_OWL_DTYPE = getattr(_owl_torch, _owl_os.environ.get(\"OWLOCR_DTYPE\", \"{dtype}\"))\n"
        "_OWL_DEVICE_TYPE = _owl_torch.device(_OWL_DEVICE).type\n"
        "_OWL_AUTOCAST = _OWL_DEVICE_TYPE == \"cuda\"\n"
        "# --- end of owl-ocr device patch header ---\n"
    )


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_atomic(path: Path, text: str) -> None:
    """Temporary file + os.replace: never half-written, and a hard link is never written through."""
    tmp = path.with_name(path.name + ".owltmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_patched(model_dir: Path) -> bool:
    target = model_dir / TARGET
    return target.is_file() and SENTINEL in _read(target)


def check_pristine(model_dir: Path) -> str:
    """Returns the pristine target text, or raises PatchRefused."""
    for name in (TARGET,) + CHECKED:
        if not (model_dir / name).is_file():
            raise PatchRefused(f"{name} not found in {model_dir}")
    text = _read(model_dir / TARGET)
    wrong = {pattern: text.count(pattern) for pattern, expected in EXPECTED_COUNTS.items()
             if text.count(pattern) != expected}
    if wrong:
        details = ", ".join(f"{p!r}: found {n}, expected {EXPECTED_COUNTS[p]}" for p, n in wrong.items())
        raise PatchRefused(f"{TARGET} is not the expected upstream code ({details})")
    for name in CHECKED:
        other = _read(model_dir / name)
        found = [p for p in FORBIDDEN_IN_CHECKED if p in other]
        if found:
            raise PatchRefused(f"{name} now contains CUDA-only code: {found}")
    return text


def patched_text(pristine: str, device: str, dtype: str) -> str:
    text = pristine.replace(MASKED_SCATTER_OLD, MASKED_SCATTER_NEW)
    text = text.replace(CUDA_CALL_OLD, CUDA_CALL_NEW)
    text = text.replace(AUTOCAST_OLD, AUTOCAST_NEW)
    text = text.replace(BF16_CAST_OLD, BF16_CAST_NEW)
    return header(device, dtype) + text


def _update_manifest_after_patch(model_dir: Path, new_bytes: bytes) -> None:
    path = model_dir / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = manifest["files"]
    if TARGET + ".orig" not in files:
        files[TARGET + ".orig"] = files[TARGET]          # pristine hashes now describe the backup
    files[TARGET] = {"size": len(new_bytes), "sha256": _sha256(new_bytes), "git_sha1": None,
                     "patched_by": SENTINEL.strip("# -")}
    _write_atomic(path, json.dumps(manifest, indent=1, ensure_ascii=False))


def _update_manifest_after_restore(model_dir: Path) -> None:
    path = model_dir / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = manifest["files"]
    if TARGET + ".orig" in files:
        files[TARGET] = files.pop(TARGET + ".orig")
    _write_atomic(path, json.dumps(manifest, indent=1, ensure_ascii=False))


def apply(model_dir: Path, device: str, dtype: str) -> str:
    """Patches the model folder. Returns 'patched' or 'already patched'."""
    if device not in DEVICES or dtype not in DTYPES:
        raise ValueError(f"unsupported device/dtype {device}/{dtype}")
    if not (model_dir / MANIFEST).is_file():
        raise FileNotFoundError(f"{MANIFEST} not found in {model_dir}")
    if is_patched(model_dir):
        return "already patched"
    pristine = check_pristine(model_dir)
    new = patched_text(pristine, device, dtype)
    if CUDA_CALL_OLD in new:
        raise PatchRefused("a .cuda() call survived the patch")
    try:
        compile(new, TARGET, "exec")
    except SyntaxError as exc:
        raise PatchRefused(f"patched code does not compile: {exc}") from exc
    _write_atomic(model_dir / (TARGET + ".orig"), pristine)
    _write_atomic(model_dir / TARGET, new)
    _update_manifest_after_patch(model_dir, new.encode("utf-8"))
    return "patched"


def restore(model_dir: Path) -> str:
    """Puts the unmodified upstream file back. Returns 'restored' or 'not patched'."""
    if not is_patched(model_dir):
        return "not patched"
    backup = model_dir / (TARGET + ".orig")
    if not backup.is_file():
        raise FileNotFoundError(f"{backup.name} is missing; verify or reinstall the model")
    os.replace(backup, model_dir / TARGET)
    _update_manifest_after_restore(model_dir)
    return "restored"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--device", default=os.environ.get("OWLOCR_DEVICE", "cpu"), choices=DEVICES)
    parser.add_argument("--dtype", default=os.environ.get("OWLOCR_DTYPE", "float32"), choices=DTYPES)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--restore", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            patched = is_patched(args.model_dir)
            print("patched" if patched else "not patched")
            return 0 if patched else 3
        result = restore(args.model_dir) if args.restore else apply(args.model_dir, args.device, args.dtype)
    except PatchRefused as exc:
        print(f"REFUSED: {exc}. The model code differs from the pinned revision; nothing was changed.")
        return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
