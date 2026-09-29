"""Prepares the separate engine root for the CPU acceptance test (plan D, task 30).

    py -3.11 tests\\acceptance\\prepare_cpu_root.py

Creates engine\\cpu-acceptance\\ inside the repository (ignored by git) with its own data and
config folders, links the already downloaded model into it (the 6.7 GB weights file as a hard
link, the small files as copies, so patching them never touches the GPU engine), and runs the
real installer with the CPU tier: uv, Python 3.11, torch from the cpu index, the dependencies,
the device patch and the self-test. The GPU engine in engine\\ is not modified.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "engine" / "cpu-acceptance"
GPU_MODEL = REPO / "engine" / "models" / "unlimited_ocr"

os.environ["OWLOCR_HOME"] = str(ROOT / "data")
os.environ["OWLOCR_CONFIG"] = str(ROOT / "config")
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
sys.path.insert(0, str(REPO))

from owlocr import paths  # noqa: E402
from owlocr.engine import bootstrap  # noqa: E402
from owlocr.hardware import tier_by_name  # noqa: E402


def link_model() -> None:
    target = paths.model_dir()
    if (target / "manifest.json").is_file():
        return
    if not (GPU_MODEL / "manifest.json").is_file():
        raise SystemExit(f"the verified model is not in {GPU_MODEL}")
    target.mkdir(parents=True, exist_ok=True)
    for src in GPU_MODEL.iterdir():
        if not src.is_file() or src.name == "manifest.json":
            continue
        dst = target / src.name
        if src.suffix == ".safetensors":
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)
    shutil.copy2(GPU_MODEL / "manifest.json", target / "manifest.json")     # the ready marker comes last


def main() -> int:
    link_model()

    def show(event) -> None:
        if event.state != "progress":
            print(f"{event.stage:9} {event.state:8} {event.message}", flush=True)

    bootstrap.run(tier_by_name("cpu", "acceptance_test"), show)
    print("CPU engine ready:", bootstrap.read_install())
    return 0


if __name__ == "__main__":
    sys.exit(main())
