# Owl OCR Plan D: Installation and Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the app of plans A–C into something a stranger can install: a hardware probe and tier choice, a resumable one-time engine installer with a setup wizard, the optional download of plan C's spell-check dictionaries, a CPU device patch, a packaged Windows build (installer and portable zip) and a public 0.1.0 release.
**Architecture:** `owlocr/hardware.py` probes the GPU with `nvidia-smi` and chooses a tier; `owlocr/engine/bootstrap.py` runs ten idempotent stages (`install_kit.py` holds their building blocks, `stages.py` the stages) that install uv, Python 3.11, torch, the dependencies, the model (through plan A's `store`), the worker, the CPU patch and a self-test into the data root, and writes `install.json` last. `owlocr/web/wizard_api.py` and `owlocr/web/dictionaries_api.py` expose this and plan C's dictionary download to the UI as Flask blueprints registered on plan B's app, and `wizard.js` renders the wizard steps (plus an optional dictionary step) into plan B's `viewWizard` and a Dictionaries section into Settings; PyInstaller (onedir) plus Inno Setup package the app, its data files and plan C's font, without torch.
**Tech Stack:** Python 3.11, Flask 3 blueprint, vanilla JavaScript, uv (pinned, sha256-checked), PyTorch 2.10.0 (cu128 or cpu index), transformers 4.57.1, PyInstaller 6 onedir, Inno Setup 6, pytest, Pillow.
**Spec:** docs/superpowers/specs/2026-09-28-owl-ocr-design.md and docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md

## Global Constraints

- Windows 10/11 x64 only; Python 3.11; every command below runs from the repository root in PowerShell.
- Work on a new branch made from the branch that contains plans A, B and C: `git switch -c plan-d-install-release`.
- Pinned engine (design 5.1): model `baidu/Unlimited-OCR` at revision `07dea832e22aefee32ad281d4b80551282e1c168`, weights `model-00001-of-000001.safetensors` 6,672,547,120 bytes, sha256 `2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6`; torch `2.10.0`, torchvision `0.25.0`, transformers `4.57.1` exactly; Python 3.11; torch indexes `https://download.pytorch.org/whl/cu128` and `https://download.pytorch.org/whl/cpu`; cu128 needs NVIDIA driver 570.65 or newer.
- uv is pinned in `owlocr/engine/pins.json` (version, URL, sha256) and its archive is verified by sha256 before use.
- Download once (design 6.3): `models\unlimited_ocr\manifest.json` is written after all files verify; `engine\install.json` after the self-test; later starts check only files, versions and sizes, never hash and never touch the network; every stage is skipped when its check passes.
- Free space needed on the data drive: 16 GB (minus what the engine and model already occupy).
- AppData trap (design 4.1): tools started from an AI session get writes to `%APPDATA%` and `%LOCALAPPDATA%` redirected. Every test and every command run from a session sets `OWLOCR_HOME` and `OWLOCR_CONFIG` (plan A's autouse fixture `owl_env` does it for pytest). Consequence: the real installer and the first real start of the installed app are done by the owner, started normally from Explorer, never from an AI session.
- Never bundle torch, torchvision, transformers or other engine libraries in the app; the build fails if they appear.
- PyInstaller ONEDIR, never onefile.
- Never run `.bat` files on the owner's PC; build with `py packaging\build.py`.
- Never run GPU tests with less than 9,500 MiB of free VRAM (`nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits`). The default pytest run deselects `gpu`; GPU tests are run explicitly with `-m gpu`.
- To hide the GPU use `CUDA_VISIBLE_DEVICES=-1`; an empty value does not hide it on the owner's PC (plan A, task 16).
- Never commit anything from `samples/` (a copyrighted textbook).
- The spell-check dictionaries (plan C) are never bundled; they are downloaded only when the user asks, and the app works without them.
- The worker scripts are copied unchanged into the engine (`owl_worker.py` contains the stdin-detach step that prevents `import torch` from hanging); never rewrite them.
- Every POST and DELETE to the local server carries the header `X-Owl: 1` (plan B guard); wizard code uses plan B's `api()` helper, tests send the header.
- Subagents run on Opus 5.5 or Sonnet, never on another model.
- Every commit message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Pushing, changing repository visibility, publishing and creating releases happen only on the owner's explicit instruction, given at that moment.

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `owlocr/hardware.py` | Modify (append) | `Gpu`, `Tier`, `probe_gpus` (nvidia-smi CSV, name → compute capability fallback), `ram_total_mib`, `choose_tier`, `tier_by_name` |
| `worker/device_patch.py` | Create | makes `modeling_unlimitedocr.py` device-agnostic; refuses unknown upstream code; `.orig` backup; manifest update; `--restore`, `--check` |
| `licenses/Apache-2.0.txt` | Create | official Apache-2.0 text (bundled; copied into the model folder) |
| `packaging/pin_uv.py` | Create | writes `owlocr/engine/pins.json` from the uv release; `--verify` checks archive and flags |
| `owlocr/engine/pins.json` | Create (generated) | pinned uv version, URL, sha256 |
| `owlocr/engine/uvtool.py` | Create | resumable HTTPS download, window-less command runner inside a Job Object |
| `owlocr/engine/install_kit.py` | Create | `BootstrapError`, `Deps`, `StageContext`, engine folder layout, stamps, env for uv, `run_tool`, `probe_tool` |
| `owlocr/engine/stages.py` | Create | the ten stages: check and action each, registered in `CHECKS` / `ACTIONS` |
| `owlocr/engine/bootstrap.py` | Create | contract API: `STAGES`, `StageEvent`, `install_path`, `is_installed`, `read_install`, `run`, `remove_engine`, `BootstrapError`; plus `reset_install`, `sync_worker_files`, `was_interrupted`, `load_pins` |
| `owlocr/engine/relocate.py` | Create | validate, choose and move the data root |
| `owlocr/uninstall.py` | Create | `--remove-data` for the uninstaller |
| `owlocr/web/wizard_api.py` | Create | Flask blueprint: wizard routes, engine routes, `InstallController`, demo install |
| `owlocr/web/dictionaries_api.py` | Create | Flask blueprint: list, download (background, progress), remove the dictionaries of plan C |
| `owlocr/web/server.py` | Modify | registers both blueprints in `create_app` |
| `owlocr/jobs/engines.py` | Modify | `engine_installed()` uses `bootstrap.is_installed()` |
| `owlocr/web/static/selftest.png` | Create (copy) | the self-test page (`tests/fixtures/pages/01_letter_clean.png`) |
| `owlocr/web/static/wizard_i18n.js` | Create | all wizard strings, Czech and English (`wz_` keys), merged into `OWL_STRINGS` |
| `owlocr/web/static/wizard.js` | Create | the wizard steps plus the optional dictionary step, progress polling, pause/continue, adopt, location, Reinstall and Move actions, the Settings Dictionaries section |
| `owlocr/web/static/wizard.css` | Create | wizard styles on plan B's colour variables |
| `owlocr/web/static/index.html` | Modify | empty `viewWizard`, empty `dictSettings` panel in Settings, wizard scripts and stylesheet |
| `owlocr/web/static/app.js` | Modify | `OwlWizard.init`, `show` on the wizard view, Settings engine buttons, Dictionaries section |
| `owlocr/web/static/i18n.js` | Modify | removes plan B's four placeholder keys |
| `packaging/launcher.py` | Create | PyInstaller entry point: null streams, `--remove-data`, `owlocr.__main__.main()` |
| `packaging/make_icon.py` | Create | pixel-art owl `.ico` |
| `packaging/notices.py` | Create | generates `packaging/THIRD_PARTY_NOTICES.md` (packages, DejaVu Sans, dictionaries note) |
| `packaging/THIRD_PARTY_NOTICES.md` | Create (generated) | licences of every bundled package |
| `packaging/owlocr.spec` | Create | PyInstaller onedir, windowed, data files (static UI, pins, dictionaries manifest, fonts, worker, licences), collect-all, excludes |
| `packaging/installer.iss` | Create | Inno Setup per-user installer with the remove-data question |
| `packaging/build.py` | Create | clean, icon, notices, PyInstaller, forbidden-library and bundled-file checks, smoke test, zip, installer, SHA256SUMS |
| `packaging/scrub_local_paths.py` | Create | removes local paths and the Windows user name from tracked files before going public |
| `README.md`, `README.cs.md` | Modify / Create | user documentation in English and Czech |
| `docs/release-notes-0.1.0.md` | Create | text of the GitHub release |
| `docs/research/2026-09-28-cpu-acceptance.md` | Create | measured result and decision of the CPU acceptance test |
| `docs/images/smartscreen-1.png`, `smartscreen-2.png` | Create (screenshots) | SmartScreen screenshots for the READMEs |
| `tests/test_hardware_tiers.py` | Create | probe parsing, name table, tiers |
| `tests/test_device_patch.py` | Create | patcher on copies of the real model files |
| `tests/test_license_files.py` | Create | Apache text hash, engine requirements |
| `tests/test_pin_uv.py` | Create | pin helpers, committed pins |
| `tests/test_uvtool.py` | Create | download with resume, command runner, cancel |
| `tests/test_install_kit.py` | Create | helpers of the installer |
| `tests/test_bootstrap_core.py` | Create | orchestration with a scripted stage table |
| `tests/install_fakes.py` | Create | fake uv, fake Pythons, fake store and engine |
| `tests/test_stages.py` | Create | every stage against the fakes |
| `tests/test_bootstrap_e2e.py` | Create | full installations, resume, reinstall, remove |
| `tests/test_relocate.py`, `tests/test_uninstall.py` | Create | data root and uninstall |
| `tests/wizard_fakes.py`, `tests/test_wizard_api.py`, `tests/test_engine_routes.py`, `tests/test_dictionaries_api.py` | Create | blueprint tests |
| `tests/test_server_wizard.py` | Create | both blueprints inside plan B's app |
| `tests/test_engines.py` | Modify | one plan B test follows the new installed check |
| `tests/test_selftest_page.py`, `tests/test_wizard_strings.py`, `tests/test_wizard_integration.py` | Create | UI assets |
| `tests/test_launcher.py`, `tests/test_make_icon.py`, `tests/test_notices.py`, `tests/test_spec.py`, `tests/test_installer_script.py`, `tests/test_build.py` | Create | packaging |
| `tests/test_readme.py`, `tests/test_scrub.py`, `tests/test_release_ready.py` | Create | documentation and release checks |
| `tests/acceptance/__init__.py`, `tests/acceptance/prepare_cpu_root.py`, `tests/acceptance/test_cpu_acceptance.py` | Create | manual CPU acceptance test |

---

### Task 1: Hardware types and the GPU probe

**Files:**
- Modify: `owlocr/hardware.py` (append below plan A's code; plan A's `REQUIRED_FREE_VRAM_MIB`, `_CREATE_NO_WINDOW` and `free_vram_mib` stay exactly as they are)
- Test: `tests/test_hardware_tiers.py` (plan A already owns `tests/test_hardware.py`; do not touch it)

**Interfaces:**
- Consumes: plan A's `REQUIRED_FREE_VRAM_MIB = {"quality": 9500, "fast": 7500}` and `free_vram_mib() -> int | None`.
- Produces (contract): `@dataclass Gpu(name: str, driver: str, vram_total_mib: int, vram_free_mib: int, compute_cap: float | None)`, `@dataclass Tier(name: str, device: str, dtype: str, default_mode: str, torch_index: str, reason: str)`, `probe_gpus() -> list[Gpu]`, `ram_total_mib() -> int`. Additions: `tier_by_name(name: str, reason: str = "ok") -> Tier`, `compute_cap_from_name(name: str) -> float | None`, `parse_driver_version(text: str) -> tuple[int, int] | None`, `parse_nvidia_smi(text: str, with_compute_cap: bool) -> list[Gpu]`, constants `CREATE_NO_WINDOW`, `TORCH_INDEXES`, `MIN_DRIVER_CU128`, `GPU_FULL_MIN_VRAM_MIB`, `GPU_REDUCED_MIN_VRAM_MIB`, `CPU_MIN_RAM_MIB`, `CPU_TIER_ENABLED`.

Facts checked on the owner's PC: `nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free,compute_cap --format=csv,noheader,nounits` prints `NVIDIA GeForce RTX 4080 SUPER, 617.14, 16376, 13858, 8.9`; asking for a field the driver does not know prints `Field "..." is not a valid field to query.` and exits with code 2, so an old driver without `compute_cap` is detected by the exit code and queried again without it. WMI `AdapterRAM` saturates at 4 GB and is never used.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hardware_tiers.py`:

```python
import subprocess
from pathlib import Path

import pytest

from owlocr import hardware
from owlocr.hardware import Gpu, Tier, parse_nvidia_smi, probe_gpus, tier_by_name

RTX4080 = "NVIDIA GeForce RTX 4080 SUPER, 617.14, 16376, 13858, 8.9\n"


def gpu(name="NVIDIA GeForce RTX 4080 SUPER", driver="617.14", total=16376, free=13858, cap=8.9):
    return Gpu(name=name, driver=driver, vram_total_mib=total, vram_free_mib=free, compute_cap=cap)


def test_plan_a_items_still_present():
    assert hardware.REQUIRED_FREE_VRAM_MIB == {"quality": 9500, "fast": 7500}
    assert callable(hardware.free_vram_mib)


def test_parse_one_gpu_with_compute_cap():
    assert parse_nvidia_smi(RTX4080, with_compute_cap=True) == [gpu()]


def test_parse_two_gpus_and_blank_lines():
    text = RTX4080 + "\n" + "NVIDIA GeForce RTX 3060, 617.14, 12288, 11000, 8.6\n"
    names = [g.name for g in parse_nvidia_smi(text, with_compute_cap=True)]
    assert names == ["NVIDIA GeForce RTX 4080 SUPER", "NVIDIA GeForce RTX 3060"]


def test_parse_not_available_values():
    text = "NVIDIA GeForce RTX 3080, 560.94, 10240, [N/A], [N/A]\n"
    (g,) = parse_nvidia_smi(text, with_compute_cap=True)
    assert g.vram_free_mib == 0
    assert g.compute_cap == 8.6          # fell back to the name table


def test_parse_without_compute_cap_column_uses_name_table():
    text = "NVIDIA GeForce GTX 1080, 472.12, 8192, 7000\n"
    (g,) = parse_nvidia_smi(text, with_compute_cap=False)
    assert (g.driver, g.vram_total_mib, g.vram_free_mib, g.compute_cap) == ("472.12", 8192, 7000, 6.1)


@pytest.mark.parametrize("name,cap", [
    ("NVIDIA GeForce RTX 5090", 12.0),
    ("NVIDIA GeForce RTX 4060 Laptop GPU", 8.9),
    ("NVIDIA RTX 6000 Ada Generation", 8.9),
    ("NVIDIA GeForce RTX 3080 Ti", 8.6),
    ("NVIDIA RTX A4000", 8.6),
    ("NVIDIA A100-SXM4-40GB", 8.0),
    ("NVIDIA GeForce RTX 2080 Ti", 7.5),
    ("NVIDIA GeForce GTX 1660 SUPER", 7.5),
    ("Tesla T4", 7.5),
    ("NVIDIA GeForce GTX 1070", 6.1),
    ("NVIDIA GeForce GTX 970", 5.2),
    ("Some Future Card", None),
])
def test_compute_cap_name_table(name, cap):
    assert hardware.compute_cap_from_name(name) == cap


def test_probe_retries_without_compute_cap(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args[1])
        if "compute_cap" in args[1]:
            return subprocess.CompletedProcess(args, 2, 'Field "compute_cap" is not a valid field to query.\n', "")
        return subprocess.CompletedProcess(args, 0, "NVIDIA GeForce GTX 1080, 472.12, 8192, 7000\n", "")

    monkeypatch.setattr(hardware, "_find_nvidia_smi", lambda: Path("nvidia-smi.exe"))
    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    gpus = probe_gpus()
    assert [g.compute_cap for g in gpus] == [6.1]
    assert calls == ["--query-gpu=name,driver_version,memory.total,memory.free,compute_cap",
                     "--query-gpu=name,driver_version,memory.total,memory.free"]


def test_probe_without_nvidia_smi(monkeypatch):
    monkeypatch.setattr(hardware, "_find_nvidia_smi", lambda: None)
    assert probe_gpus() == []


def test_probe_when_nvidia_smi_fails_twice(monkeypatch):
    monkeypatch.setattr(hardware, "_find_nvidia_smi", lambda: Path("nvidia-smi.exe"))
    monkeypatch.setattr(hardware.subprocess, "run",
                        lambda args, **kw: subprocess.CompletedProcess(args, 9, "", "NVML error"))
    assert probe_gpus() == []


def test_ram_total_is_plausible():
    assert 1024 < hardware.ram_total_mib() < 16 * 1024 * 1024


def test_tier_properties():
    assert tier_by_name("gpu_full") == Tier("gpu_full", "cuda", "bfloat16", "quality",
                                            "https://download.pytorch.org/whl/cu128", "ok")
    assert tier_by_name("gpu_reduced").default_mode == "fast"
    assert tier_by_name("cpu") == Tier("cpu", "cpu", "float32", "fast",
                                       "https://download.pytorch.org/whl/cpu", "ok")
    with pytest.raises(ValueError):
        tier_by_name("turbo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_hardware_tiers.py -q`
Expected: collection error `ImportError: cannot import name 'Gpu' from 'owlocr.hardware'`.

- [ ] **Step 3: Write minimal implementation**

Append this block to the end of `owlocr/hardware.py`. It re-imports `subprocess` next to its other imports; that is harmless and keeps the block self-contained. Do not rename plan A's `_CREATE_NO_WINDOW`.

```python
# ---------------------------------------------------------------------------------------------
# Plan D: GPU probe, RAM probe and hardware tiers (design 6.4). Everything below is plan D.
# ---------------------------------------------------------------------------------------------
import ctypes
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

TORCH_INDEXES = {
    "cu128": "https://download.pytorch.org/whl/cu128",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
MIN_DRIVER_CU128 = (570, 65)        # CUDA 12.8 wheels need Windows driver 570.65 or newer
GPU_FULL_MIN_VRAM_MIB = 9984        # "10 GB" cards report slightly less than 10240 MiB
GPU_REDUCED_MIN_VRAM_MIB = 7936     # "8 GB" cards report slightly less than 8192 MiB
CPU_MIN_RAM_MIB = 15360             # "16 GB" PCs report 15.x GiB usable
CPU_TIER_ENABLED = True             # decided by the CPU acceptance test (plan D, task 30)

_SMI_FIELDS_FULL = "name,driver_version,memory.total,memory.free,compute_cap"
_SMI_FIELDS_BASIC = "name,driver_version,memory.total,memory.free"

# Used only when nvidia-smi has no compute_cap column (drivers older than about 510).
# The first matching pattern wins, so more specific patterns come first.
_COMPUTE_CAP_BY_NAME: tuple[tuple[str, float], ...] = (
    (r"RTX\s*PRO\s*\d+\s*Blackwell", 12.0),
    (r"RTX\s*50\d0", 12.0),
    (r"\bB[12]00\b", 10.0),
    (r"\bG?H[12]00\b", 9.0),
    (r"RTX\s*40\d0", 8.9),
    (r"RTX\s*\d{4}\s*Ada", 8.9),
    (r"\bL4\b|\bL40S?\b", 8.9),
    (r"\bA100\b|\bA30\b", 8.0),
    (r"RTX\s*30\d0", 8.6),
    (r"RTX\s*A\d{3,4}\b", 8.6),
    (r"\bA10G?\b|\bA16\b|\bA40\b|\bA2\b", 8.6),
    (r"TITAN\s*RTX", 7.5),
    (r"RTX\s*20\d0", 7.5),
    (r"GTX\s*16\d0", 7.5),
    (r"Quadro\s*RTX", 7.5),
    (r"\bT4\b|\bT(400|500|550|600|1000|1200)\b", 7.5),
    (r"TITAN\s*V\b|\bV100\b", 7.0),
    (r"GTX\s*10\d0|TITAN\s*Xp?\b|Quadro\s*P\d+", 6.1),
    (r"\bP100\b", 6.0),
    (r"GTX\s*9\d0|Quadro\s*M\d+", 5.2),
    (r"GTX\s*7\d0", 3.5),
)

_REASON_RANK = {"no_nvidia_gpu": 0, "gpu_too_old": 1, "vram_too_small": 2, "driver_too_old": 3}


@dataclass
class Gpu:
    name: str
    driver: str
    vram_total_mib: int
    vram_free_mib: int
    compute_cap: float | None


@dataclass
class Tier:
    name: str            # 'gpu_full' | 'gpu_reduced' | 'cpu' | 'unsupported'
    device: str          # 'cuda' | 'cpu'
    dtype: str           # 'bfloat16' | 'float32'
    default_mode: str    # 'quality' | 'fast'
    torch_index: str     # URL
    reason: str


def tier_by_name(name: str, reason: str = "ok") -> Tier:
    """The fixed properties of each tier of design 6.4."""
    if name == "gpu_full":
        return Tier("gpu_full", "cuda", "bfloat16", "quality", TORCH_INDEXES["cu128"], reason)
    if name == "gpu_reduced":
        return Tier("gpu_reduced", "cuda", "bfloat16", "fast", TORCH_INDEXES["cu128"], reason)
    if name == "cpu":
        return Tier("cpu", "cpu", "float32", "fast", TORCH_INDEXES["cpu"], reason)
    if name == "unsupported":
        return Tier("unsupported", "cpu", "float32", "fast", "", reason)
    raise ValueError(f"unknown tier {name!r}")


def compute_cap_from_name(name: str) -> float | None:
    for pattern, cap in _COMPUTE_CAP_BY_NAME:
        if re.search(pattern, name, re.IGNORECASE):
            return cap
    return None


def parse_driver_version(text: str) -> tuple[int, int] | None:
    m = re.match(r"\s*(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _int_or_zero(text: str) -> int:
    m = re.match(r"\s*(\d+)", text or "")
    return int(m.group(1)) if m else 0


def _float_or_none(text: str) -> float | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*$", text or "")
    return float(m.group(1)) if m else None


def parse_nvidia_smi(text: str, with_compute_cap: bool) -> list[Gpu]:
    """Parses `--format=csv,noheader,nounits` output of the two queries above."""
    gpus: list[Gpu] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4 or not parts[0]:
            continue
        cap = _float_or_none(parts[4]) if with_compute_cap and len(parts) >= 5 else None
        if cap is None:
            cap = compute_cap_from_name(parts[0])
        gpus.append(Gpu(name=parts[0], driver=parts[1], vram_total_mib=_int_or_zero(parts[2]),
                        vram_free_mib=_int_or_zero(parts[3]), compute_cap=cap))
    return gpus


def _find_nvidia_smi() -> Path | None:
    found = shutil.which("nvidia-smi")
    if found:
        return Path(found)
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
    return system32 if system32.is_file() else None


def _query_nvidia_smi(exe: Path, fields: str) -> str | None:
    try:
        done = subprocess.run([str(exe), f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=15, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def probe_gpus() -> list[Gpu]:
    """NVIDIA GPUs as nvidia-smi reports them. Never WMI AdapterRAM: it saturates at 4 GB."""
    exe = _find_nvidia_smi()
    if exe is None:
        return []
    out = _query_nvidia_smi(exe, _SMI_FIELDS_FULL)
    if out is not None:
        return parse_nvidia_smi(out, with_compute_cap=True)
    out = _query_nvidia_smi(exe, _SMI_FIELDS_BASIC)   # old drivers reject the compute_cap field
    if out is not None:
        return parse_nvidia_smi(out, with_compute_cap=False)
    return []


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_total_mib() -> int:
    status = _MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(status.ullTotalPhys // (1024 * 1024))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_hardware_tiers.py tests/test_hardware.py -q`
Expected: `22 passed` from the new file, and plan A's `tests/test_hardware.py` still passes (0 failed).

- [ ] **Step 5: Commit**

```
git add owlocr/hardware.py tests/test_hardware_tiers.py
git commit -m "Add GPU probe with compute-capability fallback and RAM probe" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Choosing the hardware tier

**Files:**
- Modify: `owlocr/hardware.py` (append)
- Test: `tests/test_hardware_tiers.py` (append)

**Interfaces:**
- Consumes: `Gpu`, `tier_by_name`, `compute_cap_from_name`, `parse_driver_version`, the constants of Task 1.
- Produces (contract): `choose_tier(gpus: list[Gpu], ram_mib: int) -> Tier`. `Tier.reason` is a code the UI translates: `ok`, `driver_too_old`, `gpu_too_old`, `vram_too_small`, `no_nvidia_gpu`, `ram_too_small`.

Rules (design 6.4): a GPU counts only with driver 570.65 or newer; `gpu_full` needs compute capability 8.0 or more and at least 9,984 MiB (a "10 GB" card reports slightly less than 10,240); `gpu_reduced` needs compute capability 7.5 or more and at least 7,936 MiB; the best GPU wins; otherwise `cpu` when `CPU_TIER_ENABLED` and RAM is at least 15,360 MiB (a "16 GB" PC reports 15.x GiB); otherwise `unsupported`. A Turing card (7.5) with more than 10 GB is `gpu_reduced`, because bfloat16 arithmetic is an Ampere feature. With an old driver and enough RAM the result is `cpu` with reason `driver_too_old`: the wizard asks for a driver update and reads with the processor meanwhile.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hardware_tiers.py`:

```python
# ---- tier choice (task 2) ----------------------------------------------------------------
from owlocr.hardware import choose_tier  # noqa: E402

RAM_64 = 65_000
RAM_8 = 8_000


@pytest.fixture(autouse=True)
def cpu_tier_on(monkeypatch):
    """The table below describes the tier logic, whatever the CPU acceptance test decides."""
    monkeypatch.setattr(hardware, "CPU_TIER_ENABLED", True)


@pytest.mark.parametrize("gpus,ram,expected_name,expected_reason", [
    ([gpu()], RAM_64, "gpu_full", "ok"),                                           # the owner's PC
    ([gpu(name="RTX 3080", total=10240, cap=8.6)], RAM_64, "gpu_full", "ok"),      # 10 GB counts as 10 GB
    ([gpu(name="RTX 3070", total=8192, cap=8.6)], RAM_64, "gpu_reduced", "ok"),
    ([gpu(name="RTX 4060 Laptop", total=8188, cap=8.9)], RAM_8, "gpu_reduced", "ok"),
    ([gpu(name="RTX 2080 Ti", total=11264, cap=7.5)], RAM_64, "gpu_reduced", "ok"),  # Turing is never full
    ([gpu(name="RTX 3050", total=6144, cap=8.6)], RAM_64, "cpu", "vram_too_small"),
    ([gpu(name="GTX 1080 Ti", total=11264, cap=6.1)], RAM_64, "cpu", "gpu_too_old"),
    ([gpu(driver="566.36")], RAM_64, "cpu", "driver_too_old"),                    # below 570.65
    ([gpu(driver="570.64")], RAM_64, "cpu", "driver_too_old"),
    ([gpu(driver="570.65")], RAM_64, "gpu_full", "ok"),
    ([], RAM_64, "cpu", "no_nvidia_gpu"),
    ([], RAM_8, "unsupported", "ram_too_small"),
    ([gpu(driver="566.36")], RAM_8, "unsupported", "driver_too_old"),
    ([gpu(name="RTX 3050", total=6144, cap=8.6), gpu()], RAM_64, "gpu_full", "ok"),  # best GPU wins
    ([gpu(name="RTX 3070", total=8192, cap=8.6), gpu(driver="566.36")], RAM_64, "gpu_reduced", "ok"),
])
def test_choose_tier(gpus, ram, expected_name, expected_reason):
    tier = choose_tier(gpus, ram)
    assert (tier.name, tier.reason) == (expected_name, expected_reason)


def test_choose_tier_when_cpu_tier_is_disabled(monkeypatch):
    monkeypatch.setattr(hardware, "CPU_TIER_ENABLED", False)
    assert choose_tier([], RAM_64).name == "unsupported"
    assert choose_tier([], RAM_64).reason == "no_nvidia_gpu"
    assert choose_tier([gpu(driver="566.36")], RAM_64).reason == "driver_too_old"
    assert choose_tier([gpu()], RAM_64).name == "gpu_full"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_hardware_tiers.py -q`
Expected: collection error `ImportError: cannot import name 'choose_tier' from 'owlocr.hardware'`.

- [ ] **Step 3: Write minimal implementation**

Append to `owlocr/hardware.py`:

```python
def _gpu_tier(gpu: Gpu) -> tuple[str | None, str]:
    """(tier name or None, reason code) for one GPU."""
    driver = parse_driver_version(gpu.driver)
    if driver is None or driver < MIN_DRIVER_CU128:
        return None, "driver_too_old"
    cap = gpu.compute_cap if gpu.compute_cap is not None else compute_cap_from_name(gpu.name)
    if cap is None or cap < 7.5:
        return None, "gpu_too_old"
    if cap >= 8.0 and gpu.vram_total_mib >= GPU_FULL_MIN_VRAM_MIB:
        return "gpu_full", "ok"
    if gpu.vram_total_mib >= GPU_REDUCED_MIN_VRAM_MIB:
        return "gpu_reduced", "ok"
    return None, "vram_too_small"


def choose_tier(gpus: list[Gpu], ram_mib: int) -> Tier:
    """Design 6.4. `reason` is a code that the UI translates:
    ok, driver_too_old, gpu_too_old, vram_too_small, no_nvidia_gpu, ram_too_small."""
    best: str | None = None
    problem = "no_nvidia_gpu"
    for gpu in gpus:
        name, reason = _gpu_tier(gpu)
        if name == "gpu_full" or (name == "gpu_reduced" and best is None):
            best = name
        elif name is None and _REASON_RANK[reason] > _REASON_RANK[problem]:
            problem = reason
    if best is not None:
        return tier_by_name(best, "ok")
    if CPU_TIER_ENABLED and ram_mib >= CPU_MIN_RAM_MIB:
        return tier_by_name("cpu", problem)
    if CPU_TIER_ENABLED and problem != "driver_too_old":
        problem = "ram_too_small"
    return tier_by_name("unsupported", problem)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_hardware_tiers.py -q`
Expected: `38 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/hardware.py tests/test_hardware_tiers.py
git commit -m "Add hardware tier choice with the cu128 driver floor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Device patch for the processor

**Files:**
- Create: `worker/device_patch.py`
- Test: `tests/test_device_patch.py`

**Interfaces:**
- Consumes: the model folder of plan A's store (`manifest.json` with `{"commit", "files": {path: {"size", "sha256", "git_sha1"}}}`).
- Produces: `python device_patch.py --model-dir <dir> [--device cpu|cuda] [--dtype float32|bfloat16|float16] [--restore | --check]`, exit codes 0 done or nothing to do, 1 error, 2 refused (upstream code changed), 3 `--check` found no patch. Module names used by the tests and by `stages.py`: `SENTINEL = "# --- owl-ocr device patch v1 applied ---"`, `TARGET`, `CHECKED`, `EXPECTED_COUNTS`, `PatchRefused`, `apply(model_dir, device, dtype) -> str`, `restore(model_dir) -> str`, `is_patched(model_dir) -> bool`, `check_pristine(model_dir) -> str`, `patched_text(pristine, device, dtype) -> str`, `main(argv=None) -> int`.

Real line inventory, grepped on the pinned revision in `engine\models\unlimited_ocr`:

| File | `.cuda()` | `torch.autocast("cuda", dtype=torch.bfloat16)` | `.to(torch.bfloat16)` |
|---|---|---|---|
| `modeling_unlimitedocr.py` | 17 (line 582 in `forward()` on `images_seq_mask[idx].unsqueeze(-1)`; 1003–1005, 1028–1030, 1049, 1059, 1070 in `infer()`; 1241–1243, 1259 in `infer_multi()`) | 3 (lines 1018, 1042, 1238) | 5 (lines 886, 899, 933, 1205, plus the comment on 888) |
| `modeling_deepseekv2.py` | 0 | 0 | 0 |
| `deepencoder.py` | 0 | 0 | 0 (only the unused default `dtype=torch.bfloat16` of `build_sam_fast_vit_b`) |

So only `modeling_unlimitedocr.py` is rewritten; the other two are checked and refused if CUDA-only code ever appears in them. Replacements: the `forward()` mask gets `.to(inputs_embeds.device)` (it must follow the embeddings whatever the device), every other `.cuda()` becomes `.to(_OWL_DEVICE)`, each autocast becomes `torch.autocast(_OWL_DEVICE_TYPE, dtype=_OWL_DTYPE, enabled=_OWL_AUTOCAST)` (off on the processor, so everything stays fp32), and the forced casts become `.to(_OWL_DTYPE)`. A header states that the file was modified (Apache-2.0 section 4 practice) and defines the three names from the patch arguments, overridable at run time by `OWLOCR_DEVICE` / `OWLOCR_DTYPE`. The patched file is written through a temporary file and `os.replace`, so a hard link to the GPU engine's copy is never written through. The manifest keeps the pristine hashes under `modeling_unlimitedocr.py.orig` (so `store.verify()` checks the backup) and the patched file's size and sha256 under its own name (so `store.is_ready()` accepts it). Checked on the owner's PC with the spike's CPU torch: `torch.autocast("cpu", dtype=torch.float32, enabled=False)` runs without a warning.

The tests copy the three real model files and `manifest.json` from `engine\models\unlimited_ocr` (or `OWLOCR_TEST_MODEL_DIR`) into a temporary folder; they are skipped when the model is not there.

- [ ] **Step 1: Write the failing test**

Create `tests/test_device_patch.py`:

```python
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "worker"))
import device_patch  # noqa: E402

REAL_MODEL = Path(os.environ.get("OWLOCR_TEST_MODEL_DIR", REPO / "engine" / "models" / "unlimited_ocr"))
FILES = ("modeling_unlimitedocr.py", "modeling_deepseekv2.py", "deepencoder.py", "manifest.json")

pytestmark = pytest.mark.skipif(not (REAL_MODEL / "modeling_unlimitedocr.py").is_file(),
                                reason=f"real model code not found in {REAL_MODEL}")


@pytest.fixture
def model_copy(tmp_path):
    d = tmp_path / "unlimited_ocr"
    d.mkdir()
    for name in FILES:
        shutil.copy2(REAL_MODEL / name, d / name)
    return d


def git_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_copies_are_pristine(model_copy):
    manifest = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))
    for name in FILES[:3]:
        assert git_sha1(model_copy / name) == manifest["files"][name]["git_sha1"]


def test_patch_removes_every_cuda_call_and_compiles(model_copy):
    assert device_patch.apply(model_copy, "cpu", "float32") == "patched"
    for name in FILES[:3]:
        text = (model_copy / name).read_text(encoding="utf-8")
        assert text.count(".cuda()") == 0, name
        assert 'autocast("cuda"' not in text, name
        assert ".to(torch.bfloat16)" not in text, name
        py_compile.compile(str(model_copy / name), cfile=str(model_copy / (name + "c")), doraise=True)
    target = (model_copy / "modeling_unlimitedocr.py").read_text(encoding="utf-8")
    assert device_patch.SENTINEL in target
    assert target.startswith("# NOTICE: this file was modified by Owl OCR")
    assert "images_seq_mask[idx].unsqueeze(-1).to(inputs_embeds.device)" in target   # forward()
    assert target.count("torch.autocast(_OWL_DEVICE_TYPE, dtype=_OWL_DTYPE, enabled=_OWL_AUTOCAST)") == 3
    assert '_OWL_DEVICE = _owl_os.environ.get("OWLOCR_DEVICE", "cpu")' in target
    assert '_OWL_DTYPE = getattr(_owl_torch, _owl_os.environ.get("OWLOCR_DTYPE", "float32"))' in target


def test_patch_keeps_backup_and_updates_manifest(model_copy):
    before = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))["files"]["modeling_unlimitedocr.py"]
    device_patch.apply(model_copy, "cpu", "float32")
    backup = model_copy / "modeling_unlimitedocr.py.orig"
    assert git_sha1(backup) == before["git_sha1"]
    files = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert files["modeling_unlimitedocr.py.orig"] == before
    patched = (model_copy / "modeling_unlimitedocr.py").read_bytes()
    assert files["modeling_unlimitedocr.py"]["size"] == len(patched)
    assert files["modeling_unlimitedocr.py"]["sha256"] == hashlib.sha256(patched).hexdigest()
    assert files["modeling_unlimitedocr.py"]["git_sha1"] is None


def test_other_two_files_are_not_modified(model_copy):
    before = {n: (model_copy / n).read_bytes() for n in FILES[1:3]}
    device_patch.apply(model_copy, "cpu", "float32")
    assert {n: (model_copy / n).read_bytes() for n in FILES[1:3]} == before
    assert not (model_copy / "modeling_deepseekv2.py.orig").exists()


def test_second_run_is_a_no_op(model_copy):
    device_patch.apply(model_copy, "cpu", "float32")
    snapshot = {p.name: p.read_bytes() for p in model_copy.iterdir() if p.is_file()}
    assert device_patch.apply(model_copy, "cpu", "float32") == "already patched"
    assert {p.name: p.read_bytes() for p in model_copy.iterdir() if p.is_file()} == snapshot


def test_tampered_input_is_refused_and_left_alone(model_copy):
    target = model_copy / "modeling_unlimitedocr.py"
    text = target.read_text(encoding="utf-8")
    tampered = text.replace("input_ids.unsqueeze(0).cuda().shape[1]", "input_ids.unsqueeze(0).shape[1]", 1)
    assert tampered != text
    target.write_text(tampered, encoding="utf-8", newline="")
    with pytest.raises(device_patch.PatchRefused, match="expected upstream code"):
        device_patch.apply(model_copy, "cpu", "float32")
    assert target.read_text(encoding="utf-8") == tampered
    assert not (model_copy / "modeling_unlimitedocr.py.orig").exists()


def test_cuda_code_appearing_in_a_checked_file_is_refused(model_copy):
    other = model_copy / "deepencoder.py"
    other.write_text(other.read_text(encoding="utf-8") + "\nx = y.cuda()\n", encoding="utf-8", newline="")
    with pytest.raises(device_patch.PatchRefused, match="deepencoder.py"):
        device_patch.apply(model_copy, "cpu", "float32")


def test_restore_puts_the_original_back(model_copy):
    original = (model_copy / "modeling_unlimitedocr.py").read_bytes()
    manifest_before = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))
    device_patch.apply(model_copy, "cpu", "float32")
    assert device_patch.restore(model_copy) == "restored"
    assert (model_copy / "modeling_unlimitedocr.py").read_bytes() == original
    assert not (model_copy / "modeling_unlimitedocr.py.orig").exists()
    assert json.loads((model_copy / "manifest.json").read_text(encoding="utf-8")) == manifest_before
    assert device_patch.restore(model_copy) == "not patched"


def test_patch_does_not_write_through_a_hard_link(model_copy, tmp_path):
    shared = tmp_path / "shared.py"
    shutil.copy2(model_copy / "modeling_unlimitedocr.py", shared)
    (model_copy / "modeling_unlimitedocr.py").unlink()
    os.link(shared, model_copy / "modeling_unlimitedocr.py")
    before = shared.read_bytes()
    device_patch.apply(model_copy, "cpu", "float32")
    assert shared.read_bytes() == before


def test_command_line_exit_codes(model_copy):
    script = str(REPO / "worker" / "device_patch.py")
    run = lambda *a: subprocess.run([sys.executable, script, "--model-dir", str(model_copy), *a],
                                    capture_output=True, text=True)
    assert run("--check").returncode == 3
    done = run("--device", "cpu", "--dtype", "float32")
    assert done.returncode == 0 and "patched" in done.stdout
    assert run("--check").returncode == 0
    assert run("--restore").returncode == 0
    target = model_copy / "modeling_unlimitedocr.py"
    target.write_text(target.read_text(encoding="utf-8").replace(".cuda()", "", 1), encoding="utf-8", newline="")
    refused = run()
    assert refused.returncode == 2 and "REFUSED" in refused.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_device_patch.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'device_patch'`.

- [ ] **Step 3: Write minimal implementation**

Create `worker/device_patch.py` (standard library only; it runs with the engine's Python):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_device_patch.py -q`
Expected: `10 passed` (on the owner's PC, where `engine\models\unlimited_ocr` exists).

- [ ] **Step 5: Commit**

```
git add worker/device_patch.py tests/test_device_patch.py
git commit -m "Add device patch that makes the model code run on the processor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Licence text for the model folder

**Files:**
- Create: `licenses/Apache-2.0.txt`
- Test: `tests/test_license_files.py`

**Interfaces:**
- Consumes: plan A's `LICENSE` (MIT) and `worker/requirements-engine.txt` (used unchanged by the installer).
- Produces: `licenses/Apache-2.0.txt`, bundled with the app and copied into the model folder as `LICENSE-Apache-2.0.txt` by the worker stage (design 12: the model folder keeps Baidu's MIT `LICENSE` and gets the Apache text because `modeling_deepseekv2.py` carries an Apache header).

- [ ] **Step 1: Write the failing test**

Create `tests/test_license_files.py`:

```python
import hashlib

from tests.conftest import REPO

APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_apache_text_is_the_official_one():
    data = (REPO / "licenses" / "Apache-2.0.txt").read_bytes()
    assert hashlib.sha256(data).hexdigest() == APACHE_SHA256


def test_engine_requirements_keep_the_pins():
    text = (REPO / "worker" / "requirements-engine.txt").read_text(encoding="utf-8")
    assert "transformers==4.57.1" in text
    assert "torch" not in [line.split("=")[0].strip() for line in text.splitlines()]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_license_files.py -q`
Expected: `FileNotFoundError` for `licenses\Apache-2.0.txt` in `test_apache_text_is_the_official_one`; the other test passes.

- [ ] **Step 3: Write minimal implementation**

Download the official text (11,358 bytes, 202 lines; its sha256 is the one in the test, checked while writing this plan):

```
New-Item -ItemType Directory -Force licenses | Out-Null
curl.exe -sL https://www.apache.org/licenses/LICENSE-2.0.txt -o licenses\Apache-2.0.txt
(Get-FileHash licenses\Apache-2.0.txt -Algorithm SHA256).Hash
```

Expected hash: `CFC7749B96F63BD31C3C42B5C471BF756814053E847C10F3EB003417BC523D30`. If it differs, do not edit the file by hand: stop and report.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_license_files.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add licenses/Apache-2.0.txt tests/test_license_files.py
git commit -m "Add the Apache-2.0 text for the model folder" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Pinning uv

**Files:**
- Create: `packaging/pin_uv.py`, `owlocr/engine/pins.json` (generated by the script)
- Test: `tests/test_pin_uv.py`

**Interfaces:**
- Consumes: the GitHub release API of `astral-sh/uv` and the `.sha256` file published next to `uv-x86_64-pc-windows-msvc.zip`.
- Produces: `owlocr/engine/pins.json` = `{"uv": {"version": str, "url": str, "sha256": str}}`, read by `bootstrap.load_pins()`. Script functions: `asset_url(version)`, `parse_sha256_file(text)`, `digest_from_release(release)`, `build_pins(version, sha256)`, `pin(version, out)`, `verify(pins_file) -> list[str]`, `main(argv)`.

These three values are the only engine values looked up at build time. At the time of writing the newest release was uv 0.12.19 (published 2026-09-25, archive 17,955,780 bytes); pin whatever is newest when you run the command.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pin_uv.py`:

```python
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packaging"))
import pin_uv  # noqa: E402

SHA = "a" * 64


def test_parse_sha256_file():
    assert pin_uv.parse_sha256_file(f"{SHA} *uv-x86_64-pc-windows-msvc.zip\n") == SHA
    assert pin_uv.parse_sha256_file(SHA.upper()) == SHA
    with pytest.raises(ValueError):
        pin_uv.parse_sha256_file("<html>Not Found</html>")
    with pytest.raises(ValueError):
        pin_uv.parse_sha256_file("")


def test_digest_from_release():
    release = {"assets": [{"name": "uv-aarch64-apple-darwin.tar.gz", "digest": "sha256:" + "b" * 64},
                          {"name": pin_uv.ASSET, "digest": "sha256:" + SHA}]}
    assert pin_uv.digest_from_release(release) == SHA
    assert pin_uv.digest_from_release({"assets": [{"name": pin_uv.ASSET}]}) is None


def test_build_pins():
    pins = pin_uv.build_pins("0.12.19", SHA)
    assert pins == {"uv": {"version": "0.12.19", "sha256": SHA,
                           "url": "https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-pc-windows-msvc.zip"}}
    with pytest.raises(ValueError):
        pin_uv.build_pins("v0.12.19", SHA)


def test_pin_writes_file(tmp_path, monkeypatch):
    responses = {
        pin_uv.API_LATEST: json.dumps({"tag_name": "0.12.19", "assets": []}).encode(),
        pin_uv.asset_url("0.12.19") + ".sha256": f"{SHA} *{pin_uv.ASSET}\n".encode(),
    }
    monkeypatch.setattr(pin_uv, "_get", lambda url: responses[url])
    out = tmp_path / "pins.json"
    pin_uv.pin(None, out)
    assert json.loads(out.read_text(encoding="utf-8"))["uv"]["version"] == "0.12.19"


def test_pin_refuses_conflicting_digests(tmp_path, monkeypatch):
    responses = {
        pin_uv.API_TAG.format(tag="0.12.19"): json.dumps(
            {"tag_name": "0.12.19", "assets": [{"name": pin_uv.ASSET, "digest": "sha256:" + "c" * 64}]}).encode(),
        pin_uv.asset_url("0.12.19") + ".sha256": f"{SHA} *{pin_uv.ASSET}\n".encode(),
    }
    monkeypatch.setattr(pin_uv, "_get", lambda url: responses[url])
    with pytest.raises(ValueError, match="differs"):
        pin_uv.pin("0.12.19", tmp_path / "pins.json")


def test_committed_pins_file_is_valid():
    pins = json.loads((REPO / "owlocr" / "engine" / "pins.json").read_text(encoding="utf-8"))["uv"]
    assert len(pins["sha256"]) == 64 and int(pins["sha256"], 16) >= 0
    assert pins["url"] == pin_uv.asset_url(pins["version"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_pin_uv.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'pin_uv'`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/pin_uv.py`:

```python
"""Pins the uv release that the engine installer downloads: writes owlocr/engine/pins.json.

    py -3.11 packaging\\pin_uv.py                 latest uv release
    py -3.11 packaging\\pin_uv.py 0.12.19         a given release
    py -3.11 packaging\\pin_uv.py --verify        check the pinned archive and the uv flags we use

Without --verify only small text files are fetched (release metadata and the .sha256 file).
--verify downloads the pinned uv archive (about 18 MB) into a temporary folder, checks its sha256,
and runs `uv --help` commands to confirm the command-line flags bootstrap uses still exist.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PINS = REPO / "owlocr" / "engine" / "pins.json"
ASSET = "uv-x86_64-pc-windows-msvc.zip"
API_LATEST = "https://api.github.com/repos/astral-sh/uv/releases/latest"
API_TAG = "https://api.github.com/repos/astral-sh/uv/releases/tags/{tag}"
CREATE_NO_WINDOW = 0x08000000
# Flags used by owlocr/engine/stages.py; --verify fails if a pinned uv lacks any of them.
REQUIRED_FLAGS = {
    ("python", "install", "--help"): ("--no-bin", "--no-registry"),
    ("venv", "--help"): ("--python", "--no-project"),
    ("pip", "install", "--help"): ("--python", "--index-url", "--requirement"),
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "owl-ocr-pin-uv",
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def asset_url(version: str) -> str:
    return f"https://github.com/astral-sh/uv/releases/download/{version}/{ASSET}"


def parse_sha256_file(text: str) -> str:
    token = text.strip().split()[0].lower() if text.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError(f"not a sha256 file: {text[:80]!r}")
    return token


def digest_from_release(release: dict) -> str | None:
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET and str(asset.get("digest", "")).startswith("sha256:"):
            return asset["digest"].split(":", 1)[1].lower()
    return None


def build_pins(version: str, sha256: str) -> dict:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"unexpected uv version {version!r}")
    return {"uv": {"version": version, "url": asset_url(version), "sha256": sha256}}


def pin(version: str | None, out: Path = PINS) -> dict:
    release = json.loads(_get(API_TAG.format(tag=version) if version else API_LATEST))
    version = release["tag_name"]
    sha = parse_sha256_file(_get(asset_url(version) + ".sha256").decode("utf-8"))
    api_digest = digest_from_release(release)
    if api_digest is not None and api_digest != sha:
        raise ValueError(f"sha256 of {ASSET} differs between the .sha256 file and the release API")
    pins = build_pins(version, sha)
    out.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")
    return pins


def verify(pins_file: Path = PINS) -> list[str]:
    """Returns problems; empty when the pinned uv matches and supports every flag we use."""
    pins = json.loads(pins_file.read_text(encoding="utf-8"))["uv"]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="owl-uv-") as tmp:
        archive = Path(tmp) / ASSET
        archive.write_bytes(_get(pins["url"]))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != pins["sha256"]:
            return [f"sha256 mismatch: {digest} != {pins['sha256']}"]
        with zipfile.ZipFile(archive) as zf:
            member = next(n for n in zf.namelist() if n.replace("\\", "/").rsplit("/", 1)[-1] == "uv.exe")
            exe = Path(tmp) / "uv.exe"
            exe.write_bytes(zf.read(member))
        for args, flags in REQUIRED_FLAGS.items():
            done = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", creationflags=CREATE_NO_WINDOW, timeout=60)
            for flag in flags:
                if flag not in done.stdout:
                    problems.append(f"`uv {' '.join(args[:-1])}` has no {flag}")
    return problems


def main(argv: list[str]) -> int:
    if "--verify" in argv:
        problems = verify()
        for line in problems:
            print("PROBLEM:", line)
        print("uv pin OK" if not problems else "uv pin NOT OK")
        return 0 if not problems else 1
    version = argv[0] if argv else None
    pins = pin(version)
    print(json.dumps(pins, indent=1))
    print(f"written to {PINS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Then look up the pin and write it (this fetches only the release metadata and the small `.sha256` file):

```
py -3.11 packaging\pin_uv.py
```

Expected output: the JSON written to `owlocr\engine\pins.json`, for example
`{"uv": {"version": "0.12.19", "url": "https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-pc-windows-msvc.zip", "sha256": "<64 hex digits>"}}`.

Verify the pinned archive and the command-line flags the installer uses (this downloads the 18 MB archive into a temporary folder and deletes it afterwards):

```
py -3.11 packaging\pin_uv.py --verify
```

Expected: `uv pin OK`. If it prints `PROBLEM:` lines about a missing flag, pin an older release that has them (`py -3.11 packaging\pin_uv.py <version>`) and verify again; if none has them, stop and report, because `owlocr/engine/stages.py` passes `--no-bin`, `--no-registry` and `--no-project`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_pin_uv.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/pin_uv.py owlocr/engine/pins.json tests/test_pin_uv.py
git commit -m "Pin the uv release used by the engine installer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Download and command helpers

**Files:**
- Create: `owlocr/engine/uvtool.py`
- Test: `tests/test_uvtool.py`

**Interfaces:**
- Consumes: plan A's `owlocr.engine.lifetime.JobObject` (`assign(pid)`, `close()` kills the whole tree).
- Produces: `CREATE_NO_WINDOW`, `CANCELLED = -999`, `class Cancelled(Exception)`, `sha256_file(path) -> str`, `download_file(url, dest, on_progress=None, cancel=None, timeout_s=60.0) -> None` (resumes `<dest>.part` with an HTTP Range request), `run_command(args, env, on_line, cancel=None, cwd=None) -> int` (no window, stdout and stderr merged line by line, the process tree inside a Job Object so cancel or an app crash ends it; returns the exit code or `CANCELLED`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_uvtool.py`:

```python
import hashlib
import http.server
import os
import sys
import threading
import time

import pytest

from owlocr.engine import uvtool

PAYLOAD = bytes(range(256)) * 4096          # 1 MiB


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            if start >= len(PAYLOAD):
                self.send_response(416)
                self.end_headers()
                return
            self.send_response(206)
        else:
            self.send_response(200)
        body = PAYLOAD[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/file.zip"
    httpd.shutdown()


def test_download_whole_file(server, tmp_path):
    seen = []
    dest = tmp_path / "f.zip"
    uvtool.download_file(server, dest, on_progress=lambda d, t: seen.append((d, t)))
    assert dest.read_bytes() == PAYLOAD
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert not (tmp_path / "f.zip.part").exists()


def test_download_resumes_partial_file(server, tmp_path):
    dest = tmp_path / "f.zip"
    (tmp_path / "f.zip.part").write_bytes(PAYLOAD[:1000])
    uvtool.download_file(server, dest)
    assert dest.read_bytes() == PAYLOAD


def test_download_with_complete_partial_file(server, tmp_path):
    dest = tmp_path / "f.zip"
    (tmp_path / "f.zip.part").write_bytes(PAYLOAD)
    uvtool.download_file(server, dest)
    assert dest.read_bytes() == PAYLOAD


def test_download_cancel(server, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(uvtool.Cancelled):
        uvtool.download_file(server, tmp_path / "f.zip", cancel=cancel)
    assert not (tmp_path / "f.zip").exists()


def test_sha256_file(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(PAYLOAD)
    assert uvtool.sha256_file(p) == hashlib.sha256(PAYLOAD).hexdigest()


def test_run_command_streams_lines_and_returns_code():
    lines = []
    code = uvtool.run_command([sys.executable, "-c", "print('eins'); print('zwei ž'); raise SystemExit(3)"],
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, on_line=lines.append)
    assert code == 3
    assert lines == ["eins", "zwei ž"]


def test_run_command_cancel_kills_the_process():
    cancel = threading.Event()
    lines = []

    def on_line(line):
        lines.append(line)
        cancel.set()

    started = time.monotonic()
    code = uvtool.run_command(
        [sys.executable, "-u", "-c", "import time; print('started'); time.sleep(60)"],
        env=dict(os.environ), on_line=on_line, cancel=cancel)
    assert code == uvtool.CANCELLED
    assert lines == ["started"]
    assert time.monotonic() - started < 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_uvtool.py -q`
Expected: collection error `ImportError: cannot import name 'uvtool' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/uvtool.py`:

```python
"""Low-level helpers of the engine installer: HTTPS download and running a console tool.

Both are injected into `bootstrap._run` through `install_kit.Deps`, so tests can replace them.
"""
from __future__ import annotations

import hashlib
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
            for raw in proc.stdout:
                on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_uvtool.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/uvtool.py tests/test_uvtool.py
git commit -m "Add resumable download and window-less command runner" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Building blocks of the installer

**Files:**
- Create: `owlocr/engine/install_kit.py`
- Test: `tests/test_install_kit.py`

**Interfaces:**
- Consumes: `owlocr.paths` (`engine_dir`, `engine_python`, `worker_dir`, `model_dir`, `logs_dir`, `resource_path`, `atomic_write_text`), `owlocr.engine.store` (`is_ready`, `download`), `owlocr.engine.registry.UNLIMITED_OCR`, `owlocr.engine.uvtool`, `owlocr.hardware.Tier` and `free_vram_mib`, plan A's `SubprocessEngine(python, worker_script, model_dir, device, dtype, log_file, env=None)`.
- Produces: `class BootstrapError(RuntimeError)` (re-exported by `bootstrap`; messages are `"<code>: <details>"`), `@dataclass Deps(pins, resource, run_cmd, download_file, engine_factory, store_is_ready, store_download, free_vram, free_bytes)`, `class StageContext(tier, deps, cancel, emit, log)` with `report(done=None, total=None, message=None)` (throttled to 4 per second, never drops a new message or the final value) and `cancelled()`; layout helpers `uv_exe()`, `python_dir()`, `venv_dir()`, `uv_cache_dir()`, `stamps_dir()`, `install_file()`, `state_file()`; `read_json`, `read_stamp`, `write_stamp`, `managed_python()`, `venv_home_ok()`, `torch_flavor(tier)`, `requirements_sha256(resource=None)`, `disk_free(path)`, `dir_size(path)`, `rmtree(path)`, `copy_atomic(src, dst)`, `clean_env()`, `uv_env()`, `probe_tool(ctx, args) -> (code, lines)`, `run_tool(ctx, args, env=None) -> lines`, `python_is_311(ctx, exe)`, `default_engine(tier)`; constants `PYTHON_VERSION = "3.11"`, `WORKER_FILES`, `REQUIREMENTS_REL`, `APACHE_REL`, `SELFTEST_IMAGE_REL`, `PATCH_TARGET`, `PATCH_SENTINEL`, `APACHE_NAME`, `NOTICE_NAME`, `TORCH_DOWNLOAD_BYTES`, `SELFTEST_WORDS`, `SELFTEST_MIN_WORDS`, `SELFTEST_MAX_NEW_TOKENS`, `SELFTEST_TIME_LIMIT_S`, `INSTALL_FORMAT`, `MODEL_NOTICE`.

Engine folder layout (design 4): `<data root>\engine\tools\uv.exe`, `python\` (uv-managed CPython, `UV_PYTHON_INSTALL_DIR`), `venv\`, `uv-cache\` (kept on the same drive so a reinstall or a move needs no download), `worker\`, `stamps\`, `install.json`, `install_state.json` (present while an installation is unfinished). `uv_env()` removes every `UV_*` variable of the user's environment and sets `UV_NO_CONFIG=1` and `UV_PYTHON_PREFERENCE=only-managed`, so the user's own uv configuration can never redirect the installation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_install_kit.py`:

```python
import os
import stat
import sys
import threading

import pytest

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import uvtool
from owlocr.engine.install_kit import BootstrapError, Deps, StageContext
from owlocr.hardware import tier_by_name


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    return tmp_path / "data"


def make_ctx(run_cmd=None, cancel=None):
    emitted, logged = [], []
    deps = Deps(pins={}, run_cmd=run_cmd or (lambda args, env, on_line, cancel: 0))
    ctx = StageContext(tier_by_name("cpu"), deps, cancel, lambda d, t, m: emitted.append((d, t, m)), logged.append)
    return ctx, emitted, logged


def test_layout_of_the_engine_folder(home):
    engine = home / "engine"
    assert kit.uv_exe() == engine / "tools" / "uv.exe"
    assert kit.python_dir() == engine / "python"
    assert kit.venv_dir() == engine / "venv"
    assert kit.uv_cache_dir() == engine / "uv-cache"
    assert kit.install_file() == engine / "install.json"
    assert paths.engine_python() == kit.venv_dir() / "Scripts" / "python.exe"


def test_report_throttles_but_never_drops_text_or_completion(home):
    ctx, emitted, _ = make_ctx()
    ctx.report(done=1, total=100, message="a")
    for i in range(2, 50):
        ctx.report(done=i)                      # within 0.25 s: swallowed
    ctx.report(message="b")                    # new text: always emitted
    ctx.report(done=100)                       # finished: always emitted
    assert emitted[0] == (1, 100, "a")
    assert emitted[1] == (49, 100, "b")
    assert emitted[-1] == (100, 100, "b")
    assert len(emitted) == 3


def test_stamps_round_trip(home):
    assert kit.read_stamp("tools") is None
    kit.write_stamp("tools", {"version": "1"})
    assert kit.read_stamp("tools") == {"version": "1"}
    (kit.stamps_dir() / "bad.json").write_text("[1, 2", encoding="utf-8")
    assert kit.read_stamp("bad") is None


def test_managed_python_and_venv_home(home):
    assert kit.managed_python() is None
    base = kit.python_dir() / "cpython-3.11.13-windows-x86_64-none"
    base.mkdir(parents=True)
    (base / "python.exe").write_bytes(b"")
    assert kit.managed_python() == base / "python.exe"
    kit.venv_dir().mkdir(parents=True)
    (kit.venv_dir() / "pyvenv.cfg").write_text(f"home = {base}\n", encoding="utf-8")
    assert kit.venv_home_ok()
    (kit.venv_dir() / "pyvenv.cfg").write_text("home = C:\\Elsewhere\\python\n", encoding="utf-8")
    assert not kit.venv_home_ok()


def test_torch_flavor():
    assert kit.torch_flavor(tier_by_name("gpu_full")) == "cu128"
    assert kit.torch_flavor(tier_by_name("cpu")) == "cpu"


def test_uv_env_isolates_uv(home, monkeypatch):
    monkeypatch.setenv("UV_INDEX_URL", "https://evil.invalid/simple")
    monkeypatch.setenv("VIRTUAL_ENV", "C:\\some\\venv")
    env = kit.uv_env()
    assert "UV_INDEX_URL" not in env and "VIRTUAL_ENV" not in env
    assert env["UV_CACHE_DIR"] == str(kit.uv_cache_dir())
    assert env["UV_PYTHON_INSTALL_DIR"] == str(kit.python_dir())
    assert env["UV_NO_CONFIG"] == "1" and env["UV_PYTHON_PREFERENCE"] == "only-managed"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_run_tool_reports_failure_with_last_line(home):
    def fake(args, env, on_line, cancel):
        on_line("Resolved 3 packages")
        on_line("error: No solution found")
        return 2

    ctx, emitted, logged = make_ctx(fake)
    with pytest.raises(BootstrapError, match=r"command_failed: uv.exe pip install exited with 2: error: No solution found"):
        kit.run_tool(ctx, ["C:\\x\\uv.exe", "pip", "install", "torch"])
    assert logged[0].startswith("$ C:\\x\\uv.exe pip install torch")
    assert emitted[-1][2] == "error: No solution found"


def test_run_tool_cancel(home):
    cancel = threading.Event()
    cancel.set()
    ctx, _, _ = make_ctx(lambda args, env, on_line, c: uvtool.CANCELLED, cancel)
    with pytest.raises(BootstrapError, match="^cancelled$"):
        kit.run_tool(ctx, ["uv.exe", "venv"])


def test_probe_tool_never_raises(home):
    def boom(args, env, on_line, cancel):
        raise OSError("not found")

    ctx, _, logged = make_ctx(boom)
    assert kit.probe_tool(ctx, ["python.exe", "--version"]) == (-1, [])
    assert any("cannot start" in line for line in logged)


def test_python_is_311(home):
    ctx, _, _ = make_ctx(lambda args, env, on_line, cancel: on_line("Python 3.11.13") or 0)
    assert kit.python_is_311(ctx, kit.python_dir() / "python.exe")
    ctx, _, _ = make_ctx(lambda args, env, on_line, cancel: on_line("Python 3.12.1") or 0)
    assert not kit.python_is_311(ctx, kit.python_dir() / "python.exe")


def test_rmtree_removes_read_only_files(tmp_path):
    folder = tmp_path / "x" / "y"
    folder.mkdir(parents=True)
    locked = folder / "ro.txt"
    locked.write_text("x", encoding="utf-8")
    os.chmod(locked, stat.S_IREAD)
    kit.rmtree(tmp_path / "x")
    assert not (tmp_path / "x").exists()
    kit.rmtree(tmp_path / "missing")          # no error


def test_copy_atomic_and_dir_size(tmp_path):
    src = tmp_path / "a.bin"
    src.write_bytes(b"12345")
    kit.copy_atomic(src, tmp_path / "out" / "b.bin")
    assert (tmp_path / "out" / "b.bin").read_bytes() == b"12345"
    assert kit.dir_size(tmp_path) == 10


def test_requirements_sha256_uses_the_resource(tmp_path):
    (tmp_path / "worker").mkdir()
    (tmp_path / "worker" / "requirements-engine.txt").write_bytes(b"x\n")
    import hashlib
    assert kit.requirements_sha256(lambda rel: tmp_path / rel) == hashlib.sha256(b"x\n").hexdigest()


def test_disk_free_of_missing_path(tmp_path):
    assert kit.disk_free(tmp_path / "not" / "there") > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_install_kit.py -q`
Expected: collection error `ImportError: cannot import name 'install_kit' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/install_kit.py`:

```python
"""Building blocks of the engine installer: constants, the injectable dependencies, the stage
context, file and command helpers. The stages themselves are in `stages.py`.

Everything that touches the outside world goes through `Deps`, which the tests replace with fakes.
"""
from __future__ import annotations

import hashlib
import json
import os
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


def managed_python() -> Path | None:
    found = sorted(python_dir().glob(f"cpython-{PYTHON_VERSION}.*/python.exe"))
    return found[-1] if found else None


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


def run_tool(ctx: StageContext, args: list, env: dict[str, str] | None = None) -> list[str]:
    """Runs an installation command. Raises BootstrapError when it fails or is cancelled."""
    lines: list[str] = []

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_install_kit.py -q`
Expected: `14 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/install_kit.py tests/test_install_kit.py
git commit -m "Add building blocks of the engine installer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Installer orchestration and the contract API

**Files:**
- Create: `owlocr/engine/bootstrap.py`, `owlocr/engine/stages.py` (skeleton; the stages arrive in tasks 9–12)
- Test: `tests/test_bootstrap_core.py`

**Interfaces:**
- Consumes: everything of `install_kit` (Task 7), `owlocr.engine.store.is_ready()`, `owlocr.engine.registry.UNLIMITED_OCR`, `owlocr.paths`.
- Produces (contract): `STAGES = ("tools", "python", "venv", "torch", "deps", "model", "worker", "patch", "selftest", "mark")`, `@dataclass StageEvent(stage: str, state: str, done: int, total: int, message: str)` with states `start`, `progress`, `done`, `skipped`, `failed`, `install_path() -> Path`, `is_installed() -> bool`, `read_install() -> dict | None`, `run(tier: Tier, on_event: Callable[[StageEvent], None], cancel: threading.Event | None = None) -> None`, `remove_engine() -> None`, `class BootstrapError(RuntimeError)`. Additions: `REQUIRED_FREE_BYTES = 16 * 1024**3`, `required_free_bytes(already_present: int) -> int`, `load_pins() -> dict`, `was_interrupted() -> bool`, `reset_install() -> None`, `sync_worker_files() -> bool`, private `_run(tier, on_event, cancel, deps)` (the tests inject `Deps`). In `stages.py`: `CHECKS: dict[str, Callable[[StageContext], bool]]`, `ACTIONS: dict[str, Callable[[StageContext], None]]`.

How `run` works: refuse the `unsupported` tier; allow one installation at a time (a module lock); check free space on the data drive (16 GB minus what the engine and model folders already hold); write `install_state.json` (so the wizard can offer to continue after a restart); then for every stage: emit `start` ("checking"), run the check, emit `skipped` when it passes, otherwise run the action, check again, emit `done`. A `BootstrapError` or any other exception emits `failed` with the message and stops; cancel between stages or inside a stage ends with `BootstrapError("cancelled")`. Everything is logged to `<data root>\logs\install.log`. `install_state.json` is removed only after the last stage.

`is_installed()` is the only check made on every start and on every `/api/status` poll: it reads `install.json`, compares format, Python version, engine id, revision, torch, torchvision, transformers and the sha256 of `worker/requirements-engine.txt` with the app's pins, checks that the venv Python exists and still points at the managed Python (a moved data root does not), and asks `store.is_ready()` (sizes only). No hashing, no network. A development record written by plan A's `scripts/dev_engine.py` (`"tier": "development"`) counts as installed when its Python, its worker and the model are there, so development keeps working.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_core.py`:

```python
"""bootstrap.py orchestration with a scripted stage table (the real stages come in tasks 9-12)."""
import json
import threading

import pytest

from owlocr import paths
from owlocr.engine import bootstrap, stages
from owlocr.engine import install_kit as kit
from owlocr.engine.bootstrap import STAGES, BootstrapError, StageEvent
from owlocr.engine.install_kit import Deps
from owlocr.hardware import tier_by_name

CPU = tier_by_name("cpu")


class Script:
    """Every stage is 'done' once its action ran; `done_before` marks stages already finished."""

    def __init__(self, done_before=(), fail=None, cancel_at=None, cancel=None):
        self.done = set(done_before)
        self.actions = []
        self.fail, self.cancel_at, self.cancel = fail, cancel_at, cancel

    def check(self, name):
        return lambda ctx: name in self.done

    def action(self, name):
        def run(ctx):
            self.actions.append(name)
            ctx.report(done=5, total=10, message=f"{name} halfway")
            if name == self.fail:
                raise BootstrapError(f"command_failed: {name} broke")
            if name == self.cancel_at:
                self.cancel.set()
                return
            if name == "mark":
                paths.atomic_write_text(kit.install_file(), "{}")
            self.done.add(name)
        return run


@pytest.fixture
def script(monkeypatch):
    def install(**kw):
        s = Script(**kw)
        monkeypatch.setattr(stages, "CHECKS", {n: s.check(n) for n in STAGES})
        monkeypatch.setattr(stages, "ACTIONS", {n: s.action(n) for n in STAGES})
        return s
    return install


def deps(free=100 * 1024**3):
    return Deps(pins={"uv": {"version": "0", "url": "https://x", "sha256": "0" * 64}}, free_bytes=lambda p: free)


def run(tier=CPU, cancel=None, free=100 * 1024**3):
    events = []
    bootstrap._run(tier, events.append, cancel, deps(free))
    return events


def test_contract_names():
    assert STAGES == ("tools", "python", "venv", "torch", "deps", "model", "worker", "patch", "selftest", "mark")
    assert StageEvent("tools", "start", 0, 0, "").state == "start"
    assert bootstrap.install_path() == paths.engine_dir() / "install.json"


def test_runs_every_stage_in_order(script):
    s = script()
    events = run()
    assert s.actions == list(STAGES)
    assert [(e.stage, e.state) for e in events[:3]] == [("tools", "start"), ("tools", "progress"), ("tools", "done")]
    assert events[1].message == "tools halfway" and (events[1].done, events[1].total) == (5, 10)
    assert not bootstrap.was_interrupted()
    assert "=== installation finished" in (paths.logs_dir() / "install.log").read_text(encoding="utf-8")


def test_finished_stages_are_skipped(script):
    s = script(done_before=("tools", "python", "venv"))
    events = run()
    assert s.actions == list(STAGES[3:])
    assert [e.state for e in events if e.stage == "python"] == ["start", "skipped"]


def test_failure_stops_and_is_reported(script):
    s = script(fail="deps")
    events = []
    with pytest.raises(BootstrapError, match="command_failed: deps broke"):
        bootstrap._run(CPU, events.append, None, deps())
    assert s.actions == ["tools", "python", "venv", "torch", "deps"]
    assert (events[-1].stage, events[-1].state) == ("deps", "failed")
    assert bootstrap.was_interrupted()
    assert "stage deps failed" in (paths.logs_dir() / "install.log").read_text(encoding="utf-8")


def test_unexpected_exception_becomes_internal_error(script, monkeypatch):
    script()

    def boom(ctx):
        raise KeyError("oops")

    monkeypatch.setitem(stages.ACTIONS, "venv", boom)
    with pytest.raises(BootstrapError, match="internal: KeyError"):
        run()
    assert "Traceback" in (paths.logs_dir() / "install.log").read_text(encoding="utf-8")


def test_cancel_between_stages(script):
    cancel = threading.Event()
    s = script(cancel_at="torch", cancel=cancel)
    events = []
    with pytest.raises(BootstrapError, match="^cancelled$"):
        bootstrap._run(CPU, events.append, cancel, deps())
    assert s.actions == ["tools", "python", "venv", "torch"]
    assert (events[-1].stage, events[-1].state, events[-1].message) == ("torch", "failed", "cancelled")


def test_a_stage_whose_check_still_fails_is_an_error(script, monkeypatch):
    script()
    monkeypatch.setitem(stages.ACTIONS, "python", lambda ctx: None)
    with pytest.raises(BootstrapError, match="check_failed: the python stage"):
        run()


def test_not_enough_space(script):
    script()
    with pytest.raises(BootstrapError, match="not_enough_space"):
        run(free=1024)
    assert not bootstrap.was_interrupted()


def test_space_already_used_by_the_engine_counts(script, monkeypatch):
    script()
    monkeypatch.setattr(kit, "dir_size", lambda path: 15 * 1024**3 if path == paths.model_dir() else 0)
    run(free=2 * 1024**3)                          # 16 GB - 15 GB already present = 1 GB needed


def test_unsupported_tier(script):
    script()
    with pytest.raises(BootstrapError, match="unsupported: ram_too_small"):
        run(tier_by_name("unsupported", "ram_too_small"))


def test_one_installation_at_a_time(script, monkeypatch):
    script()
    started, release = threading.Event(), threading.Event()

    def slow(ctx):
        started.set()
        release.wait(10)

    monkeypatch.setitem(stages.ACTIONS, "tools", slow)
    worker = threading.Thread(target=lambda: pytest.raises(BootstrapError, run))
    worker.start()
    started.wait(10)
    with pytest.raises(BootstrapError, match="already_running"):
        run()
    with pytest.raises(BootstrapError, match="already_running"):
        bootstrap.remove_engine()
    release.set()
    worker.join(10)


def test_read_install(script):
    assert bootstrap.read_install() is None
    kit.install_file().parent.mkdir(parents=True, exist_ok=True)
    kit.install_file().write_text("{broken", encoding="utf-8")
    assert bootstrap.read_install() is None
    kit.install_file().write_text(json.dumps({"tier": "cpu"}), encoding="utf-8")
    assert bootstrap.read_install() == {"tier": "cpu"}


def test_load_pins_rejects_a_missing_or_incomplete_file(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "resource_path", lambda rel: tmp_path / rel)
    with pytest.raises(BootstrapError, match="pins.json"):
        bootstrap.load_pins()
    (tmp_path / "owlocr" / "engine").mkdir(parents=True)
    (tmp_path / "owlocr" / "engine" / "pins.json").write_text(
        json.dumps({"uv": {"version": "0.12.19", "url": "https://github.com/x.zip", "sha256": "ab"}}), encoding="utf-8")
    with pytest.raises(BootstrapError, match="incomplete uv pin"):
        bootstrap.load_pins()


def test_required_free_bytes():
    assert bootstrap.REQUIRED_FREE_BYTES == 16 * 1024**3
    assert bootstrap.required_free_bytes(0) == 16 * 1024**3
    assert bootstrap.required_free_bytes(20 * 1024**3) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_bootstrap_core.py -q`
Expected: collection error `ImportError: cannot import name 'bootstrap' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/stages.py` as a skeleton (Task 9 replaces it):

```python
"""The ten stages of the engine installation (design 6.2): one check and one action each."""
from __future__ import annotations

from typing import Callable

from owlocr.engine.install_kit import StageContext

# Filled stage by stage in tasks 9-12: name -> check, name -> action.
CHECKS: dict[str, Callable[[StageContext], bool]] = {}
ACTIONS: dict[str, Callable[[StageContext], None]] = {}
```

Create `owlocr/engine/bootstrap.py`:

```python
"""One-time installation of the OCR engine (design 6.2 and 6.3).

`run()` walks the STAGES in order. Every stage has its own check and is skipped when the check
passes, so an interrupted installation continues where it stopped. The stages live in
`owlocr/engine/stages.py`, their building blocks in `owlocr/engine/install_kit.py`; this module
holds the public API of the interface contract.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import registry, stages, store
from owlocr.engine.install_kit import BootstrapError, Deps, StageContext
from owlocr.hardware import Tier

__all__ = ["STAGES", "StageEvent", "install_path", "is_installed", "read_install", "run",
           "remove_engine", "reset_install", "sync_worker_files", "was_interrupted",
           "required_free_bytes", "BootstrapError"]

STAGES = ("tools", "python", "venv", "torch", "deps", "model", "worker", "patch", "selftest", "mark")
REQUIRED_FREE_BYTES = 16 * 1024**3        # design 6.3 rule 6
PINS_REL = "owlocr/engine/pins.json"

_RUN_LOCK = threading.Lock()


@dataclass
class StageEvent:
    stage: str
    state: str      # 'start' | 'progress' | 'done' | 'skipped' | 'failed'
    done: int
    total: int
    message: str


def install_path() -> Path:
    return kit.install_file()


def read_install() -> dict | None:
    return kit.read_json(install_path())


def is_installed() -> bool:
    """install.json matches the app's pins and the model passes the fast readiness check.
    A development record written by plan A's scripts/dev_engine.py (tier "development") counts
    as installed when its Python and worker exist and the model is ready."""
    record = read_install()
    if not record:
        return False
    if record.get("tier") == "development":
        python = Path(record.get("python") or paths.engine_python())
        worker = Path(record.get("worker_script") or paths.worker_dir() / "owl_worker.py")
        return python.is_file() and worker.is_file() and store.is_ready()
    spec = registry.UNLIMITED_OCR
    expected = {
        "format": kit.INSTALL_FORMAT, "python_version": kit.PYTHON_VERSION, "engine_id": spec.engine_id,
        "revision": spec.revision, "torch": spec.torch, "torchvision": spec.torchvision,
        "transformers": spec.transformers,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        return False
    try:
        if record.get("requirements_sha256") != kit.requirements_sha256():
            return False
    except OSError:
        return False
    if not paths.engine_python().is_file() or not kit.venv_home_ok():
        return False
    return store.is_ready()


def was_interrupted() -> bool:
    """True when an installation was started and has not finished (resume after restart)."""
    return kit.state_file().exists()


def load_pins() -> dict:
    pins_file = paths.resource_path(PINS_REL)
    try:
        pins = json.loads(pins_file.read_text(encoding="utf-8"))
        uv = pins["uv"]
        if len(uv["sha256"]) != 64 or not uv["url"].startswith("https://") or not uv["version"]:
            raise ValueError("incomplete uv pin")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BootstrapError(f"internal: {pins_file} is missing or invalid: {exc}") from exc
    return pins


def required_free_bytes(already_present: int) -> int:
    return max(0, REQUIRED_FREE_BYTES - already_present)


class _InstallLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")


def run(tier: Tier, on_event: Callable[[StageEvent], None],
        cancel: threading.Event | None = None) -> None:
    _run(tier, on_event, cancel, Deps(pins=load_pins()))


def _run(tier: Tier, on_event: Callable[[StageEvent], None], cancel: threading.Event | None,
         deps: Deps) -> None:
    if tier.name == "unsupported":
        raise BootstrapError(f"unsupported: {tier.reason}")
    if not _RUN_LOCK.acquire(blocking=False):
        raise BootstrapError("already_running: an installation is already running")
    try:
        paths.engine_dir().mkdir(parents=True, exist_ok=True)
        log = _InstallLog(paths.logs_dir() / "install.log")
        log.write(f"=== Owl OCR engine installation, tier {tier.name}, {time.strftime('%Y-%m-%d %H:%M:%S')}")
        present = kit.dir_size(paths.engine_dir()) + kit.dir_size(paths.model_dir())
        need, free = required_free_bytes(present), deps.free_bytes(paths.data_root())
        if free < need:
            log.write(f"not enough space: {need} needed, {free} free")
            raise BootstrapError(f"not_enough_space: {need} bytes needed on the data drive, {free} free")
        paths.atomic_write_text(kit.state_file(), json.dumps({"tier": tier.name, "started": time.time()}))
        for stage in STAGES:
            _run_stage(stage, tier, deps, cancel, on_event, log)
        kit.state_file().unlink(missing_ok=True)
        log.write("=== installation finished")
    finally:
        _RUN_LOCK.release()


def _run_stage(stage: str, tier: Tier, deps: Deps, cancel: threading.Event | None,
               on_event: Callable[[StageEvent], None], log: _InstallLog) -> None:
    ctx = StageContext(tier, deps, cancel,
                       lambda d, t, m: on_event(StageEvent(stage, "progress", d, t, m)), log.write)

    def fail(message: str) -> None:
        log.write(f"--- stage {stage} failed: {message}")
        on_event(StageEvent(stage, "failed", ctx.done, ctx.total, message))

    if ctx.cancelled():
        fail("cancelled")
        raise BootstrapError("cancelled")
    log.write(f"--- stage {stage}")
    on_event(StageEvent(stage, "start", 0, 0, "checking"))
    try:
        if stages.CHECKS[stage](ctx):
            log.write(f"--- stage {stage} already done, skipped")
            on_event(StageEvent(stage, "skipped", 0, 0, ""))
            return
        stages.ACTIONS[stage](ctx)
        if ctx.cancelled():
            raise BootstrapError("cancelled")
        if not stages.CHECKS[stage](ctx):
            raise BootstrapError(f"check_failed: the {stage} stage finished but its check does not pass")
    except BootstrapError as exc:
        fail(str(exc))
        raise
    except Exception as exc:
        log.write(traceback.format_exc())
        fail(f"internal: {type(exc).__name__}: {exc}")
        raise BootstrapError(f"internal: {type(exc).__name__}: {exc}") from exc
    log.write(f"--- stage {stage} done")
    on_event(StageEvent(stage, "done", ctx.done, ctx.total, ctx.message))


def remove_engine() -> None:
    """Deletes the engine runtime, the model and the Hugging Face caches. The queue stays."""
    if _RUN_LOCK.locked():
        raise BootstrapError("already_running: an installation is running")
    for folder in (paths.engine_dir(), paths.model_dir(), paths.hf_home()):
        kit.rmtree(folder)


def reset_install() -> None:
    """For 'Reinstall': forgets what was installed and rebuilds the venv. Downloads are kept
    (uv cache, Python, intact model files), so a reinstall downloads only damaged model files."""
    if _RUN_LOCK.locked():
        raise BootstrapError("already_running: an installation is running")
    model = paths.model_dir().resolve()
    problems = store.verify() if store.manifest_path().exists() else {}
    for rel in problems:
        damaged = (model / rel).resolve()
        if damaged.is_relative_to(model) and damaged.is_file():
            damaged.unlink()
    if problems:
        store.manifest_path().unlink(missing_ok=True)      # the model stage downloads them again
    install_path().unlink(missing_ok=True)
    for name in ("deps", "selftest"):
        (kit.stamps_dir() / f"{name}.json").unlink(missing_ok=True)
    kit.rmtree(kit.venv_dir())


def sync_worker_files() -> bool:
    """Copies the app's worker scripts into an installed engine when they differ.
    Returns True when something was copied. Called once when the server starts."""
    if not paths.worker_dir().is_dir():
        return False
    copied = False
    for name in kit.WORKER_FILES:
        src, dst = paths.resource_path(f"worker/{name}"), paths.worker_dir() / name
        if src.is_file() and (not dst.is_file() or dst.read_bytes() != src.read_bytes()):
            kit.copy_atomic(src, dst)
            copied = True
    return copied
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_bootstrap_core.py -q`
Expected: `14 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/bootstrap.py owlocr/engine/stages.py tests/test_bootstrap_core.py
git commit -m "Add engine installer orchestration, install record and readiness check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Stages tools, python and venv

**Files:**
- Modify: `owlocr/engine/stages.py` (replace the skeleton)
- Create: `tests/install_fakes.py`
- Test: `tests/test_stages.py`

**Interfaces:**
- Consumes: `install_kit` helpers; `Deps.pins["uv"]` from `pins.json`; `Deps.download_file`, `Deps.run_cmd`.
- Produces: `check_tools`, `do_tools`, `check_python`, `do_python`, `check_venv`, `do_venv`, registered in `CHECKS` / `ACTIONS`. `tests/install_fakes.py`: `FakeTools` (plays uv, the managed and the venv Python, `device_patch.py`, the store and the engine; records every call), `FakeEngine`, `make_resources(root)`, `UV_ZIP`, `UV_PINS`, `LETTER`, `collect_events()`.

Stage rules (design 6.2):
- **tools**: download the pinned archive to `engine\tools\uv.zip` (resumable), compare its sha256 with `pins.json` (a mismatch deletes the archive and fails with `checksum_mismatch`), extract only `uv.exe`, write the stamp `stamps\tools.json` = version and sha256. Check: `uv.exe` exists and the stamp equals the pin.
- **python**: `uv python install 3.11 --no-bin --no-registry` with `UV_PYTHON_INSTALL_DIR=<engine>\python` (nothing is added to the user's PATH or registry). Check: `python\cpython-3.11.*\python.exe --version` prints `Python 3.11.`.
- **venv**: delete any old venv, then `uv venv --python <managed python.exe> --no-project <engine>\venv`. Check: `venv\Scripts\python.exe` runs as 3.11 and `pyvenv.cfg` points into `engine\python` (after a move of the data root it does not, so the venv is rebuilt without any download).

- [ ] **Step 1: Write the failing test**

Create `tests/install_fakes.py`:

```python
"""Fakes for testing the engine installer without uv, Python downloads, torch or the model."""
from __future__ import annotations

import hashlib
import io
import json
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
            (folder / "python.exe").write_bytes(b"")
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
```

Create `tests/test_stages.py`:

```python
import json
from types import SimpleNamespace

import pytest

from tests.install_fakes import LETTER, FakeTools, make_resources
from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import stages
from owlocr.engine.install_kit import BootstrapError, StageContext
from owlocr.hardware import tier_by_name

CPU = tier_by_name("cpu")
GPU = tier_by_name("gpu_full")


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    fake = FakeTools(make_resources(tmp_path / "res"))
    monkeypatch.setattr(paths, "resource_path", lambda rel: fake.resources / rel)
    return fake


def ctx(tools, tier=CPU, deps=None):
    return StageContext(tier, deps or tools.deps_for_test(), None, lambda d, t, m: None, lambda line: None)


def run(tools, names, tier=CPU):
    """Runs the given stages the way bootstrap does: action only when the check fails."""
    c = ctx(tools, tier)
    for name in names:
        if not stages.CHECKS[name](c):
            stages.ACTIONS[name](c)
        assert stages.CHECKS[name](c), name
    return c


# ---- tools, python, venv -------------------------------------------------------------

def test_tools_downloads_verifies_and_extracts_uv(tools):
    run(tools, ["tools"])
    assert kit.uv_exe().read_bytes() == b"fake uv binary"
    assert not (kit.uv_exe().parent / "uv.zip").exists()
    assert kit.read_stamp("tools")["version"] == "0.0.0-test"


def test_tools_check_needs_the_pinned_version(tools):
    run(tools, ["tools"])
    deps = tools.deps_for_test()
    deps.pins["uv"]["version"] = "9.9.9"
    assert not stages.check_tools(ctx(tools, deps=deps))


def test_tools_refuses_a_wrong_checksum(tools):
    deps = tools.deps_for_test()
    deps.pins["uv"]["sha256"] = "f" * 64
    with pytest.raises(BootstrapError, match="checksum_mismatch"):
        stages.do_tools(ctx(tools, deps=deps))
    assert not kit.uv_exe().exists()


def test_python_and_venv(tools):
    run(tools, ["tools", "python", "venv"])
    assert tools.uv_calls()[0] == ["python", "install", "3.11", "--no-bin", "--no-registry"]
    assert paths.engine_python().is_file() and kit.venv_home_ok()


def test_venv_is_rebuilt_when_its_python_moved(tools):
    run(tools, ["tools", "python", "venv"])
    (kit.venv_dir() / "pyvenv.cfg").write_text("home = D:\\old\\python\n", encoding="utf-8")
    assert not stages.check_venv(ctx(tools))
    run(tools, ["venv"])
    assert kit.venv_home_ok()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `5 failed`, each with `KeyError: 'tools'` (or `AttributeError: module 'owlocr.engine.stages' has no attribute 'do_tools'`).

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `owlocr/engine/stages.py` with:

```python
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
    requirements_sha256, rmtree, run_tool, torch_flavor, uv_cache_dir, uv_exe, venv_dir,
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

def check_python(ctx: StageContext) -> bool:
    exe = managed_python()
    return exe is not None and python_is_311(ctx, exe)


def do_python(ctx: StageContext) -> None:
    run_tool(ctx, [uv_exe(), "python", "install", PYTHON_VERSION, "--no-bin", "--no-registry"])


# ---------------------------------------------------------------- stage: venv

def check_venv(ctx: StageContext) -> bool:
    exe = paths.engine_python()
    return exe.is_file() and venv_home_ok() and python_is_311(ctx, exe)


def do_venv(ctx: StageContext) -> None:
    base = managed_python()
    if base is None:
        raise BootstrapError("check_failed: the managed Python 3.11 is missing")
    rmtree(venv_dir())
    run_tool(ctx, [uv_exe(), "venv", "--python", base, "--no-project", venv_dir()])


CHECKS.update(tools=check_tools, python=check_python, venv=check_venv)
ACTIONS.update(tools=do_tools, python=do_python, venv=do_venv)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_stages.py tests/test_bootstrap_core.py -q`
Expected: `19 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/stages.py tests/install_fakes.py tests/test_stages.py
git commit -m "Add installer stages for uv, Python 3.11 and the venv" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Stages torch and deps

**Files:**
- Modify: `owlocr/engine/stages.py` (append)
- Test: `tests/test_stages.py` (append)

**Interfaces:**
- Consumes: `Tier.torch_index`, `registry.UNLIMITED_OCR.torch`, `.torchvision`, `.transformers`; plan A's `worker/requirements-engine.txt` (unchanged: transformers 4.57.1, tokenizers, huggingface_hub, safetensors, accelerate, Pillow, einops, addict, easydict, matplotlib, psutil, numpy, requests, tqdm).
- Produces: `installed_torch(ctx) -> tuple[str, str] | None`, `check_torch`, `do_torch`, `DEPS_IMPORT_TEST`, `check_deps`, `do_deps`, registered.

Stage rules:
- **torch**: `uv pip install --python <venv python> torch==2.10.0 torchvision==0.25.0 --index-url <tier.torch_index>`. Progress: uv prints no byte counts when it is not attached to a console, so the stage reports how much the uv cache grew against the known wheel sizes (2,876,740,161 bytes for cu128, 117,675,311 for cpu). Check: the venv imports torch and torchvision with exactly `2.10.0+<flavour>` and `0.25.0+<flavour>`, where the flavour is the last part of the index URL (`cu128`, `cpu`), so a tier change reinstalls torch.
- **deps**: `uv pip install --python <venv python> -r worker\requirements-engine.txt`, then the stamp `stamps\deps.json` with the sha256 of the requirements file. Check: the stamp matches the bundled file, all engine imports work with transformers `4.57.1`, and torch is still the right build (a dependency must never replace it).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stages.py`:

```python
# ---- torch, deps ---------------------------------------------------------------------

def test_torch_from_the_tier_index(tools):
    run(tools, ["tools", "python", "venv", "torch"], GPU)
    assert tools.uv_calls()[-1][-2:] == ["--index-url", "https://download.pytorch.org/whl/cu128"]


def test_torch_of_the_wrong_flavour_is_replaced(tools):
    run(tools, ["tools", "python", "venv", "torch"], GPU)
    assert not stages.check_torch(ctx(tools, CPU))
    run(tools, ["torch"], CPU)
    assert tools.torch == "cpu"


def test_deps_install_and_stamp(tools):
    run(tools, ["tools", "python", "venv", "torch", "deps"])
    assert kit.read_stamp("deps")["requirements_sha256"] == kit.requirements_sha256(tools.deps_for_test().resource)


def test_deps_run_again_when_requirements_change(tools):
    run(tools, ["tools", "python", "venv", "torch", "deps"])
    (tools.resources / "worker" / "requirements-engine.txt").write_text("transformers==4.57.1\neinops==0.8.2\n",
                                                                        encoding="utf-8")
    assert not stages.check_deps(ctx(tools))


def test_deps_check_fails_if_torch_was_replaced(tools):
    run(tools, ["tools", "python", "venv", "torch", "deps"])
    tools.torch = "cu130"
    assert not stages.check_deps(ctx(tools))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `5 failed` (the new tests: `KeyError: 'torch'` or missing `check_torch` / `check_deps`), `5 passed`.

- [ ] **Step 3: Write minimal implementation**

Append to `owlocr/engine/stages.py`:

```python
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
    """Reports download progress of torch by watching the uv cache grow."""

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
    run_tool(ctx, [uv_exe(), "pip", "install", "--python", paths.engine_python(),
                   "-r", ctx.deps.resource(REQUIREMENTS_REL)])
    write_stamp("deps", {"requirements_sha256": requirements_sha256(ctx.deps.resource)})


CHECKS.update(torch=check_torch, deps=check_deps)
ACTIONS.update(torch=do_torch, deps=do_deps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/stages.py tests/test_stages.py
git commit -m "Add installer stages for torch and the engine dependencies" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Stages model, worker and patch

**Files:**
- Modify: `owlocr/engine/stages.py` (append)
- Test: `tests/test_stages.py` (append)

**Interfaces:**
- Consumes: `store.download(spec, on_progress, cancel)` through `Deps.store_download` (progress in bytes; raises `StoreError("cancelled")` on cancel), `store.is_ready()` through `Deps.store_is_ready`; the bundled `worker/owl_worker.py`, `worker/device_patch.py`, `licenses/Apache-2.0.txt` through `Deps.resource`.
- Produces: `check_model`, `do_model`, `check_worker`, `do_worker`, `model_is_patched() -> bool`, `check_patch`, `do_patch`, registered.

Stage rules:
- **model**: delegate to `store.download` (resumable; manifest written last). Check: `store.is_ready()`. A folder adopted through "I already have the engine" is already ready, so nothing is downloaded.
- **worker**: copy `owl_worker.py` and `device_patch.py` byte for byte into `<engine>\worker\` (never modified: the worker's stdin detach must survive), copy the Apache text into the model folder as `LICENSE-Apache-2.0.txt` and write `NOTICE-OwlOCR.txt` there. Check: the copies equal the bundled files and the notice is current.
- **patch**: on the CPU tier run `device_patch.py --model-dir <model> --device cpu --dtype float32` with the engine's Python; on GPU tiers, if a patch from an earlier CPU installation is present, run it with `--restore`. Exit code 2 is `patch_refused` (upstream code changed; nothing was modified). Check: the sentinel is present exactly when the tier's device is `cpu`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stages.py`:

```python
# ---- model, worker, patch ------------------------------------------------------------

def test_model_uses_the_store(tools):
    run(tools, ["model"])
    assert tools.model and (paths.model_dir() / "manifest.json").exists()


def test_model_download_failure(tools):
    from owlocr.engine import store

    deps = tools.deps_for_test()

    def fail(on_progress, cancel):
        raise store.StoreError("both sources failed")

    deps.store_download = fail
    with pytest.raises(BootstrapError, match="model_download_failed: both sources failed"):
        stages.do_model(ctx(tools, deps=deps))


def test_worker_copies_scripts_and_licence_files(tools):
    run(tools, ["model", "worker"])
    assert (paths.worker_dir() / "owl_worker.py").read_text(encoding="utf-8") == "# fake worker\n"
    assert (paths.worker_dir() / "device_patch.py").exists()
    assert (paths.model_dir() / "LICENSE-Apache-2.0.txt").read_text(encoding="utf-8").startswith("Apache License")
    assert "modeling_deepseekv2.py" in (paths.model_dir() / "NOTICE-OwlOCR.txt").read_text(encoding="utf-8")


def test_worker_detects_an_outdated_copy(tools):
    run(tools, ["model", "worker"])
    (tools.resources / "worker" / "owl_worker.py").write_text("# v2\n", encoding="utf-8")
    assert not stages.check_worker(ctx(tools))


def test_patch_on_cpu_and_restore_on_gpu(tools):
    run(tools, ["tools", "python", "venv", "model", "worker", "patch"], CPU)
    assert stages.model_is_patched()
    call = [c for c in tools.calls if c[1].endswith("device_patch.py")][-1]
    assert call[-4:] == ["--device", "cpu", "--dtype", "float32"]
    run(tools, ["patch"], GPU)
    assert not stages.model_is_patched()


def test_patch_is_not_run_on_gpu_when_the_model_is_pristine(tools):
    run(tools, ["tools", "python", "venv", "model", "worker", "patch"], GPU)
    assert not any(c[1].endswith("device_patch.py") for c in tools.calls)


def test_refused_patch(tools):
    run(tools, ["tools", "python", "venv", "model", "worker"])
    tools.patch_code = 2
    with pytest.raises(BootstrapError, match="patch_refused: REFUSED"):
        stages.do_patch(ctx(tools))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `7 failed` (the new tests: `KeyError: 'model'`, missing `do_model`, `do_patch`, `model_is_patched`), `10 passed`.

- [ ] **Step 3: Write minimal implementation**

Append to `owlocr/engine/stages.py`:

```python
# ---------------------------------------------------------------- stage: model

def check_model(ctx: StageContext) -> bool:
    return bool(ctx.deps.store_is_ready())


def do_model(ctx: StageContext) -> None:
    try:
        ctx.deps.store_download(lambda d, t: ctx.report(done=d, total=t), ctx.cancel)
    except store.StoreError as exc:
        if ctx.cancelled():
            raise BootstrapError("cancelled") from exc
        raise BootstrapError(f"model_download_failed: {exc}") from exc
    if ctx.cancelled():
        raise BootstrapError("cancelled")


# ---------------------------------------------------------------- stage: worker

def _worker_pairs(ctx_resource: Callable[[str], Path]) -> list[tuple[Path, Path]]:
    pairs = [(ctx_resource(f"worker/{n}"), paths.worker_dir() / n) for n in WORKER_FILES]
    pairs.append((ctx_resource(APACHE_REL), paths.model_dir() / APACHE_NAME))
    return pairs


def check_worker(ctx: StageContext) -> bool:
    for src, dst in _worker_pairs(ctx.deps.resource):
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            return False
    notice = paths.model_dir() / NOTICE_NAME
    return notice.is_file() and notice.read_text(encoding="utf-8") == MODEL_NOTICE


def do_worker(ctx: StageContext) -> None:
    for src, dst in _worker_pairs(ctx.deps.resource):
        copy_atomic(src, dst)
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
    args = [paths.engine_python(), paths.worker_dir() / "device_patch.py", "--model-dir", paths.model_dir()]
    if ctx.tier.device == "cpu":
        args += ["--device", ctx.tier.device, "--dtype", ctx.tier.dtype]
    else:
        args += ["--restore"]
    lines: list[str] = []
    ctx.log("$ " + " ".join(str(a) for a in args))
    code = ctx.deps.run_cmd([str(a) for a in args], clean_env(), lambda s: (lines.append(s), ctx.log(s)), ctx.cancel)
    last = next((line for line in reversed(lines) if line.strip()), "")
    if code == 2:
        raise BootstrapError(f"patch_refused: {last}")
    if code != 0:
        raise BootstrapError(f"command_failed: device_patch.py exited with {code}: {last}")


CHECKS.update(model=check_model, worker=check_worker, patch=check_patch)
ACTIONS.update(model=do_model, worker=do_worker, patch=do_patch)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/stages.py tests/test_stages.py
git commit -m "Add installer stages for the model, the worker scripts and the device patch" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Stages selftest and mark

**Files:**
- Modify: `owlocr/engine/stages.py` (append)
- Test: `tests/test_stages.py` (append)

**Interfaces:**
- Consumes: plan A's `SubprocessEngine` through `Deps.engine_factory` (`start()`, `load()`, `ocr_page(image, mode, max_new_tokens, time_limit_s, on_progress, cancel) -> PageResult`, `stop()`), `EngineError`, `hardware.REQUIRED_FREE_VRAM_MIB`, `Deps.free_vram` (plan A's `free_vram_mib`), `settings.get`, `settings.update`, `settings.DEFAULTS`.
- Produces: `fingerprint(ctx) -> str`, `selftest_words_found(text) -> list[str]`, `check_selftest`, `do_selftest`, `check_mark`, `do_mark`, registered. `install.json` keys: `format`, `fingerprint`, `tier`, `device`, `dtype`, `default_mode`, `torch_index`, `python_version`, `uv`, `engine_id`, `revision`, `torch`, `torchvision`, `transformers`, `requirements_sha256`, `patched`, `selftest_seconds`, `app_version`, `installed_at`. There is deliberately **no** `python` key: plan A's `default_engine()` reads `python` as the path of the engine interpreter and falls back to `engine_python()` when it is absent.

Stage rules:
- **selftest**: on a GPU tier first check free VRAM (9,500 MiB for Quality, 7,500 for Fast; less fails with `not_enough_vram` and the missing amount). Start the engine through plan A's `SubprocessEngine` (so the Job Object protects the installation too), load, read `owlocr/web/static/selftest.png` (the generated letter page) in the tier's default mode with at most 1,500 new tokens and a time limit of 180 s on the GPU or 1,800 s on the processor, and always stop the engine afterwards, also on errors. Pass: at least 3 of the words `Vážená`, `doktorko`, `lékařské`, `Dvořáka`, `rehabilitaci` appear. The stamp `stamps\selftest.json` stores the fingerprint (tier, device, dtype, index, Python, revision, versions, requirements hash) and the seconds; a different tier or pin runs the self-test again.
- **mark**: write `install.json` (last, design 6.3 rule 2). On the first installation set `mode_default` to the tier's default mode, unless the user already changed it from `DEFAULTS["mode_default"]`. Check: `install.json` carries the current fingerprint.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stages.py`:

```python
# ---- selftest, mark ------------------------------------------------------------------

ALL_BUT_LAST = ["tools", "python", "venv", "torch", "deps", "model", "worker", "patch"]


def test_selftest_reads_the_page_and_stops_the_engine(tools):
    run(tools, ALL_BUT_LAST + ["selftest"])
    assert tools.ocr_calls == [("selftest.png", "fast", 1500, 1800.0)]
    assert tools.engines[0].stopped
    stamp = kit.read_stamp("selftest")
    assert stamp["ok"] is True and stamp["seconds"] == 12.3 and stamp["words_found"] == 5


def test_selftest_stops_the_engine_when_reading_fails(tools):
    from owlocr.engine.protocol import EngineError

    run(tools, ALL_BUT_LAST)
    deps = tools.deps_for_test()
    engine = SimpleNamespace(stopped=False)
    engine.start = lambda: None
    engine.load = lambda: 0.1

    def crash(*a, **k):
        raise EngineError("died")

    engine.ocr_page = crash
    engine.stop = lambda timeout_s=5.0: setattr(engine, "stopped", True)
    deps.engine_factory = lambda tier: engine
    with pytest.raises(BootstrapError, match="selftest_failed"):
        stages.do_selftest(ctx(tools, deps=deps))
    assert engine.stopped


def test_selftest_needs_free_vram_on_gpu(tools):
    run(tools, ALL_BUT_LAST, GPU)
    tools.free_vram = 9000                    # Quality needs 9500
    with pytest.raises(BootstrapError, match="not_enough_vram: 9500 MiB"):
        stages.do_selftest(ctx(tools, GPU))
    assert tools.engines == []


def test_selftest_rejects_output_without_the_words(tools):
    run(tools, ALL_BUT_LAST)
    tools.ocr_text = "<|det|>image [0, 0, 999, 999]<|/det|>"
    with pytest.raises(BootstrapError, match="selftest_failed: expected words"):
        stages.do_selftest(ctx(tools))


def test_selftest_runs_again_for_another_tier(tools):
    run(tools, ALL_BUT_LAST + ["selftest"], CPU)
    assert not stages.check_selftest(ctx(tools, GPU))


def test_mark_writes_install_json(tools):
    run(tools, ALL_BUT_LAST + ["selftest", "mark"], CPU)
    record = json.loads(kit.install_file().read_text(encoding="utf-8"))
    assert record["tier"] == "cpu" and record["patched"] is True and record["selftest_seconds"] == 12.3
    assert record["fingerprint"] == stages.fingerprint(ctx(tools, CPU))


def test_selftest_word_matching():
    assert stages.selftest_words_found(LETTER) == list(kit.SELFTEST_WORDS)
    assert stages.selftest_words_found("VÁŽENÁ paní DOKTORKO") == ["Vážená", "doktorko"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_stages.py -q`
Expected: `7 failed` (the new tests: `KeyError: 'selftest'`, missing `do_selftest`, `fingerprint`, `selftest_words_found`), `17 passed`.

- [ ] **Step 3: Write minimal implementation**

Append to `owlocr/engine/stages.py`:

```python
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
        raise BootstrapError(f"selftest_failed: {getattr(exc, 'kind', 'internal')}: {exc}") from exc
    finally:
        engine.stop()
    if result.cancelled or ctx.cancelled():
        raise BootstrapError("cancelled")
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
        # Design 10.3: the default mode follows the tier, unless the user already changed it.
        if first_install and settings.get("mode_default") == settings.DEFAULTS["mode_default"]:
            settings.update({"mode_default": ctx.tier.default_mode})
    except Exception as exc:            # a settings problem must not undo a finished installation
        ctx.log(f"could not set mode_default: {exc}")


CHECKS.update(selftest=check_selftest, mark=check_mark)
ACTIONS.update(selftest=do_selftest, mark=do_mark)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_stages.py tests/test_bootstrap_core.py -q`
Expected: `38 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/stages.py tests/test_stages.py
git commit -m "Add the self-test and install record stages" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Whole installations end to end

**Files:**
- Test: `tests/test_bootstrap_e2e.py`

**Interfaces:**
- Consumes: `bootstrap._run`, `is_installed`, `read_install`, `remove_engine`, `reset_install`, `sync_worker_files`, `was_interrupted`; `tests/install_fakes.py`.
- Produces: tests only. They pin the behaviour of design 6.2 and 6.3: a fresh CPU and a fresh GPU installation, a second run that skips every stage and runs no installer command, a switch from CPU to GPU that restores the pristine model code and replaces torch, a checksum failure, a failed command with its output in `install.log`, cancel during the torch download and resume after it without repeating finished stages, the mode default, a development record, `is_installed` after a moved venv or an unready model, remove, reinstall that downloads only damaged model files, and worker sync.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bootstrap_e2e.py`:

```python
import json
import threading
import time
from pathlib import Path

import pytest

from tests.install_fakes import FakeTools, UV_PINS, collect_events, make_resources
from owlocr import paths
from owlocr.engine import bootstrap, stages
from owlocr.engine import install_kit as kit
from owlocr.engine.bootstrap import STAGES, BootstrapError
from owlocr.hardware import tier_by_name

CPU = tier_by_name("cpu")
GPU = tier_by_name("gpu_full")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    return tmp_path / "data"


@pytest.fixture
def tools(tmp_path, home, monkeypatch):
    fake = FakeTools(make_resources(tmp_path / "res"))
    monkeypatch.setattr(paths, "resource_path", lambda rel: fake.resources / rel)
    return fake


def install(tools, tier=CPU, cancel=None):
    events, on_event = collect_events()
    bootstrap._run(tier, on_event, cancel, tools.deps_for_test())
    return events


def finals(events):
    """stage -> last state."""
    out = {}
    for ev in events:
        out[ev.stage] = ev.state
    return out


def test_fresh_cpu_install_runs_every_stage(tools, home):
    events = install(tools)
    assert finals(events) == {s: "done" for s in STAGES}
    assert [e.stage for e in events if e.state == "done"] == list(STAGES)
    assert (home / "engine" / "tools" / "uv.exe").read_bytes() == b"fake uv binary"
    uv = tools.uv_calls()
    assert uv[0] == ["python", "install", "3.11", "--no-bin", "--no-registry"]
    assert uv[1][:3] == ["venv", "--python", str(kit.managed_python())]
    assert "--no-project" in uv[1] and uv[1][-1] == str(kit.venv_dir())
    assert uv[2] == ["pip", "install", "--python", str(paths.engine_python()), "torch==2.10.0",
                     "torchvision==0.25.0", "--index-url", "https://download.pytorch.org/whl/cpu"]
    assert uv[3] == ["pip", "install", "--python", str(paths.engine_python()), "-r",
                     str(tools.resources / "worker" / "requirements-engine.txt")]
    patch_call = next(c for c in tools.calls if c[1].endswith("device_patch.py"))
    assert patch_call[-4:] == ["--device", "cpu", "--dtype", "float32"]
    assert tools.ocr_calls == [("selftest.png", "fast", 1500, 1800.0)]
    assert all(e.stopped for e in tools.engines)


def test_install_json_and_files(tools, home):
    install(tools)
    record = json.loads((home / "engine" / "install.json").read_text(encoding="utf-8"))
    assert record["tier"] == "cpu" and record["device"] == "cpu" and record["dtype"] == "float32"
    assert record["torch_index"] == "https://download.pytorch.org/whl/cpu"
    assert (record["python_version"], record["torch"], record["torchvision"], record["transformers"]) == \
        ("3.11", "2.10.0", "0.25.0", "4.57.1")
    assert record["revision"] == "07dea832e22aefee32ad281d4b80551282e1c168"
    assert record["patched"] is True and record["selftest_seconds"] == 12.3
    assert record["uv"] == UV_PINS["uv"]["version"]
    assert record["engine_id"] == "unlimited_ocr" and "python" not in record   # plan A reads "python" as a path
    assert (paths.worker_dir() / "owl_worker.py").read_text(encoding="utf-8") == "# fake worker\n"
    assert (paths.model_dir() / "LICENSE-Apache-2.0.txt").is_file()
    assert "Apache License" in (paths.model_dir() / "NOTICE-OwlOCR.txt").read_text(encoding="utf-8")
    assert not bootstrap.was_interrupted()
    log = (home / "logs" / "install.log").read_text(encoding="utf-8")
    assert "Installed 14 packages" in log


def test_first_install_sets_default_mode_by_tier(tools):
    from owlocr import settings
    install(tools, CPU)
    assert settings.get("mode_default") == "fast"


def test_install_keeps_a_mode_the_user_chose(tools):
    from owlocr import settings
    settings.update({"mode_default": "fast"})
    install(tools, GPU)
    assert settings.get("mode_default") == "fast"


def test_development_record_counts_as_installed(tools, monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.store, "is_ready", lambda *a, **k: True)
    python, worker = tmp_path / "python.exe", tmp_path / "owl_worker.py"
    python.write_bytes(b"")
    worker.write_text("# worker", encoding="utf-8")
    bootstrap.install_path().parent.mkdir(parents=True, exist_ok=True)
    bootstrap.install_path().write_text(json.dumps({"tier": "development", "engine_id": "unlimited_ocr",
                                                    "python": str(python), "worker_script": str(worker),
                                                    "device": "cuda", "dtype": "bfloat16"}), encoding="utf-8")
    assert bootstrap.is_installed()
    python.unlink()
    assert not bootstrap.is_installed()


def test_second_run_skips_everything_and_runs_no_installer(tools):
    install(tools)
    tools.calls.clear()
    tools.downloads.clear()
    events = install(tools)
    assert finals(events) == {s: "skipped" for s in STAGES}
    assert tools.uv_calls() == []
    assert tools.downloads == []
    assert len(tools.engines) == 1          # the self-test did not run again


def test_gpu_tier_does_not_patch_and_uses_cu128(tools):
    events = install(tools, GPU)
    assert finals(events)["patch"] == "skipped"
    assert not any(c[1].endswith("device_patch.py") for c in tools.calls)
    assert "https://download.pytorch.org/whl/cu128" in tools.uv_calls()[2]
    assert tools.ocr_calls == [("selftest.png", "quality", 1500, 180.0)]


def test_switching_from_cpu_to_gpu_restores_the_model_code(tools):
    install(tools, CPU)
    events = install(tools, GPU)
    restore = [c for c in tools.calls if c[1].endswith("device_patch.py") and "--restore" in c]
    assert len(restore) == 1
    assert finals(events)["torch"] == "done"          # cu128 replaces the cpu build
    assert not stages.model_is_patched()


def test_uv_checksum_mismatch_fails_the_tools_stage(tools, home):
    deps = tools.deps_for_test()
    deps.pins["uv"]["sha256"] = "0" * 64
    events, on_event = collect_events()
    with pytest.raises(BootstrapError, match="checksum_mismatch"):
        bootstrap._run(CPU, on_event, None, deps)
    assert events[-1].stage == "tools" and events[-1].state == "failed"
    assert not (home / "engine" / "tools" / "uv.exe").exists()
    assert not (home / "engine" / "tools" / "uv.zip").exists()
    assert bootstrap.was_interrupted()


def test_failed_command_reports_exit_code_and_output(tools, home):
    tools.fail_when = lambda args: "-r" in args
    events, on_event = collect_events()
    with pytest.raises(BootstrapError, match="command_failed: uv.exe pip install exited with 1"):
        bootstrap._run(CPU, on_event, None, tools.deps_for_test())
    assert finals(events)["deps"] == "failed"
    assert "simulated failure" in events[-1].message
    assert "simulated failure" in (home / "logs" / "install.log").read_text(encoding="utf-8")


def test_cancel_during_torch_then_resume(tools):
    tools.block_torch = True
    cancel = threading.Event()
    events, on_event = collect_events()
    errors = []

    def target():
        try:
            bootstrap._run(CPU, on_event, cancel, tools.deps_for_test())
        except BootstrapError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=target)
    worker.start()
    deadline = time.monotonic() + 10
    while not any(e.stage == "torch" and e.state == "start" for e in events) and time.monotonic() < deadline:
        time.sleep(0.01)
    cancel.set()
    worker.join(10)
    assert errors == ["cancelled"]
    assert finals(events)["torch"] == "failed" and events[-1].message == "cancelled"
    assert bootstrap.was_interrupted()

    tools.block_torch = False
    tools.calls.clear()
    resumed = install(tools)
    state = finals(resumed)
    assert [state[s] for s in ("tools", "python", "venv")] == ["skipped"] * 3
    assert state["torch"] == "done" and state["mark"] == "done"
    assert not any(c[:3] == ["python", "install", "3.11"] for c in tools.uv_calls())


def test_is_installed(tools, monkeypatch):
    monkeypatch.setattr(bootstrap.store, "is_ready", lambda *a, **k: tools.model)
    assert not bootstrap.is_installed()
    install(tools)
    assert bootstrap.is_installed()
    record = bootstrap.read_install()
    record["revision"] = "0" * 40
    bootstrap.install_path().write_text(json.dumps(record), encoding="utf-8")
    assert not bootstrap.is_installed()


def test_is_installed_is_false_after_the_venv_python_moved(tools, monkeypatch):
    monkeypatch.setattr(bootstrap.store, "is_ready", lambda *a, **k: True)
    install(tools)
    cfg = kit.venv_dir() / "pyvenv.cfg"
    cfg.write_text("home = D:\\somewhere\\else\n", encoding="utf-8")
    assert not bootstrap.is_installed()


def test_is_installed_is_false_when_the_model_is_not_ready(tools, monkeypatch):
    install(tools)
    monkeypatch.setattr(bootstrap.store, "is_ready", lambda *a, **k: False)
    assert not bootstrap.is_installed()


def test_remove_engine(tools, home):
    install(tools)
    (home / "queue.json").write_text("{}", encoding="utf-8")
    bootstrap.remove_engine()
    assert not (home / "engine").exists()
    assert not paths.model_dir().exists()
    assert (home / "queue.json").exists()


def test_reset_install_keeps_downloads(tools, home):
    install(tools)
    bootstrap.reset_install()
    assert not bootstrap.install_path().exists()
    assert not kit.venv_dir().exists()
    assert kit.managed_python() is not None
    assert (home / "engine" / "tools" / "uv.exe").exists()
    tools.calls.clear()
    events = install(tools)
    state = finals(events)
    assert state["tools"] == state["python"] == state["model"] == "skipped"
    assert (state["venv"], state["torch"], state["mark"]) == ("done", "done", "done"), state
    assert tools.downloads == [UV_PINS["uv"]["url"]]      # only the first install downloaded uv


def test_sync_worker_files(tools):
    install(tools)
    assert bootstrap.sync_worker_files() is False
    (tools.resources / "worker" / "owl_worker.py").write_text("# newer worker\n", encoding="utf-8")
    assert bootstrap.sync_worker_files() is True
    assert (paths.worker_dir() / "owl_worker.py").read_text(encoding="utf-8") == "# newer worker\n"


def test_sync_worker_files_without_engine(tools):
    assert bootstrap.sync_worker_files() is False


def test_reinstall_repairs_damaged_model_files(tools, monkeypatch):
    install(tools)
    (paths.model_dir() / "tokenizer.json").write_text("damaged", encoding="utf-8")
    monkeypatch.setattr(bootstrap.store, "verify", lambda engine_id="unlimited_ocr": {"tokenizer.json": "sha256 mismatch"})
    bootstrap.reset_install()
    assert not (paths.model_dir() / "tokenizer.json").exists()
    assert not (paths.model_dir() / "manifest.json").exists()     # the model stage downloads it again
    tools.model = False
    events = install(tools)
    assert finals(events)["model"] == "done"


def test_patch_sentinel_matches_the_patcher():
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "worker" / "device_patch.py"
    spec = importlib.util.spec_from_file_location("device_patch", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SENTINEL == kit.PATCH_SENTINEL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_bootstrap_e2e.py -q`
Expected: this task adds no production code, so the tests are expected to pass immediately; if any fails, the failure points at a gap in tasks 8–12. Fix the stage or the orchestration (not the test) until they pass. For a real red step first, temporarily change `"--no-registry"` to `"--no-registryX"` in `do_python`, run the file and confirm `test_fresh_cpu_install_runs_every_stage` fails with an assertion on the uv call; then undo the change.

- [ ] **Step 3: Write minimal implementation**

No new production code. If Step 2 exposed a gap, the fix goes into `owlocr/engine/stages.py` or `owlocr/engine/bootstrap.py` exactly as listed in tasks 8–12.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_bootstrap_e2e.py tests/test_stages.py tests/test_bootstrap_core.py tests/test_install_kit.py -q`
Expected: `72 passed`.

- [ ] **Step 5: Commit**

```
git add tests/test_bootstrap_e2e.py
git commit -m "Add end-to-end tests of the engine installer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Choosing and moving the data root

**Files:**
- Create: `owlocr/engine/relocate.py`
- Test: `tests/test_relocate.py`

**Interfaces:**
- Consumes: `paths.data_root()`, `paths.set_data_root(path)` (plan A resolves and stores the path in `location.txt`), `install_kit.disk_free`, `dir_size`, `rmtree`.
- Produces: `DATA_ITEMS = ("engine", "models", "hf_home", "work", "logs", "dictionaries", "queue.json")`, `class LocationError(ValueError)` (messages `"<code>: <details>"`), `free_bytes(path) -> int`, `has_data(root) -> bool`, `validate_location(path) -> Path`, `choose_location(path) -> Path` (wizard step 3: moves an existing data root, otherwise only points `location.txt` at the folder), `move_data_root(dest) -> Path` (Settings → Move).

Only the items of `DATA_ITEMS` are ever moved; anything else the user keeps in that folder stays. A failed move deletes a half-copied item (its source is still intact) and moves the finished items back. The venv stores absolute paths, so after a move `bootstrap.is_installed()` is False until the wizard has rebuilt the venv; torch and the dependencies come from the moved uv cache and the model is already there, so nothing is downloaded. `OWLOCR_HOME` wins over `location.txt` (design 4), so both functions refuse to change the folder while it is set.

- [ ] **Step 1: Write the failing test**

Create `tests/test_relocate.py`:

```python
import shutil

import pytest

from owlocr import paths
from owlocr.engine import relocate
from owlocr.engine.relocate import LocationError


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    return tmp_path


def fill(root):
    (root / "engine" / "venv").mkdir(parents=True)
    (root / "engine" / "venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (root / "models" / "unlimited_ocr").mkdir(parents=True)
    (root / "models" / "unlimited_ocr" / "config.json").write_text("{}", encoding="utf-8")
    (root / "queue.json").write_text('{"jobs": []}', encoding="utf-8")
    (root / "private.txt").write_text("not ours", encoding="utf-8")


def test_validate_rejects_relative_and_files(config):
    with pytest.raises(LocationError, match="not_absolute"):
        relocate.validate_location(relocate.Path("relative\\folder"))
    f = config / "a_file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(LocationError, match="not_a_folder"):
        relocate.validate_location(f)
    with pytest.raises(LocationError, match="empty"):
        relocate.validate_location(relocate.Path(" "))


def test_validate_creates_folder(config):
    target = config / "new" / "OwlOCR data"
    assert relocate.validate_location(target) == target.resolve()
    assert target.is_dir()


def test_choose_location_without_data_just_points_there(config):
    target = config / "D_drive" / "OwlOCR"
    relocate.choose_location(target)
    assert paths.data_root().resolve() == target.resolve()


def test_move_data_root_moves_only_our_items(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    new = config / "new"
    relocate.move_data_root(new)
    assert paths.data_root().resolve() == new.resolve()
    assert (new / "engine" / "venv" / "pyvenv.cfg").exists()
    assert (new / "models" / "unlimited_ocr" / "config.json").exists()
    assert (new / "queue.json").exists()
    assert (old / "private.txt").exists() and not (new / "private.txt").exists()
    assert not (old / "engine").exists()


def test_choose_location_moves_existing_data(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    relocate.choose_location(config / "new")
    assert (config / "new" / "models").is_dir()


def test_move_refuses_nested_and_existing(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    with pytest.raises(LocationError, match="nested"):
        relocate.move_data_root(old / "inner")
    clash = config / "clash"
    (clash / "models").mkdir(parents=True)
    with pytest.raises(LocationError, match="exists"):
        relocate.move_data_root(clash)
    assert (old / "models").is_dir()


def test_move_refused_when_env_override(config, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(config / "home"))
    with pytest.raises(LocationError, match="env_override"):
        relocate.move_data_root(config / "elsewhere")


def test_failed_move_rolls_back(config, monkeypatch):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    real_move = shutil.move

    def flaky(src, dst):
        if src.endswith("queue.json"):
            raise OSError("disk full")
        return real_move(src, dst)

    monkeypatch.setattr(relocate.shutil, "move", flaky)
    with pytest.raises(LocationError, match="move_failed"):
        relocate.move_data_root(config / "new")
    assert (old / "engine" / "venv" / "pyvenv.cfg").exists()
    assert (old / "models" / "unlimited_ocr" / "config.json").exists()
    assert paths.data_root().resolve() == old.resolve()


def test_free_bytes_of_missing_folder_uses_parent(config):
    assert relocate.free_bytes(config / "does" / "not" / "exist") > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_relocate.py -q`
Expected: collection error `ImportError: cannot import name 'relocate' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/relocate.py`:

```python
"""Choosing the data root and moving an existing one (design 4 and 6.1 step 3)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from owlocr import paths
from owlocr.engine import install_kit as kit

# Everything Owl OCR keeps in the data root. Nothing else in that folder is ever touched.
DATA_ITEMS = ("engine", "models", "hf_home", "work", "logs", "dictionaries", "queue.json")


class LocationError(ValueError):
    """The message starts with a code: `<code>: <details>`."""


def free_bytes(path: Path) -> int:
    return kit.disk_free(path)


def has_data(root: Path) -> bool:
    return any((root / item).exists() for item in ("engine", "models"))


def _install_dir() -> Path | None:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


def validate_location(path: Path) -> Path:
    """Returns the absolute folder or raises LocationError. Creates the folder if needed."""
    raw = str(path).strip().strip('"')
    if not raw:
        raise LocationError("empty: no folder given")
    folder = Path(os.path.expandvars(raw)).expanduser()
    if not folder.is_absolute():
        raise LocationError(f"not_absolute: {folder}")
    folder = folder.resolve()
    if folder.exists() and not folder.is_dir():
        raise LocationError(f"not_a_folder: {folder}")
    install = _install_dir()
    if install is not None and (folder == install or folder.is_relative_to(install)):
        raise LocationError(f"inside_install: {folder} is inside the program folder {install}")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".owlocr-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise LocationError(f"not_writable: {folder}: {exc}") from exc
    return folder


def choose_location(path: Path) -> Path:
    """Wizard step 3: makes `path` the data root. An existing data root is moved there."""
    folder = validate_location(path)
    current = paths.data_root().resolve()
    if folder == current:
        return folder
    if has_data(current):
        move_data_root(folder)
    else:
        if os.environ.get("OWLOCR_HOME"):
            raise LocationError("env_override: OWLOCR_HOME is set, the data folder cannot be changed")
        paths.set_data_root(folder)
    return folder


def move_data_root(dest: Path) -> Path:
    """Moves every item of DATA_ITEMS to `dest` and points location.txt there.

    The engine must be stopped. Items already moved are moved back when a later one fails.
    The venv stores absolute paths, so afterwards `bootstrap.is_installed()` is False until the
    installer has rebuilt the venv from the kept downloads (no network needed)."""
    if os.environ.get("OWLOCR_HOME"):
        raise LocationError("env_override: OWLOCR_HOME is set, the data folder cannot be moved")
    src = paths.data_root().resolve()
    dest = validate_location(dest)
    if dest == src:
        return dest
    if dest.is_relative_to(src) or src.is_relative_to(dest):
        raise LocationError(f"nested: {dest} and {src} contain each other")
    items = [item for item in DATA_ITEMS if (src / item).exists()]
    clashes = [item for item in items if (dest / item).exists()]
    if clashes:
        raise LocationError(f"exists: {dest} already contains {', '.join(clashes)}")
    needed = sum(kit.dir_size(src / i) if (src / i).is_dir() else (src / i).stat().st_size for i in items)
    same_drive = os.path.splitdrive(str(src))[0].lower() == os.path.splitdrive(str(dest))[0].lower()
    if not same_drive and free_bytes(dest) < needed:
        raise LocationError(f"not_enough_space: {needed} bytes needed, {free_bytes(dest)} free")
    moved: list[str] = []
    try:
        for item in items:
            shutil.move(str(src / item), str(dest / item))
            moved.append(item)
    except OSError as exc:
        failed = items[len(moved)]
        partial = dest / failed
        if (src / failed).exists() and partial.exists():     # half-copied: the source is intact
            if partial.is_dir():
                kit.rmtree(partial)
            else:
                partial.unlink()
        for item in reversed(moved):
            try:
                shutil.move(str(dest / item), str(src / item))
            except OSError:
                pass
        raise LocationError(f"move_failed: {exc}") from exc
    paths.set_data_root(dest)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_relocate.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/relocate.py tests/test_relocate.py
git commit -m "Add choosing and moving the data folder" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Removing the app's data for the uninstaller

**Files:**
- Create: `owlocr/uninstall.py`
- Test: `tests/test_uninstall.py`

**Interfaces:**
- Consumes: `paths.data_root()`, `paths.config_dir()`, `relocate.DATA_ITEMS`, `install_kit.rmtree`, plan A's `client.sweep_stale_worker()`.
- Produces: `CONFIG_ITEMS = ("settings.json", "location.txt")`, `remove_all_data() -> list[str]` (problems; empty when all went well), `main() -> int`. The uninstaller runs `OwlOCR.exe --remove-data` (Task 23 routes it here) only after the user said yes. The folders themselves are removed only when nothing else is left in them, so a data root chosen as, say, `D:\` is never wiped.

- [ ] **Step 1: Write the failing test**

Create `tests/test_uninstall.py`:

```python
import pytest

from owlocr import paths, uninstall


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    data = tmp_path / "data"
    paths.set_data_root(data)
    monkeypatch.setattr("owlocr.engine.client.sweep_stale_worker", lambda: None, raising=False)
    return tmp_path, data


def test_removes_our_items_and_empty_folders(dirs):
    tmp, data = dirs
    for d in ("engine/venv", "models/unlimited_ocr", "hf_home", "work/abc", "logs", "dictionaries"):
        (data / d).mkdir(parents=True)
    (data / "models" / "unlimited_ocr" / "x.bin").write_bytes(b"1")
    (data / "queue.json").write_text("{}", encoding="utf-8")
    (tmp / "config" / "settings.json").write_text("{}", encoding="utf-8")
    assert uninstall.remove_all_data() == []
    assert not data.exists()
    assert not (tmp / "config").exists()


def test_keeps_foreign_files(dirs):
    tmp, data = dirs
    (data / "engine").mkdir(parents=True)
    (data / "my thesis.docx").write_text("precious", encoding="utf-8")
    assert uninstall.remove_all_data() == []
    assert (data / "my thesis.docx").read_text(encoding="utf-8") == "precious"
    assert not (data / "engine").exists()


def test_main_exit_code(dirs):
    assert uninstall.main() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_uninstall.py -q`
Expected: collection error `ImportError: cannot import name 'uninstall' from 'owlocr'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/uninstall.py`:

```python
"""`OwlOCR.exe --remove-data`: called by the uninstaller when the user agrees to delete the
engine and the app's data. Deletes only what Owl OCR created; documents and the files written
next to them are never touched."""
from __future__ import annotations

import sys
from pathlib import Path

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine.relocate import DATA_ITEMS

CONFIG_ITEMS = ("settings.json", "location.txt")


def _remove(target: Path, problems: list[str]) -> None:
    try:
        if target.is_dir():
            kit.rmtree(target)
        elif target.exists():
            target.unlink()
    except OSError as exc:
        problems.append(f"{target}: {exc}")


def remove_all_data() -> list[str]:
    """Returns a list of problems; empty when everything was removed."""
    problems: list[str] = []
    try:
        from owlocr.engine.client import sweep_stale_worker
        sweep_stale_worker()            # an engine left running would keep files locked
    except Exception as exc:            # a failed sweep must not stop the uninstall
        problems.append(f"sweep: {exc}")
    root, config = paths.data_root(), paths.config_dir()
    for item in DATA_ITEMS:
        _remove(root / item, problems)
    for item in CONFIG_ITEMS:
        _remove(config / item, problems)
    for folder in (root, config):
        try:
            folder.rmdir()               # only succeeds when nothing else is left in it
        except OSError:
            pass
    return problems


def main() -> int:
    return 0 if not remove_all_data() else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_uninstall.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/uninstall.py tests/test_uninstall.py
git commit -m "Add removal of the engine and app data for the uninstaller" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Wizard HTTP routes

**Files:**
- Create: `owlocr/web/wizard_api.py`
- Create: `tests/wizard_fakes.py`
- Test: `tests/test_wizard_api.py`

**Interfaces:**
- Consumes: `hardware.probe_gpus`, `ram_total_mib`, `choose_tier`, `CPU_TIER_ENABLED`; `bootstrap.run`, `STAGES`, `StageEvent`, `BootstrapError`, `REQUIRED_FREE_BYTES`, `was_interrupted`, `is_installed`, `read_install`, `sync_worker_files`; `relocate.choose_location`, `has_data`, `free_bytes`, `LocationError`; `store.adopt(folder, spec, move)`, `store.is_ready`, `StoreError`; plan B's `Runner.status()` and `Runner.stop_engine()`, `owlocr.jobs.engines.forget_installed()`.
- Produces: `make_blueprint(runner, controller=None, probe_fn=None) -> flask.Blueprint`, `class InstallController(run_fn=None)` with `start(tier) -> bool`, `cancel()`, `wait(timeout)`, `snapshot() -> {"events", "running", "error"}`, property `running`; `demo_install(tier, on_event, cancel)` (used when `OWLOCR_DEMO_INSTALL=1`). Routes (contract, plus additions marked +):
  - `GET /api/wizard/probe` → `{"gpus": [Gpu], "ram_mib", "tier": Tier, "data_root", "free_bytes"}` + `required_bytes`, `interrupted`, `installed`, `model_ready`, `install` (the install record or null), `env_override`, `logs_dir`, `cpu_tier_enabled`
  - `POST /api/wizard/location {"path"}` → `{"data_root", "free_bytes"}`; errors 400 with `LocationError` codes, 409 while installing or while the queue runs
  - `POST /api/wizard/adopt {"path", + "copy": bool}` → `{"ok": true}`; 400 `adopt_failed: ...`
  - `POST /api/wizard/install` → `{"started": true}` (+ `false` when it already runs); 400 `unsupported: <reason>`
  - `POST /api/wizard/cancel` → `{}` (the UI calls it "Pause": everything downloaded is kept)
  - `GET /api/wizard/progress` → `{"events": [StageEvent], "running", "error"}`; progress events of one stage run are collapsed into the latest, so the list stays short

`InstallController` runs `bootstrap.run` in a daemon thread. When the app closes during an installation the thread dies with it; the running uv is ended by the Job Object of `uvtool.run_command`, and `install_state.json` makes the wizard offer "Continue" on the next start. After every installation, adoption or data-root change the controller or route calls `engines.forget_installed()`, so `/api/status` shows the new state at once (plan B caches it for 5 s). `make_blueprint` also calls `bootstrap.sync_worker_files()` once, so an app update brings its newer worker scripts into an existing engine without the wizard. Every error is a JSON `{"error": "<code>: <details>"}`; the UI translates the code.

- [ ] **Step 1: Write the failing test**

Create `tests/wizard_fakes.py`:

```python
"""Helpers for the wizard and engine route tests: a fake Runner and a client with the X-Owl header."""
import time

from flask import Flask

from owlocr.engine.bootstrap import BootstrapError
from owlocr.hardware import Gpu
from owlocr.web.wizard_api import make_blueprint

RTX = Gpu("NVIDIA GeForce RTX 4080 SUPER", "617.14", 16376, 13858, 8.9)


class FakeRunner:
    def __init__(self):
        self.state = {"engine": "stopped", "running": False, "paused": False, "current_job": None,
                      "current_page_tokens": 0, "vram_used_mib": None}
        self.stops = 0

    def status(self):
        return dict(self.state)

    def stop_engine(self):
        self.stops += 1


def scripted_run(events_to_send, error=None, gate=None):
    def run(tier, on_event, cancel):
        for ev in events_to_send:
            on_event(ev)
        if gate is not None:
            while not cancel.is_set():
                time.sleep(0.01)
            raise BootstrapError("cancelled")
        if error:
            raise BootstrapError(error)
    return run


H = {"X-Owl": "1"}


class Client:
    """Flask test client that sends the X-Owl header plan B's guard requires."""

    def __init__(self, client):
        self._client = client

    def get(self, path, **kw):
        return self._client.get(path, **kw)

    def post(self, path, **kw):
        return self._client.post(path, headers=H, **kw)


def make_client(runner=None, controller=None, gpus=(RTX,), ram=65000):
    app = Flask(__name__)
    runner = runner or FakeRunner()
    app.register_blueprint(make_blueprint(runner, controller, probe_fn=lambda: (list(gpus), ram)))
    return Client(app.test_client()), runner
```

Create `tests/test_wizard_api.py`:

```python
import threading
from pathlib import Path

import pytest

from owlocr import paths
from owlocr.engine import bootstrap
from owlocr.engine.bootstrap import StageEvent
from owlocr.web import wizard_api
from owlocr.web.wizard_api import InstallController
from tests.wizard_fakes import make_client, scripted_run


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    paths.set_data_root(tmp_path / "data")
    return tmp_path


def test_probe(env):
    client, _ = make_client()
    data = client.get("/api/wizard/probe").get_json()
    assert data["gpus"][0]["name"] == "NVIDIA GeForce RTX 4080 SUPER"
    assert data["ram_mib"] == 65000
    assert data["tier"]["name"] == "gpu_full" and data["tier"]["default_mode"] == "quality"
    assert Path(data["data_root"]).resolve() == (env / "data").resolve()
    assert data["free_bytes"] > 0 and data["required_bytes"] == 16 * 1024**3
    assert data["installed"] is False and data["interrupted"] is False and data["install"] is None
    assert data["env_override"] is False and data["cpu_tier_enabled"] is True


def test_location_sets_data_root(env):
    client, runner = make_client()
    target = env / "other drive" / "Owl"
    data = client.post("/api/wizard/location", json={"path": str(target)}).get_json()
    assert data["data_root"] == str(target.resolve())
    assert paths.data_root().resolve() == target.resolve()
    assert runner.stops == 0


def test_location_moves_existing_data_after_stopping_the_engine(env):
    (env / "data" / "models" / "unlimited_ocr").mkdir(parents=True)
    client, runner = make_client()
    response = client.post("/api/wizard/location", json={"path": str(env / "new")})
    assert response.status_code == 200
    assert (env / "new" / "models" / "unlimited_ocr").is_dir()
    assert runner.stops == 1


def test_location_errors(env):
    client, _ = make_client()
    assert client.post("/api/wizard/location", json={}).get_json()["error"].startswith("empty")
    response = client.post("/api/wizard/location", json={"path": "relative"})
    assert response.status_code == 400 and response.get_json()["error"].startswith("not_absolute")


def test_adopt_calls_store(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.store, "adopt", lambda folder, spec, move=True: calls.append((folder, spec.engine_id, move)))
    client, _ = make_client()
    assert client.post("/api/wizard/adopt", json={"path": "C:\\Users\\x\\engine"}).get_json() == {"ok": True}
    assert client.post("/api/wizard/adopt", json={"path": "C:\\Users\\x\\engine", "copy": True}).status_code == 200
    assert [c[2] for c in calls] == [True, False]
    assert calls[0][1] == "unlimited_ocr"


def test_adopt_failure(env, monkeypatch):
    def boom(folder, spec, move=True):
        raise wizard_api.store.StoreError("sha256 mismatch in model-00001-of-000001.safetensors")
    monkeypatch.setattr(wizard_api.store, "adopt", boom)
    client, _ = make_client()
    response = client.post("/api/wizard/adopt", json={"path": "C:\\nowhere"})
    assert response.status_code == 400
    assert response.get_json()["error"].startswith("adopt_failed: sha256 mismatch")


def test_install_progress_and_collapsed_events(env):
    events = [StageEvent("tools", "start", 0, 0, "checking")] + \
             [StageEvent("tools", "progress", i, 10, "") for i in range(1, 11)] + \
             [StageEvent("tools", "done", 10, 10, "")]
    controller = InstallController(run_fn=scripted_run(events))
    client, _ = make_client(controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    controller.wait(5)
    data = client.get("/api/wizard/progress").get_json()
    assert data["running"] is False and data["error"] is None
    assert [(e["state"], e["done"]) for e in data["events"]] == [("start", 0), ("progress", 10), ("done", 10)]


def test_install_error_is_reported(env):
    controller = InstallController(run_fn=scripted_run([], error="not_enough_space: 1 bytes needed, 0 free"))
    client, _ = make_client(controller=controller)
    client.post("/api/wizard/install")
    controller.wait(5)
    assert client.get("/api/wizard/progress").get_json()["error"].startswith("not_enough_space")


def test_cancel_and_second_start(env):
    gate = threading.Event()
    controller = InstallController(run_fn=scripted_run([StageEvent("torch", "start", 0, 0, "")], gate=gate))
    client, _ = make_client(controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    assert client.post("/api/wizard/install").get_json() == {"started": False}
    assert client.post("/api/wizard/cancel").get_json() == {}
    controller.wait(5)
    data = client.get("/api/wizard/progress").get_json()
    assert data["running"] is False and data["error"] == "cancelled"


def test_install_refused_on_unsupported_hardware(env):
    client, _ = make_client(gpus=(), ram=8000)
    response = client.post("/api/wizard/install")
    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported: ram_too_small"


def test_finished_install_refreshes_the_installed_cache(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.engines, "forget_installed", lambda: calls.append("forget"))
    controller = InstallController(run_fn=scripted_run([StageEvent("mark", "done", 0, 0, "")]))
    client, _ = make_client(controller=controller)
    client.post("/api/wizard/install")
    controller.wait(5)
    assert calls == ["forget"]


def test_demo_install_is_used_when_requested(env, monkeypatch):
    monkeypatch.setenv("OWLOCR_DEMO_INSTALL", "1")
    assert InstallController()._run_fn is wizard_api.demo_install
    monkeypatch.delenv("OWLOCR_DEMO_INSTALL")
    assert InstallController()._run_fn is bootstrap.run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_wizard_api.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'owlocr.web.wizard_api'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/web/wizard_api.py`:

```python
"""HTTP routes of the setup wizard and of the engine actions in Settings (plan D).

Registered by `owlocr/web/server.py:create_app` with `app.register_blueprint(make_blueprint(runner))`.
"""
from __future__ import annotations

import dataclasses
import os
import threading
import time
from pathlib import Path
from typing import Callable

from flask import Blueprint, jsonify, request

from owlocr import hardware, paths
from owlocr.engine import bootstrap, registry, relocate, store
from owlocr.engine.bootstrap import BootstrapError, StageEvent
from owlocr.engine.relocate import LocationError
from owlocr.jobs import engines


def demo_install(tier: hardware.Tier, on_event: Callable[[StageEvent], None],
                 cancel: threading.Event) -> None:
    """Used when OWLOCR_DEMO_INSTALL=1: walks through the stages without installing anything,
    so the wizard can be tried out and smoke-tested without downloading 10 GB."""
    for stage in bootstrap.STAGES:
        on_event(StageEvent(stage, "start", 0, 0, "checking"))
        for step in range(1, 11):
            if cancel.is_set():
                on_event(StageEvent(stage, "failed", step, 10, "cancelled"))
                raise BootstrapError("cancelled")
            time.sleep(0.25)
            on_event(StageEvent(stage, "progress", step * 100_000_000, 1_000_000_000, f"demo {stage}"))
        on_event(StageEvent(stage, "done", 1_000_000_000, 1_000_000_000, ""))


class InstallController:
    """Runs `bootstrap.run` in a background thread and keeps its events for polling."""

    def __init__(self, run_fn: Callable | None = None) -> None:
        if run_fn is None:
            run_fn = demo_install if os.environ.get("OWLOCR_DEMO_INSTALL") == "1" else bootstrap.run
        self._run_fn = run_fn
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, tier: hardware.Tier) -> bool:
        with self._lock:
            if self.running:
                return False
            self._events, self._error = [], None
            self._cancel = threading.Event()
            self._thread = threading.Thread(target=self._work, args=(tier, self._cancel),
                                            name="owl-install", daemon=True)
            self._thread.start()
            return True

    def _work(self, tier: hardware.Tier, cancel: threading.Event) -> None:
        try:
            self._run_fn(tier, self._on_event, cancel)
        except BootstrapError as exc:
            with self._lock:
                self._error = str(exc)
        except Exception as exc:        # never let the thread die silently
            with self._lock:
                self._error = f"internal: {type(exc).__name__}: {exc}"
        finally:
            engines.forget_installed()  # /api/status must see the new state at once

    def _on_event(self, event: StageEvent) -> None:
        data = dataclasses.asdict(event)
        with self._lock:
            last = self._events[-1] if self._events else None
            if (data["state"] == "progress" and last is not None
                    and last["stage"] == data["stage"] and last["state"] == "progress"):
                self._events[-1] = data           # keep one progress event per stage run
            else:
                self._events.append(data)

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def snapshot(self) -> dict:
        with self._lock:
            return {"events": list(self._events), "running": self.running, "error": self._error}


def _default_probe() -> tuple[list[hardware.Gpu], int]:
    return hardware.probe_gpus(), hardware.ram_total_mib()


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def make_blueprint(runner, controller: InstallController | None = None,
                   probe_fn: Callable[[], tuple[list[hardware.Gpu], int]] | None = None) -> Blueprint:
    bp = Blueprint("owl_wizard", __name__)
    installer = controller or InstallController()
    probe_hw = probe_fn or _default_probe
    try:
        bootstrap.sync_worker_files()   # an app update may bring newer worker scripts
    except OSError:
        pass

    def queue_busy() -> bool:
        status = runner.status()
        return status.get("engine") == "busy" or (bool(status.get("running")) and not status.get("paused"))

    def blocked():
        """Response when the engine files must not be touched now, else None."""
        if installer.running:
            return _error("install_running: wait until the installation finishes or pause it", 409)
        if queue_busy():
            return _error("queue_running: pause the queue first", 409)
        return None

    def body_path() -> str | None:
        body = request.get_json(silent=True) or {}
        value = body.get("path")
        return value if isinstance(value, str) and value.strip() else None

    @bp.get("/api/wizard/probe")
    def wizard_probe():
        gpus, ram = probe_hw()
        tier = hardware.choose_tier(gpus, ram)
        root = paths.data_root()
        return jsonify({
            "gpus": [dataclasses.asdict(g) for g in gpus], "ram_mib": ram,
            "tier": dataclasses.asdict(tier), "data_root": str(root),
            "free_bytes": relocate.free_bytes(root), "required_bytes": bootstrap.REQUIRED_FREE_BYTES,
            "interrupted": bootstrap.was_interrupted(), "installed": bootstrap.is_installed(),
            "model_ready": store.is_ready(),
            "install": bootstrap.read_install(), "env_override": bool(os.environ.get("OWLOCR_HOME")),
            "logs_dir": str(paths.logs_dir()), "cpu_tier_enabled": hardware.CPU_TIER_ENABLED,
        })

    @bp.post("/api/wizard/location")
    def wizard_location():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        if relocate.has_data(paths.data_root()):
            refusal = blocked()
            if refusal:
                return refusal
            runner.stop_engine()
        elif installer.running:
            return _error("install_running: wait until the installation finishes or pause it", 409)
        try:
            folder = relocate.choose_location(Path(path))
        except LocationError as exc:
            return _error(str(exc), 400)
        finally:
            engines.forget_installed()
        return jsonify({"data_root": str(folder), "free_bytes": relocate.free_bytes(folder)})

    @bp.post("/api/wizard/adopt")
    def wizard_adopt():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        if installer.running:
            return _error("install_running: wait until the installation finishes or pause it", 409)
        copy = bool((request.get_json(silent=True) or {}).get("copy", False))
        try:
            store.adopt(Path(path), registry.UNLIMITED_OCR, move=not copy)
        except (store.StoreError, OSError) as exc:
            return _error(f"adopt_failed: {exc}", 400)
        finally:
            engines.forget_installed()
        return jsonify({"ok": True})

    @bp.post("/api/wizard/install")
    def wizard_install():
        gpus, ram = probe_hw()
        tier = hardware.choose_tier(gpus, ram)
        if tier.name == "unsupported":
            return _error(f"unsupported: {tier.reason}", 400)
        return jsonify({"started": installer.start(tier)})

    @bp.post("/api/wizard/cancel")
    def wizard_cancel():
        installer.cancel()
        return jsonify({})

    @bp.get("/api/wizard/progress")
    def wizard_progress():
        return jsonify(installer.snapshot())

    return bp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_wizard_api.py -q`
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/web/wizard_api.py tests/wizard_fakes.py tests/test_wizard_api.py
git commit -m "Add wizard routes with a background install controller" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Engine routes for Settings

**Files:**
- Modify: `owlocr/web/wizard_api.py`
- Test: `tests/test_engine_routes.py`

**Interfaces:**
- Consumes: `store.verify()` (re-hashes every file, design 6.3 rule 4), `bootstrap.remove_engine()`, `bootstrap.reset_install()`, `relocate.move_data_root()`, `Runner.stop_engine()`, `engines.forget_installed()`.
- Produces (contract): `POST /api/engine/verify` → `{"problems": {path: reason}}`, `POST /api/engine/remove` → `{}`. Additions: `POST /api/engine/reinstall` → `{}` (forgets the install record, rebuilds the venv, deletes model files that fail verification so only those are downloaded again), `POST /api/engine/move {"path"}` → `{"data_root", "free_bytes"}`. All four answer 409 `install_running: ...` during an installation; remove, reinstall and move answer 409 `queue_running: ...` while the queue is processing, and otherwise stop the engine with `Runner.stop_engine()` first (its thread stays alive, so the queue works again afterwards; `Runner.shutdown()` is never used here).

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_routes.py`:

```python
import threading

import pytest

from owlocr import paths
from owlocr.engine.bootstrap import StageEvent
from owlocr.web import wizard_api
from owlocr.web.wizard_api import InstallController
from tests.wizard_fakes import FakeRunner, make_client, scripted_run


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    paths.set_data_root(tmp_path / "data")
    return tmp_path


def test_move_refused_while_queue_runs(env):
    (env / "data" / "engine").mkdir(parents=True)
    runner = FakeRunner()
    runner.state.update(running=True, engine="busy")
    client, _ = make_client(runner)
    response = client.post("/api/engine/move", json={"path": str(env / "new")})
    assert response.status_code == 409 and response.get_json()["error"].startswith("queue_running")
    assert (env / "data" / "engine").is_dir()


def test_verify(env, monkeypatch):
    monkeypatch.setattr(wizard_api.store, "verify", lambda engine_id="unlimited_ocr": {"tokenizer.json": "sha mismatch"})
    client, _ = make_client()
    assert client.post("/api/engine/verify").get_json() == {"problems": {"tokenizer.json": "sha mismatch"}}


def test_remove_and_reinstall(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.bootstrap, "remove_engine", lambda: calls.append("remove"))
    monkeypatch.setattr(wizard_api.bootstrap, "reset_install", lambda: calls.append("reset"))
    monkeypatch.setattr(wizard_api.engines, "forget_installed", lambda: calls.append("forget"))
    client, runner = make_client()
    assert client.post("/api/engine/remove").get_json() == {}
    assert client.post("/api/engine/reinstall").get_json() == {}
    assert calls == ["remove", "forget", "reset", "forget"] and runner.stops == 2


def test_engine_move(env):
    (env / "data" / "engine").mkdir(parents=True)
    client, runner = make_client()
    data = client.post("/api/engine/move", json={"path": str(env / "moved")}).get_json()
    assert data["data_root"] == str((env / "moved").resolve())
    assert (env / "moved" / "engine").is_dir() and runner.stops == 1


def test_engine_actions_are_refused_while_installing(env):
    gate = threading.Event()
    controller = InstallController(run_fn=scripted_run([StageEvent("torch", "start", 0, 0, "")], gate=gate))
    client, runner = make_client(controller=controller)
    client.post("/api/wizard/install")
    for path in ("/api/engine/remove", "/api/engine/reinstall", "/api/engine/verify"):
        response = client.post(path)
        assert response.status_code == 409 and response.get_json()["error"].startswith("install_running"), path
    assert client.post("/api/engine/move", json={"path": str(env / "x")}).status_code == 409
    assert runner.stops == 0
    client.post("/api/wizard/cancel")
    controller.wait(5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_engine_routes.py -q`
Expected: `5 failed`, each with a 404 status or `TypeError: 'NoneType' object is not subscriptable` from a 404 answer.

- [ ] **Step 3: Write minimal implementation**

In `owlocr/web/wizard_api.py`, insert these routes inside `make_blueprint`, directly above its final line `    return bp`:

```python
    @bp.post("/api/engine/verify")
    def engine_verify():
        if installer.running:
            return _error("install_running: wait until the installation finishes or pause it", 409)
        return jsonify({"problems": store.verify()})

    @bp.post("/api/engine/remove")
    def engine_remove():
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        try:
            bootstrap.remove_engine()
        except BootstrapError as exc:
            return _error(str(exc), 409)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        finally:
            engines.forget_installed()
        return jsonify({})

    @bp.post("/api/engine/reinstall")
    def engine_reinstall():
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        try:
            bootstrap.reset_install()
        except BootstrapError as exc:
            return _error(str(exc), 409)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        finally:
            engines.forget_installed()
        return jsonify({})

    @bp.post("/api/engine/move")
    def engine_move():
        path = body_path()
        if path is None:
            return _error("empty: no folder given", 400)
        refusal = blocked()
        if refusal:
            return refusal
        runner.stop_engine()
        try:
            folder = relocate.move_data_root(Path(path))
        except LocationError as exc:
            return _error(str(exc), 400)
        finally:
            engines.forget_installed()
        return jsonify({"data_root": str(folder), "free_bytes": relocate.free_bytes(folder)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_engine_routes.py tests/test_wizard_api.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/web/wizard_api.py tests/test_engine_routes.py
git commit -m "Add engine verify, reinstall, move and remove routes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Dictionary routes

**Files:**
- Create: `owlocr/web/dictionaries_api.py`
- Test: `tests/test_dictionaries_api.py`

**Interfaces:**
- Consumes: plan C's `owlocr.pipeline.dictionaries` (`LANGUAGES = ("cs", "en")`, `manifest()` → `{"url_template", "languages": {lang: {"name", "source", "commit", "licence", "decision", "files": [{"name", "path", "size", "sha256"}]}}}`, `download(language, on_progress=None, cancel=None, entry=None) -> Path` (progress in bytes, verified files moved in one by one, calls `spellcheck._reset_cache()` at the end), `remove(language)` (also resets the cache), `DictionaryError`, test seam `_open(url)`), `owlocr.pipeline.spellcheck` (`available(language)`, `_reset_cache()`), plan C's test fixture `no_dicts`.
- Produces: `class DictionaryJobs(download_fn=None, remove_fn=None)` with `start(language) -> bool`, `running(language)`, `remove(language)`, `wait(language, timeout)`, `state(language) -> {"done", "total", "error", "running"}`; `languages_status(jobs) -> list[dict]`; `make_dictionaries_blueprint(jobs=None) -> flask.Blueprint`. Routes (additions to the contract):
  - `GET /api/dictionaries` → `{"languages": [{"language", "name", "installed", "size", "licence", "source", "running", "done", "total", "error"}]}` in the order `cs`, `en`; the UI polls it once a second while a download runs (plan C's `download` is blocking, so progress comes through this route, not through the POST answer)
  - `POST /api/dictionaries/<language>` → `{"started": true}` (`false` while that language already downloads); 404 `unknown_language: ...`
  - `DELETE /api/dictionaries/<language>` → `{}`; 409 `dictionary_running: ...` during its download; 404 for an unknown language

Behaviour: every download runs in its own daemon thread. Plan C moves a file into place only after its size and sha256 match, but a failure in the second or third file would leave the licence and the `.aff` file behind; when the language was not installed before, the job therefore calls `dictionaries.remove(language)` after any failure, so no partial dictionary stays, and the error becomes `dictionary_failed: <details>`. Plan C's `spellcheck` caches loaded dictionaries and look-ups and already has `_reset_cache()`, which `download` and `remove` call; the job calls it once more after a success (harmless), so a running app uses a new dictionary at once, without a restart. The dictionaries are optional: the app never downloads them on its own.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dictionaries_api.py`:

```python
"""Routes for the optional dictionaries, on top of plan C's `dictionaries` module (network faked)."""
import hashlib
import io
import threading

import pytest
from flask import Flask

from owlocr.pipeline import dictionaries, spellcheck
from owlocr.web.dictionaries_api import DictionaryJobs, make_dictionaries_blueprint

H = {"X-Owl": "1"}
FILES = {
    "cs_CZ.LICENSE.txt": b"GNU GPL licence text",
    "cs_CZ.aff": "SET UTF-8\n".encode("utf-8"),
    "cs_CZ.dic": "2\nbuď\nstrom\n".encode("utf-8"),
}


REAL_MANIFEST = dictionaries.manifest()


def fake_manifest(files=FILES):
    real = REAL_MANIFEST
    cs = {"name": "cs_CZ", "source": "https://example.invalid/cs_CZ", "commit": "0" * 40,
          "licence": "GNU GPL", "decision": "test",
          "files": [{"name": n, "path": f"cs_CZ/{n}", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                    for n, d in files.items()]}
    return {"url_template": real["url_template"], "languages": {"cs": cs, "en": real["languages"]["en"]}}


@pytest.fixture
def served(no_dicts, monkeypatch):
    """Serves FILES instead of GitHub; the test may change what is served."""
    content = dict(FILES)
    monkeypatch.setattr(dictionaries, "manifest", lambda: fake_manifest())
    monkeypatch.setattr(dictionaries, "_open", lambda url: io.BytesIO(content[url.rsplit("/", 1)[1]]))
    return content


def client(jobs=None):
    app = Flask(__name__)
    jobs = jobs or DictionaryJobs()
    app.register_blueprint(make_dictionaries_blueprint(jobs))
    return app.test_client(), jobs


def by_language(response):
    return {row["language"]: row for row in response.get_json()["languages"]}


def test_list_shows_state_size_and_licence(served):
    c, _ = client()
    rows = by_language(c.get("/api/dictionaries"))
    assert set(rows) == {"cs", "en"}
    assert rows["cs"]["installed"] is False and rows["cs"]["running"] is False
    assert rows["cs"]["size"] == sum(len(d) for d in FILES.values())
    assert rows["cs"]["licence"] == "GNU GPL" and rows["cs"]["source"].startswith("https://")
    assert rows["en"]["licence"].startswith("SCOWL") and rows["en"]["size"] > 500_000


def test_install_makes_the_dictionary_work_without_a_restart(served):
    c, jobs = client()
    assert spellcheck.known("bud", "cs") is True            # no dictionary: everything is "known"
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": True}
    jobs.wait("cs", 10)
    row = by_language(c.get("/api/dictionaries"))["cs"]
    assert row["installed"] is True and row["error"] is None
    assert row["done"] == row["total"] == sum(len(d) for d in FILES.values())
    assert spellcheck.known("buď", "cs") and not spellcheck.known("bud", "cs")


def test_failed_download_leaves_nothing_behind(served):
    served["cs_CZ.dic"] = b"2\nbroken\n"                     # wrong sha256 for the last file
    c, jobs = client()
    c.post("/api/dictionaries/cs", headers=H)
    jobs.wait("cs", 10)
    row = by_language(c.get("/api/dictionaries"))["cs"]
    assert row["installed"] is False and row["error"].startswith("dictionary_failed:")
    assert list(spellcheck.dictionaries_dir().iterdir()) == []   # licence and .aff removed again


def test_remove(served):
    c, jobs = client()
    c.post("/api/dictionaries/cs", headers=H)
    jobs.wait("cs", 10)
    assert c.delete("/api/dictionaries/cs", headers=H).get_json() == {}
    assert by_language(c.get("/api/dictionaries"))["cs"]["installed"] is False
    assert spellcheck.known("bud", "cs") is True


def test_one_download_per_language_and_no_remove_meanwhile(served):
    release = threading.Event()

    def slow_download(language, on_progress=None):
        release.wait(10)

    c, jobs = client(DictionaryJobs(download_fn=slow_download))
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": True}
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": False}
    assert by_language(c.get("/api/dictionaries"))["cs"]["running"] is True
    response = c.delete("/api/dictionaries/cs", headers=H)
    assert response.status_code == 409 and response.get_json()["error"].startswith("dictionary_running")
    release.set()
    jobs.wait("cs", 10)


def test_unknown_language(served):
    c, _ = client()
    assert c.post("/api/dictionaries/de", headers=H).status_code == 404
    assert c.delete("/api/dictionaries/de", headers=H).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_dictionaries_api.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'owlocr.web.dictionaries_api'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/web/dictionaries_api.py`:

```python
"""HTTP routes for the optional spell-check dictionaries (plan C's `dictionaries` module).

The dictionaries are never bundled: the wizard's optional step and Settings download them on
request. A download runs in a background thread; `GET /api/dictionaries` reports its progress.
A failed download removes every file of that language again, so no half dictionary is left.
"""
from __future__ import annotations

import threading
from typing import Callable

from flask import Blueprint, jsonify

from owlocr.pipeline import dictionaries, spellcheck


class DictionaryJobs:
    """One background download per language, with progress and the last error."""

    def __init__(self, download_fn: Callable | None = None, remove_fn: Callable | None = None) -> None:
        self._download = download_fn or dictionaries.download
        self._remove = remove_fn or dictionaries.remove
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}

    def running(self, language: str) -> bool:
        thread = self._threads.get(language)
        return thread is not None and thread.is_alive()

    def start(self, language: str) -> bool:
        with self._lock:
            if self.running(language):
                return False
            self._jobs[language] = {"done": 0, "total": 0, "error": None}
            thread = threading.Thread(target=self._work, args=(language,), name=f"owl-dict-{language}", daemon=True)
            self._threads[language] = thread
            thread.start()
            return True

    def _work(self, language: str) -> None:
        was_installed = spellcheck.available(language)

        def progress(done: int, total: int) -> None:
            with self._lock:
                self._jobs[language].update(done=done, total=total)

        try:
            self._download(language, on_progress=progress)
            spellcheck._reset_cache()           # plan C resets too; a second reset is harmless
        except Exception as exc:                # DictionaryError, network, disk: never half-installed
            message = str(exc) if isinstance(exc, dictionaries.DictionaryError) else f"{type(exc).__name__}: {exc}"
            if not was_installed:
                try:
                    self._remove(language)
                except OSError:
                    pass
            with self._lock:
                self._jobs[language]["error"] = f"dictionary_failed: {message}"

    def remove(self, language: str) -> None:
        self._remove(language)
        with self._lock:
            self._jobs.pop(language, None)

    def wait(self, language: str, timeout: float | None = None) -> None:
        thread = self._threads.get(language)
        if thread is not None:
            thread.join(timeout)

    def state(self, language: str) -> dict:
        with self._lock:
            job = dict(self._jobs.get(language) or {"done": 0, "total": 0, "error": None})
        job["running"] = self.running(language)
        return job


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def languages_status(jobs: DictionaryJobs) -> list[dict]:
    languages = dictionaries.manifest()["languages"]
    rows = []
    for language in dictionaries.LANGUAGES:
        entry = languages[language]
        rows.append({"language": language, "name": entry["name"], "installed": spellcheck.available(language),
                     "size": sum(f["size"] for f in entry["files"]), "licence": entry["licence"],
                     "source": entry["source"], **jobs.state(language)})
    return rows


def make_dictionaries_blueprint(jobs: DictionaryJobs | None = None) -> Blueprint:
    bp = Blueprint("owl_dictionaries", __name__)
    work = jobs or DictionaryJobs()

    @bp.get("/api/dictionaries")
    def dictionaries_list():
        return jsonify({"languages": languages_status(work)})

    @bp.post("/api/dictionaries/<language>")
    def dictionaries_install(language):
        if language not in dictionaries.LANGUAGES:
            return _error(f"unknown_language: {language}", 404)
        return jsonify({"started": work.start(language)})

    @bp.delete("/api/dictionaries/<language>")
    def dictionaries_remove(language):
        if language not in dictionaries.LANGUAGES:
            return _error(f"unknown_language: {language}", 404)
        if work.running(language):
            return _error("dictionary_running: wait until the download finishes", 409)
        try:
            work.remove(language)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        return jsonify({})

    return bp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_dictionaries_api.py tests/test_dictionaries.py -q`
Expected: `6 passed` in the new file, plan C's dictionary tests unchanged (0 failed). The test `test_install_makes_the_dictionary_work_without_a_restart` proves the cache refresh: `known("bud", "cs")` is True before and False right after the download.

- [ ] **Step 5: Commit**

```
git add owlocr/web/dictionaries_api.py tests/test_dictionaries_api.py
git commit -m "Add routes to download and remove the optional dictionaries" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Plug the routes into plan B's app

**Files:**
- Modify: `owlocr/web/server.py`, `owlocr/jobs/engines.py`, `tests/test_engines.py`
- Test: `tests/test_server_wizard.py`

**Interfaces:**
- Consumes: plan B's `create_app(runner, queue)`, its `X-Owl` guard, `/api/status`, `Runner(queue, engine_factory, settings_get)`, `owlocr.jobs.engines` (`WORKER_ENV`, `engine_installed`, `forget_installed`).
- Produces: both blueprints (wizard and engine routes, dictionary routes) registered on the real app; `engines.engine_installed()` answers with `bootstrap.is_installed()` (still cached 5 s, still `True` with `OWLOCR_ENGINE_WORKER`), because plan A's `default_engine()` does not check the model (plan A contract note).

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_wizard.py`:

```python
"""Plan D routes inside plan B's real app: registration, the X-Owl guard, and the installed state."""
import pytest

from owlocr.engine import bootstrap
from owlocr.jobs import engines
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web.server import create_app

H = {"X-Owl": "1"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)
    queue = JobQueue(tmp_path / "queue.json")
    runner = Runner(queue, lambda: None, dict)
    client = create_app(runner, queue).test_client()
    engines.forget_installed()
    yield client, runner
    runner.shutdown()
    engines.forget_installed()


def test_wizard_routes_are_registered(app):
    client, _ = app
    probe = client.get("/api/wizard/probe")
    assert probe.status_code == 200
    assert probe.get_json()["tier"]["name"] in ("gpu_full", "gpu_reduced", "cpu", "unsupported")
    assert client.get("/api/wizard/progress").get_json() == {"events": [], "running": False, "error": None}
    languages = client.get("/api/dictionaries").get_json()["languages"]
    assert [d["language"] for d in languages] == ["cs", "en"]


def test_wizard_and_engine_posts_need_the_owl_header(app):
    client, _ = app
    for path in ("/api/wizard/cancel", "/api/wizard/install", "/api/engine/remove", "/api/engine/verify",
                 "/api/dictionaries/cs"):
        assert client.post(path).status_code == 403, path
    assert client.delete("/api/dictionaries/cs").status_code == 403
    assert client.post("/api/wizard/cancel", headers=H).status_code == 200


def test_status_follows_bootstrap_is_installed(app, monkeypatch):
    client, _ = app
    monkeypatch.setattr(bootstrap, "is_installed", lambda: True)
    engines.forget_installed()
    assert client.get("/api/status").get_json()["installed"] is True
    monkeypatch.setattr(bootstrap, "is_installed", lambda: False)
    engines.forget_installed()
    assert client.get("/api/status").get_json()["installed"] is False


def test_remove_stops_the_engine_first_and_refreshes_status(app, monkeypatch):
    client, runner = app
    calls = []
    monkeypatch.setattr(runner, "stop_engine", lambda: calls.append("stop"))
    monkeypatch.setattr(bootstrap, "remove_engine", lambda: calls.append("remove"))
    monkeypatch.setattr(bootstrap, "is_installed", lambda: True)
    engines.engine_installed()                         # cache "installed"
    monkeypatch.setattr(bootstrap, "is_installed", lambda: False)
    assert client.post("/api/engine/remove", headers=H).status_code == 200
    assert calls == ["stop", "remove"]
    assert client.get("/api/status").get_json()["installed"] is False


def test_verify_answers_through_the_app(app, monkeypatch):
    client, _ = app
    monkeypatch.setattr("owlocr.engine.store.verify", lambda engine_id="unlimited_ocr": {})
    assert client.post("/api/engine/verify", headers=H).get_json() == {"problems": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_server_wizard.py -q`
Expected: `5 failed`: the routes answer 404 (plan B's guard already answers 403 to the POSTs and DELETEs without the header, so the header test fails only at its last line with `assert 404 == 200`), and the status test fails with `assert False is True` or with the old `default_engine` answer.

- [ ] **Step 3: Write minimal implementation**

In `owlocr/web/server.py` add the import next to plan B's other `owlocr` imports:

```python
from owlocr.web.dictionaries_api import make_dictionaries_blueprint
from owlocr.web.wizard_api import make_blueprint
```

and, inside `create_app`, directly above its final line `    return app`, add:

```python
    app.register_blueprint(make_blueprint(runner))
    app.register_blueprint(make_dictionaries_blueprint())
```

In `owlocr/jobs/engines.py` add the import next to the other `owlocr` imports:

```python
from owlocr.engine import bootstrap
```

and replace the whole function `engine_installed` with:

```python
def engine_installed() -> bool:
    """True when the engine is installed: bootstrap.is_installed() checks install.json against
    the app's pins, the venv and the model (sizes only, no network). OWLOCR_ENGINE_WORKER still
    counts as installed. Cached for 5 s because the UI asks every second."""
    now = time.monotonic()
    if now - _cache["at"] < _CACHE_S:
        return _cache["value"]
    if os.environ.get(WORKER_ENV):
        value = True
    else:
        try:
            value = bootstrap.is_installed()
        except Exception:  # an unreadable install record counts as not installed
            value = False
    _cache.update(at=now, value=value)
    return value
```

`default_engine` stays imported in `engines.py`; `engine_factory()` still uses it.

In `tests/test_engines.py` (plan B) replace the whole test `test_answer_is_cached_until_forgotten` with this version, which counts calls of the new check instead of `default_engine`:

```python
def test_answer_is_cached_until_forgotten(monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)
    calls = []

    def fine():
        calls.append(1)
        return True
    monkeypatch.setattr(engines.bootstrap, "is_installed", fine)
    engines.forget_installed()
    assert engines.engine_installed() and engines.engine_installed()
    assert len(calls) == 1
    engines.forget_installed()
    engines.engine_installed()
    assert len(calls) == 2
    engines.forget_installed()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_server_wizard.py tests/test_engines.py tests/test_server.py -q`
Expected: all pass (`5 passed` from the new file, plan B's files unchanged in count, 0 failed).

- [ ] **Step 5: Commit**

```
git add owlocr/web/server.py owlocr/jobs/engines.py tests/test_engines.py tests/test_server_wizard.py
git commit -m "Register wizard, engine and dictionary routes and base the installed state on bootstrap" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 20: The self-test page

**Files:**
- Create: `owlocr/web/static/selftest.png` (a byte copy of `tests/fixtures/pages/01_letter_clean.png`)
- Test: `tests/test_selftest_page.py`

**Interfaces:**
- Consumes: plan A's fixtures `tests/fixtures/pages/01_letter_clean.png` and `.gt.txt` and the spike outputs `tests/fixtures/raw/01_letter_clean.gundam.raw.txt` and `.base.raw.txt` (constants `PAGES`, `RAW`, `REPO` of `tests/conftest.py`); `install_kit.SELFTEST_WORDS`, `SELFTEST_MIN_WORDS`; `stages.selftest_words_found`.
- Produces: the bundled page read by the `selftest` stage (`SELFTEST_IMAGE_REL = "owlocr/web/static/selftest.png"`). Bundling the generated page is simpler and more predictable than drawing one at install time; it is a 2480 × 3508 px A4 letter at 300 dpi, 212 KB. All five expected words were found in the spike's Quality and Fast outputs of this page.

- [ ] **Step 1: Write the failing test**

Create `tests/test_selftest_page.py`:

```python
from owlocr.engine import install_kit as kit
from owlocr.engine import stages
from tests.conftest import PAGES, RAW, REPO


def test_selftest_page_is_the_letter_fixture():
    bundled = REPO / "owlocr" / "web" / "static" / "selftest.png"
    assert bundled.read_bytes() == (PAGES / "01_letter_clean.png").read_bytes()


def test_expected_words_are_on_the_page():
    truth = (PAGES / "01_letter_clean.gt.txt").read_text(encoding="utf-8")
    assert all(word in truth for word in kit.SELFTEST_WORDS)


def test_both_modes_found_the_words_in_the_spike():
    for mode in ("gundam", "base"):
        raw = (RAW / f"01_letter_clean.{mode}.raw.txt").read_text(encoding="utf-8")
        assert len(stages.selftest_words_found(raw)) >= kit.SELFTEST_MIN_WORDS, mode
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_selftest_page.py -q`
Expected: `1 failed` (`FileNotFoundError` for `owlocr\web\static\selftest.png`), `2 passed`.

- [ ] **Step 3: Write minimal implementation**

```
Copy-Item tests\fixtures\pages\01_letter_clean.png owlocr\web\static\selftest.png
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_selftest_page.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/web/static/selftest.png tests/test_selftest_page.py
git commit -m "Bundle the self-test page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 21: Wizard strings in Czech and English

**Files:**
- Create: `owlocr/web/static/wizard_i18n.js`
- Test: `tests/test_wizard_strings.py`

**Interfaces:**
- Consumes: plan B's `window.OWL_STRINGS = {cs: {...}, en: {...}}` (loaded before this file) and `window.OwlI18n.t(key, vars)` (falls back to English, then to the key; `{name}` placeholders).
- Produces: `wz_`-prefixed snake_case keys (plan B's naming scheme) merged into `window.OWL_STRINGS.cs` and `.en`, including the dictionary step and the Settings Dictionaries section (`wz_dict_*`). The block between `/*WIZARD-STRINGS-BEGIN*/` and `/*WIZARD-STRINGS-END*/` is strict JSON so the tests can read it. Families used with computed names: `wz_step_<step>` (including `dicts`), `wz_stage_<stage>`, `wz_state_<state>` (including `paused`), `wz_tier_<tier>`, `wz_tier_desc_<tier>`, `wz_speed_<tier>`, `wz_reason_<reason>`, `wz_dict_lang_<language>`, `wz_error_<code>`. Every value is non-empty (plan B's string test demands it), so there is no key for the reason `ok`.

The error test collects every error code the Python side can send (`BootstrapError("<code>: ...")`, `LocationError("<code>: ...")`, `_error("<code>: ...")`, and the `["error"] = f"<code>: ..."` of the dictionary jobs) and demands a message for each.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wizard_strings.py`:

```python
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from owlocr import hardware
from owlocr.engine import bootstrap

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "owlocr" / "web" / "static"
PY_SOURCES = [REPO / "owlocr" / "engine" / n for n in ("bootstrap.py", "stages.py", "relocate.py")] + \
             [REPO / "owlocr" / "web" / n for n in ("wizard_api.py", "dictionaries_api.py")]

STEPS = ("welcome", "hardware", "location", "install", "selftest", "dicts", "done")
STATES = ("pending", "start", "progress", "done", "skipped", "failed", "paused")
TIERS = ("gpu_full", "gpu_reduced", "cpu", "unsupported")
REASONS = ("driver_too_old", "gpu_too_old", "vram_too_small", "no_nvidia_gpu", "ram_too_small")


def wizard_strings() -> dict:
    text = (STATIC / "wizard_i18n.js").read_text(encoding="utf-8")
    begin, end = "/*WIZARD-STRINGS-BEGIN*/", "/*WIZARD-STRINGS-END*/"
    start = text.index(begin) + len(begin)
    return json.loads(text[start:text.index(end, start)])


STRINGS = wizard_strings()


def placeholders(text):
    return set(re.findall(r"\{(\w+)\}", text))


def test_both_languages_have_the_same_non_empty_keys():
    assert set(STRINGS) == {"cs", "en"}
    assert set(STRINGS["cs"]) == set(STRINGS["en"])
    for table in STRINGS.values():
        for key, value in table.items():
            assert key.startswith("wz_") and value.strip(), key


def test_placeholders_match_between_languages():
    for key in STRINGS["cs"]:
        assert placeholders(STRINGS["cs"][key]) == placeholders(STRINGS["en"][key]), key


def test_reason_codes_cover_choose_tier():
    assert set(hardware._REASON_RANK) | {"ram_too_small"} == set(REASONS)


def test_every_error_code_raised_by_python_has_a_message():
    pattern = re.compile(r'(?:(?:BootstrapError|LocationError|_error)\(\s*|\["error"\]\s*=\s*)f?"([a-z_]+)[:"]')
    codes = set()
    for source in PY_SOURCES:
        codes |= set(pattern.findall(source.read_text(encoding="utf-8")))
    assert {"cancelled", "not_enough_space", "checksum_mismatch", "queue_running", "nested",
            "dictionary_failed", "dictionary_running"} <= codes
    assert sorted(c for c in codes if f"wz_error_{c}" not in STRINGS["en"]) == []


def test_every_dynamic_key_family_is_complete():
    families = [("wz_step_", STEPS), ("wz_stage_", bootstrap.STAGES), ("wz_state_", STATES),
                ("wz_tier_", TIERS), ("wz_tier_desc_", TIERS), ("wz_speed_", TIERS), ("wz_reason_", REASONS),
                ("wz_dict_lang_", ("cs", "en"))]
    for prefix, names in families:
        for name in names:
            assert prefix + name in STRINGS["en"], prefix + name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_wizard_strings.py -q`
Expected: collection error `FileNotFoundError: ... owlocr\web\static\wizard_i18n.js`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/web/static/wizard_i18n.js`:

```javascript
'use strict';
// Strings of the setup wizard (plan D), merged into window.OWL_STRINGS of i18n.js, so
// window.OwlI18n.t() finds them. The block between the markers must stay strict JSON: the
// tests read it with json.loads. Load this file after i18n.js and before wizard.js.
(function () {
  const WIZARD = /*WIZARD-STRINGS-BEGIN*/{
  "cs": {
    "wz_step": "Krok {n} z {total}",
    "wz_step_welcome": "Vítejte",
    "wz_step_hardware": "Počítač",
    "wz_step_location": "Umístění",
    "wz_step_install": "Instalace",
    "wz_step_selftest": "Zkouška",
    "wz_step_done": "Hotovo",
    "wz_step_dicts": "Slovníky",
    "wz_dict_heading": "Slovníky pro kontrolu pravopisu (doporučeno)",
    "wz_dict_intro": "Se slovníkem Owl OCR opraví typické chyby čtení (například ď a ť) a označí slova, která slovník nezná. Bez slovníku Owl OCR funguje také, jen tyto kontroly vynechá.",
    "wz_dict_source": "Slovníky se stahují zvlášť z projektu LibreOffice dictionaries a platí pro ně jejich vlastní licence. Kdykoli je můžete přidat nebo odebrat v Nastavení.",
    "wz_dict_item": "{language} – {size}, licence: {licence}",
    "wz_dict_lang_cs": "Čeština",
    "wz_dict_lang_en": "Angličtina",
    "wz_dict_installed": "nainstalován",
    "wz_dict_missing": "nenainstalován",
    "wz_dict_downloading": "stahuje se: {done} z {total}",
    "wz_dict_settings_heading": "Slovníky",
    "wz_dict_remove_confirm": "Odebrat slovník ({language})? Kontrola pravopisu pro tento jazyk se vypne.",
    "wz_btn_skip": "Přeskočit",
    "wz_btn_download": "Stáhnout vybrané",
    "wz_btn_install_dict": "Nainstalovat",
    "wz_btn_remove_dict": "Odebrat",
    "wz_error_dictionary_failed": "Slovník se nepodařilo stáhnout a nic nebylo nainstalováno. Zkontrolujte připojení a zkuste to znovu.",
    "wz_error_dictionary_running": "Počkejte, až stahování slovníku skončí.",
    "wz_error_unknown_language": "Pro tento jazyk slovník není.",
    "wz_btn_next": "Další",
    "wz_btn_back": "Zpět",
    "wz_btn_install": "Instalovat",
    "wz_btn_pause": "Pozastavit",
    "wz_btn_continue": "Pokračovat",
    "wz_btn_retry": "Zkusit znovu",
    "wz_btn_open_logs": "Otevřít záznamy",
    "wz_btn_choose_folder": "Vybrat jinou složku",
    "wz_btn_have_engine": "Engine už mám",
    "wz_btn_start_using": "Začít používat Owl OCR",
    "wz_welcome_heading": "Vítejte v Owl OCR",
    "wz_welcome_intro": "Owl OCR převádí skeny, fotky, snímky obrazovky a PDF na text. Čte je přímo ve vašem počítači, bez cloudu.",
    "wz_welcome_download": "Před prvním použitím je potřeba jednou stáhnout čtecí engine: asi 10 GB (PyTorch a model Unlimited-OCR). Na disku zabere asi 16 GB. Podle rychlosti připojení to trvá od 15 minut po několik hodin.",
    "wz_welcome_once": "Stahuje se jen jednou. Další spuštění už nic nestahují a fungují i bez internetu.",
    "wz_welcome_privacy": "Vaše dokumenty nikdy neopustí tento počítač. Internet se použije jen pro toto stažení (huggingface.co, modelscope.cn, download.pytorch.org, pypi.org, github.com).",
    "wz_hw_heading": "Váš počítač",
    "wz_hw_gpu": "Grafická karta",
    "wz_hw_no_gpu": "Nenalezena žádná grafická karta NVIDIA",
    "wz_hw_gpu_line": "{name}, {vram} GB paměti, ovladač {driver}",
    "wz_hw_ram": "Operační paměť",
    "wz_hw_tier": "Zvolený způsob čtení",
    "wz_hw_speed": "Očekávaná rychlost",
    "wz_hw_cpu_meanwhile": "Do té doby může Owl OCR číst procesorem, jen pomaleji.",
    "wz_hw_unsupported_help": "Owl OCR potřebuje grafickou kartu NVIDIA s alespoň 8 GB paměti, nebo počítač s alespoň 16 GB operační paměti.",
    "wz_hw_gpu_only": "Owl OCR 0.1 umí číst jen na grafické kartě NVIDIA s alespoň 8 GB paměti a s ovladačem 570.65 nebo novějším.",
    "wz_tier_gpu_full": "Grafická karta – plná kvalita",
    "wz_tier_gpu_reduced": "Grafická karta – úsporný režim",
    "wz_tier_cpu": "Jen procesor",
    "wz_tier_unsupported": "Nepodporováno",
    "wz_tier_desc_gpu_full": "Čte na grafické kartě. Výchozí režim je Kvalita.",
    "wz_tier_desc_gpu_reduced": "Čte na grafické kartě s 8 až 10 GB paměti. Výchozí režim je Rychlý, který potřebuje méně paměti.",
    "wz_tier_desc_cpu": "Čte procesorem. Funguje, ale je mnohem pomalejší než grafická karta. Výchozí režim je Rychlý.",
    "wz_tier_desc_unsupported": "Na tomto počítači Owl OCR číst nemůže.",
    "wz_speed_gpu_full": "asi 25 až 45 sekund na stránku knihy",
    "wz_speed_gpu_reduced": "asi 30 až 70 sekund na stránku knihy",
    "wz_speed_cpu": "neměřeno, odhadem 1 až 5 minut na stránku",
    "wz_speed_unsupported": "–",
    "wz_reason_driver_too_old": "Ovladač grafické karty je starý. Pro čtení na grafické kartě nainstalujte ovladač NVIDIA 570.65 nebo novější (máte {driver}).",
    "wz_reason_gpu_too_old": "Grafická karta je pro engine příliš stará (potřebná je řada RTX 20 nebo novější).",
    "wz_reason_vram_too_small": "Grafická karta má méně než 8 GB paměti a engine se do ní nevejde.",
    "wz_reason_no_nvidia_gpu": "Engine umí využít jen grafické karty NVIDIA.",
    "wz_reason_ram_too_small": "Pro čtení procesorem je potřeba alespoň 16 GB operační paměti.",
    "wz_loc_heading": "Kam uložit engine",
    "wz_loc_folder": "Složka pro data",
    "wz_loc_free": "Volné místo na tomto disku: {free}",
    "wz_loc_need": "Potřeba: asi {need}",
    "wz_loc_low": "Na tomto disku není dost místa. Vyberte jinou složku, třeba na jiném disku.",
    "wz_loc_env": "Složku určuje proměnná prostředí OWLOCR_HOME a tady ji změnit nelze.",
    "wz_loc_moving": "Přesouvám data…",
    "wz_loc_have_help": "Pokud už máte model Unlimited-OCR stažený (složku models\\unlimited_ocr nebo složku, která ji obsahuje), vyberte ji tlačítkem Engine už mám. Soubory se zkontrolují a nebudou se stahovat znovu.",
    "wz_loc_copy": "Zkopírovat místo přesunutí (původní složka zůstane, zabere o 6,7 GB víc)",
    "wz_loc_checking": "Kontroluji soubory, může to trvat minutu…",
    "wz_loc_adopted": "Model nalezen a zkontrolován. Nebude se stahovat.",
    "wz_loc_type_path": "Zadejte úplnou cestu ke složce:",
    "wz_inst_heading": "Instalace enginu",
    "wz_inst_intro": "Instalaci můžete pozastavit a později v ní pokračovat, i po zavření aplikace. Co už je stažené, se znovu nestahuje.",
    "wz_inst_paused": "Pozastaveno. Pokračujte, až budete chtít.",
    "wz_inst_interrupted": "Instalace nebyla dokončena. Můžete pokračovat tam, kde skončila.",
    "wz_inst_failed": "Instalace se nezdařila.",
    "wz_inst_of": "{done} z {total}",
    "wz_inst_speed": "{rate}/s",
    "wz_stage_tools": "Stažení instalačního nástroje uv",
    "wz_stage_python": "Instalace Pythonu 3.11",
    "wz_stage_venv": "Příprava prostředí enginu",
    "wz_stage_torch": "Stažení knihovny PyTorch",
    "wz_stage_deps": "Instalace dalších knihoven",
    "wz_stage_model": "Stažení modelu Unlimited-OCR (6,7 GB)",
    "wz_stage_worker": "Kopírování skriptů enginu",
    "wz_stage_patch": "Úprava modelu pro procesor",
    "wz_stage_selftest": "Přečtení zkušební stránky",
    "wz_stage_mark": "Dokončení",
    "wz_state_pending": "čeká",
    "wz_state_start": "probíhá",
    "wz_state_progress": "probíhá",
    "wz_state_done": "hotovo",
    "wz_state_skipped": "už hotovo",
    "wz_state_failed": "chyba",
    "wz_state_paused": "pozastaveno",
    "wz_st_heading": "Zkouška proběhla",
    "wz_st_result": "Zkušební stránka se přečetla za {seconds} s.",
    "wz_st_estimate": "Očekávaná rychlost: {speed}.",
    "wz_st_unknown": "Doba čtení zkušební stránky není známa.",
    "wz_done_heading": "Owl OCR je připraven",
    "wz_done_body": "Přetáhněte do okna soubory nebo složky a Owl OCR je přečte.",
    "wz_done_note": "Text přečetl stroj. Než ho budete citovat, zkontrolujte ho.",
    "wz_eng_reinstall_confirm": "Prostředí enginu se sestaví znovu. Co je už stažené a v pořádku, se znovu nestahuje. Pokračovat?",
    "wz_eng_move_confirm": "Přesunout engine a data Owl OCR do složky {folder}?",
    "wz_eng_moved": "Přesunuto. Prostředí enginu se teď sestaví znovu, bez stahování.",
    "wz_error_cancelled": "Pozastaveno.",
    "wz_error_not_enough_space": "Na disku není dost místa.",
    "wz_error_download_failed": "Stažení se nepodařilo. Zkontrolujte připojení k internetu a zkuste to znovu.",
    "wz_error_checksum_mismatch": "Stažený soubor je poškozený nebo podvržený a byl smazán. Zkuste to znovu.",
    "wz_error_command_failed": "Instalační krok selhal. Podrobnosti jsou v záznamu install.log.",
    "wz_error_check_failed": "Krok doběhl, ale kontrola neprošla. Podrobnosti jsou v záznamu install.log.",
    "wz_error_model_download_failed": "Model se nepodařilo stáhnout z žádného zdroje. Zkuste to později.",
    "wz_error_patch_refused": "Kód modelu není ten, se kterým tato verze Owl OCR umí pracovat. Nic nebylo změněno.",
    "wz_error_not_enough_vram": "Na grafické kartě není dost volné paměti. Zavřete hry, střih videa nebo nahrávání obrazovky a zkuste to znovu.",
    "wz_error_selftest_failed": "Zkušební stránka se nepřečetla správně.",
    "wz_error_unsupported": "Tento počítač Owl OCR nepodporuje.",
    "wz_error_already_running": "Instalace už běží.",
    "wz_error_internal": "Neočekávaná chyba. Podrobnosti jsou v záznamu install.log.",
    "wz_error_install_running": "Počkejte, až instalace skončí, nebo ji pozastavte.",
    "wz_error_queue_running": "Nejdřív pozastavte frontu.",
    "wz_error_empty": "Nebyla vybrána žádná složka.",
    "wz_error_not_absolute": "Zadejte úplnou cestu, například D:\\OwlOCR.",
    "wz_error_not_a_folder": "Tato cesta vede k souboru, ne ke složce.",
    "wz_error_inside_install": "Data nemohou být ve složce programu.",
    "wz_error_not_writable": "Do této složky nelze zapisovat.",
    "wz_error_env_override": "Složku určuje proměnná prostředí OWLOCR_HOME.",
    "wz_error_nested": "Nová složka nesmí být uvnitř té staré ani naopak.",
    "wz_error_exists": "V cílové složce už data Owl OCR jsou.",
    "wz_error_move_failed": "Přesun se nepodařil; data zůstala na původním místě.",
    "wz_error_adopt_failed": "Ve vybrané složce není úplný a nepoškozený model.",
    "wz_error_remove_failed": "Některé soubory nešly smazat. Zavřete ostatní programy a zkuste to znovu.",
    "wz_error_unknown": "Něco se nepovedlo.",
    "wz_error_network": "Aplikace neodpovídá.",
    "wz_title": "První nastavení"
  },
  "en": {
    "wz_step": "Step {n} of {total}",
    "wz_step_welcome": "Welcome",
    "wz_step_hardware": "Computer",
    "wz_step_location": "Location",
    "wz_step_install": "Installation",
    "wz_step_selftest": "Self-test",
    "wz_step_done": "Done",
    "wz_step_dicts": "Dictionaries",
    "wz_dict_heading": "Spell-check dictionaries (recommended)",
    "wz_dict_intro": "With a dictionary Owl OCR repairs typical reading errors (such as ď and ť) and marks words the dictionary does not know. Owl OCR also works without one; it then skips these checks.",
    "wz_dict_source": "The dictionaries are downloaded separately from the LibreOffice dictionaries project and come under their own licences. You can add or remove them in Settings at any time.",
    "wz_dict_item": "{language} – {size}, licence: {licence}",
    "wz_dict_lang_cs": "Czech",
    "wz_dict_lang_en": "English",
    "wz_dict_installed": "installed",
    "wz_dict_missing": "not installed",
    "wz_dict_downloading": "downloading: {done} of {total}",
    "wz_dict_settings_heading": "Dictionaries",
    "wz_dict_remove_confirm": "Remove the dictionary ({language})? Spell checking for this language is switched off.",
    "wz_btn_skip": "Skip",
    "wz_btn_download": "Download selected",
    "wz_btn_install_dict": "Install",
    "wz_btn_remove_dict": "Remove",
    "wz_error_dictionary_failed": "The dictionary could not be downloaded and nothing was installed. Check your connection and try again.",
    "wz_error_dictionary_running": "Wait until the dictionary download finishes.",
    "wz_error_unknown_language": "There is no dictionary for this language.",
    "wz_btn_next": "Next",
    "wz_btn_back": "Back",
    "wz_btn_install": "Install",
    "wz_btn_pause": "Pause",
    "wz_btn_continue": "Continue",
    "wz_btn_retry": "Try again",
    "wz_btn_open_logs": "Open logs",
    "wz_btn_choose_folder": "Choose another folder",
    "wz_btn_have_engine": "I already have the engine",
    "wz_btn_start_using": "Start using Owl OCR",
    "wz_welcome_heading": "Welcome to Owl OCR",
    "wz_welcome_intro": "Owl OCR turns scans, photos, screenshots and PDFs into text. It reads them on your own computer, without any cloud service.",
    "wz_welcome_download": "Before the first use the reading engine has to be downloaded once: about 10 GB (PyTorch and the Unlimited-OCR model). It needs about 16 GB on disk. Depending on your connection this takes from 15 minutes to a few hours.",
    "wz_welcome_once": "This happens only once. Later starts download nothing and work without internet.",
    "wz_welcome_privacy": "Your documents never leave this computer. The internet is used only for this download (huggingface.co, modelscope.cn, download.pytorch.org, pypi.org, github.com).",
    "wz_hw_heading": "Your computer",
    "wz_hw_gpu": "Graphics card",
    "wz_hw_no_gpu": "No NVIDIA graphics card found",
    "wz_hw_gpu_line": "{name}, {vram} GB memory, driver {driver}",
    "wz_hw_ram": "System memory",
    "wz_hw_tier": "Chosen way of reading",
    "wz_hw_speed": "Expected speed",
    "wz_hw_cpu_meanwhile": "Until then Owl OCR can read with the processor, only more slowly.",
    "wz_hw_unsupported_help": "Owl OCR needs an NVIDIA graphics card with at least 8 GB of memory, or a computer with at least 16 GB of system memory.",
    "wz_hw_gpu_only": "Owl OCR 0.1 can only read on an NVIDIA graphics card with at least 8 GB of memory and driver 570.65 or newer.",
    "wz_tier_gpu_full": "Graphics card – full quality",
    "wz_tier_gpu_reduced": "Graphics card – memory-saving",
    "wz_tier_cpu": "Processor only",
    "wz_tier_unsupported": "Not supported",
    "wz_tier_desc_gpu_full": "Reads on the graphics card. The default mode is Quality.",
    "wz_tier_desc_gpu_reduced": "Reads on a graphics card with 8 to 10 GB of memory. The default mode is Fast, which needs less memory.",
    "wz_tier_desc_cpu": "Reads with the processor. It works, but it is much slower than a graphics card. The default mode is Fast.",
    "wz_tier_desc_unsupported": "Owl OCR cannot read on this computer.",
    "wz_speed_gpu_full": "about 25 to 45 seconds per book page",
    "wz_speed_gpu_reduced": "about 30 to 70 seconds per book page",
    "wz_speed_cpu": "not measured, roughly 1 to 5 minutes per page",
    "wz_speed_unsupported": "–",
    "wz_reason_driver_too_old": "The graphics driver is too old. To read on the graphics card, install NVIDIA driver 570.65 or newer (you have {driver}).",
    "wz_reason_gpu_too_old": "The graphics card is too old for the engine (an RTX 20 series card or newer is needed).",
    "wz_reason_vram_too_small": "The graphics card has less than 8 GB of memory, so the engine does not fit.",
    "wz_reason_no_nvidia_gpu": "The engine can only use NVIDIA graphics cards.",
    "wz_reason_ram_too_small": "Reading with the processor needs at least 16 GB of system memory.",
    "wz_loc_heading": "Where to keep the engine",
    "wz_loc_folder": "Data folder",
    "wz_loc_free": "Free space on this drive: {free}",
    "wz_loc_need": "Needed: about {need}",
    "wz_loc_low": "There is not enough space on this drive. Choose another folder, for example on another drive.",
    "wz_loc_env": "The folder is set by the OWLOCR_HOME environment variable and cannot be changed here.",
    "wz_loc_moving": "Moving the data…",
    "wz_loc_have_help": "If you already have the Unlimited-OCR model (a models\\unlimited_ocr folder, or a folder that contains one), choose it with I already have the engine. The files are checked and will not be downloaded again.",
    "wz_loc_copy": "Copy instead of move (keeps the original folder, uses 6.7 GB more)",
    "wz_loc_checking": "Checking the files, this can take a minute…",
    "wz_loc_adopted": "Model found and checked. It will not be downloaded.",
    "wz_loc_type_path": "Type the full path of the folder:",
    "wz_inst_heading": "Installing the engine",
    "wz_inst_intro": "You can pause the installation and continue later, even after closing the app. Whatever has been downloaded is not downloaded again.",
    "wz_inst_paused": "Paused. Continue whenever you like.",
    "wz_inst_interrupted": "The installation did not finish. You can continue where it stopped.",
    "wz_inst_failed": "The installation failed.",
    "wz_inst_of": "{done} of {total}",
    "wz_inst_speed": "{rate}/s",
    "wz_stage_tools": "Download the uv installer tool",
    "wz_stage_python": "Install Python 3.11",
    "wz_stage_venv": "Create the engine environment",
    "wz_stage_torch": "Download PyTorch",
    "wz_stage_deps": "Install the other libraries",
    "wz_stage_model": "Download the Unlimited-OCR model (6.7 GB)",
    "wz_stage_worker": "Copy the engine scripts",
    "wz_stage_patch": "Adapt the model to the processor",
    "wz_stage_selftest": "Read a test page",
    "wz_stage_mark": "Finish",
    "wz_state_pending": "waiting",
    "wz_state_start": "running",
    "wz_state_progress": "running",
    "wz_state_done": "done",
    "wz_state_skipped": "already done",
    "wz_state_failed": "failed",
    "wz_state_paused": "paused",
    "wz_st_heading": "Self-test passed",
    "wz_st_result": "The test page was read in {seconds} s.",
    "wz_st_estimate": "Expected speed: {speed}.",
    "wz_st_unknown": "The reading time of the test page is not known.",
    "wz_done_heading": "Owl OCR is ready",
    "wz_done_body": "Drag files or folders into the window and Owl OCR will read them.",
    "wz_done_note": "The text is read by a machine. Check it before you quote it.",
    "wz_eng_reinstall_confirm": "The engine environment will be rebuilt. Nothing that is already downloaded and intact is downloaded again. Continue?",
    "wz_eng_move_confirm": "Move the engine and Owl OCR's data to {folder}?",
    "wz_eng_moved": "Moved. The engine environment is now rebuilt, without downloading.",
    "wz_error_cancelled": "Paused.",
    "wz_error_not_enough_space": "Not enough disk space.",
    "wz_error_download_failed": "The download failed. Check your internet connection and try again.",
    "wz_error_checksum_mismatch": "The downloaded file is damaged or not genuine and was deleted. Try again.",
    "wz_error_command_failed": "An installation step failed. Details are in install.log.",
    "wz_error_check_failed": "A step finished but its check did not pass. Details are in install.log.",
    "wz_error_model_download_failed": "The model could not be downloaded from any source. Try again later.",
    "wz_error_patch_refused": "The model code is not the code this version of Owl OCR can work with. Nothing was changed.",
    "wz_error_not_enough_vram": "Not enough free graphics memory. Close games, video editors or screen recorders and try again.",
    "wz_error_selftest_failed": "The test page was not read correctly.",
    "wz_error_unsupported": "Owl OCR does not support this computer.",
    "wz_error_already_running": "The installation is already running.",
    "wz_error_internal": "Unexpected error. Details are in install.log.",
    "wz_error_install_running": "Wait until the installation finishes, or pause it.",
    "wz_error_queue_running": "Pause the queue first.",
    "wz_error_empty": "No folder was chosen.",
    "wz_error_not_absolute": "Enter a full path, for example D:\\OwlOCR.",
    "wz_error_not_a_folder": "This path is a file, not a folder.",
    "wz_error_inside_install": "The data cannot be inside the program folder.",
    "wz_error_not_writable": "This folder cannot be written to.",
    "wz_error_env_override": "The folder is set by the OWLOCR_HOME environment variable.",
    "wz_error_nested": "The new folder must not be inside the old one, or the other way round.",
    "wz_error_exists": "The target folder already contains Owl OCR data.",
    "wz_error_move_failed": "The move failed; the data stayed where it was.",
    "wz_error_adopt_failed": "The chosen folder does not contain a complete, undamaged model.",
    "wz_error_remove_failed": "Some files could not be deleted. Close other programs and try again.",
    "wz_error_unknown": "Something went wrong.",
    "wz_error_network": "The app does not respond.",
    "wz_title": "First-time setup"
  }
}/*WIZARD-STRINGS-END*/;
  Object.keys(WIZARD).forEach(function (lang) {
    window.OWL_STRINGS[lang] = Object.assign(window.OWL_STRINGS[lang] || {}, WIZARD[lang]);
  });
})();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_wizard_strings.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/web/static/wizard_i18n.js tests/test_wizard_strings.py
git commit -m "Add the wizard strings in Czech and English" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 22: The wizard screen, the dictionary step and the Settings engine and dictionary actions

**Files:**
- Create: `owlocr/web/static/wizard.js`, `owlocr/web/static/wizard.css`
- Modify: `owlocr/web/static/index.html`, `owlocr/web/static/app.js`, `owlocr/web/static/i18n.js` (all plan B)
- Test: `tests/test_wizard_strings.py` (append), `tests/test_wizard_integration.py`

**Interfaces:**
- Consumes: plan B's `index.html` (views `viewQueue`, `viewReview`, `viewSettings`, `viewAbout`, `viewWizard`; Settings buttons `btnVerify`, `btnReinstall`, `btnMove`, `btnRemoveEngine`; `confirmDlg`), `app.js` private helpers `api(method, path, body)` (sends `X-Owl: 1`, throws `Error(message)` with `.status`), `toast(message)`, `confirmDialog(text) -> Promise<bool>`, `showView(name)`, `engineAction(path, confirmKey)`; `window.OwlI18n.t`, `getLang`; `window.pywebview.api.pick_folder()` and `open_folder(path)` (plan B's Bridge); the routes of tasks 16–18.
- Produces: `window.OwlWizard = {init(deps), show(), render(), reinstall(), move(), renderDictionaries(container)}` where `deps = {api, toast, confirmDialog, showView}`.

The six steps of design 6.1, with the optional dictionary step (6) before Done:
1. **Welcome** – what happens, about 10 GB download, about 16 GB on disk, download once, privacy.
2. **Hardware** – each NVIDIA card with memory and driver, system memory, the chosen tier with its description and expected speed, the reason when the GPU cannot be used (with "until then the processor" for an old driver); on `unsupported` the Next button is disabled and the help text says what is needed (GPU-only wording when `cpu_tier_enabled` is false).
3. **Location** – data folder, free space, space needed (less when the model is already there), warning when too low, "Choose another folder" (hidden when `OWLOCR_HOME` fixes it), "I already have the engine" with the option "Copy instead of move", and Install.
4. **Install** – the ten stages with state, a progress bar with bytes, speed and the latest tool line, Pause (keeps everything downloaded) and Continue / Try again, Open logs, translated errors with details; after an app restart with an unfinished installation the wizard opens here with Continue.
5. **Self-test** – seconds of the test page from `install.json` and the expected speed of the tier.
6. **Dictionaries (optional)** – "Spell-check dictionaries (recommended)": Czech and English pre-ticked, each with its size and licence name from `GET /api/dictionaries`, a sentence that they come separately from the LibreOffice dictionaries project under their own licences and that the app works without them; "Skip" goes on without downloading, "Download selected" starts the downloads and shows their progress, a failure shows a translated message and nothing is installed. Already installed dictionaries are shown as installed.
7. **Done** – start using the app (shows the queue).

Settings gets a **Dictionaries** section below the engine buttons (`renderDictionaries`): each language with its size, licence and state (installed, not installed, downloading x of y, error) and an Install or Remove button; Remove asks for confirmation.

Polling: `GET /api/wizard/progress` every second while an installation runs, `GET /api/dictionaries` every second while a dictionary downloads. Language: the wizard re-renders when plan B's language switch changes `document.documentElement.lang`. Security: the wizard only builds DOM nodes and sets `textContent`; it never uses `innerHTML`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard_strings.py`:

```python
# ---- wizard.js (task 22) ----------------------------------------------------------------
JS = (STATIC / "wizard.js").read_text(encoding="utf-8")


def test_every_static_key_in_wizard_js_exists():
    used = set(re.findall(r"\bt\('(wz_[a-z_]*[a-z])'", JS))
    assert len(used) > 30
    assert sorted(used - set(STRINGS["en"])) == []


def test_wizard_js_uses_the_same_step_and_stage_lists():
    assert "const STEPS = ['welcome', 'hardware', 'location', 'install', 'selftest', 'dicts', 'done'];" in JS
    stages = ", ".join(f"'{s}'" for s in bootstrap.STAGES)
    assert f"const STAGES = [{stages}];" in JS


def test_no_html_injection_in_wizard_js():
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("name", ["wizard.js", "wizard_i18n.js"])
def test_scripts_parse(name):
    done = subprocess.run(["node", "--check", str(STATIC / name)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
```

Create `tests/test_wizard_integration.py`:

```python
"""The wizard is wired into plan B's page: markup, script order, app.js hooks, no placeholder left."""
import json

from tests.conftest import REPO

STATIC = REPO / "owlocr" / "web" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
I18N = (STATIC / "i18n.js").read_text(encoding="utf-8")


def test_wizard_view_and_dictionary_panel_are_empty_containers():
    assert '<section id="viewWizard" class="view" hidden></section>' in INDEX
    assert '<div id="dictSettings" class="wz-dicts-panel"></div>' in INDEX
    assert INDEX.index('id="btnRemoveEngine"') < INDEX.index('id="dictSettings"')


def test_scripts_and_stylesheet_are_loaded_in_order():
    order = ["static/i18n.js", "static/owl.js", "static/review.js", "static/wizard_i18n.js",
             "static/wizard.js", "static/app.js"]
    positions = [INDEX.index(f'<script src="{name}"></script>') for name in order]
    assert positions == sorted(positions)
    assert '<link rel="stylesheet" href="static/wizard.css">' in INDEX
    assert INDEX.rstrip().endswith("</script></body></html>")


def test_app_js_hands_its_helpers_to_the_wizard():
    assert "window.OwlWizard.init({ api: api, toast: toast, confirmDialog: confirmDialog, showView: showView });" in APP
    assert "if (name === 'wizard') window.OwlWizard.show();" in APP
    assert "window.OwlWizard.reinstall();" in APP and "window.OwlWizard.move();" in APP
    assert "if (name === 'settings') window.OwlWizard.renderDictionaries($('dictSettings'));" in APP


def test_placeholder_is_gone():
    for text in (INDEX, APP):
        assert "wizardToSettings" not in text and "wizardToQueue" not in text
    begin, end = "/*STRINGS-BEGIN*/", "/*STRINGS-END*/"
    table = json.loads(I18N[I18N.index(begin) + len(begin):I18N.index(end)])
    for lang in ("cs", "en"):
        assert not {"wizard_title", "wizard_text", "wizard_to_settings", "wizard_to_queue"} & set(table[lang])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_wizard_strings.py tests/test_wizard_integration.py -q`
Expected: collection error `FileNotFoundError: ... owlocr\web\static\wizard.js` for the strings file, and `4 failed` in the integration file (no wizard section and dictionary panel, no scripts, no `OwlWizard.init`, placeholder still present).

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/web/static/wizard.js`:

```javascript
'use strict';
// Owl OCR setup wizard (design 6.1, plus the optional dictionary step), the Settings actions
// Reinstall and Move (design 10.3) and the Settings section for the spell-check dictionaries.
// Renders into <section id="viewWizard">. app.js calls OwlWizard.init({...}) with its own api()
// helper (which sends the X-Owl header), toast(), confirmDialog() and showView(); showView('wizard')
// calls OwlWizard.show(). Text comes from wizard_i18n.js through window.OwlI18n.t; dynamic values
// are inserted with textContent only.
(function () {
  const STEPS = ['welcome', 'hardware', 'location', 'install', 'selftest', 'dicts', 'done'];
  const STAGES = ['tools', 'python', 'venv', 'torch', 'deps', 'model', 'worker', 'patch', 'selftest', 'mark'];
  const POLL_MS = 1000;
  const MODEL_BYTES = 7516192768;      // 7 GiB: space no longer needed once the model is present

  const W = {
    deps: null, root: null, step: 'welcome', probe: null, progress: null, timer: null,
    busy: '', notice: null, speed: { stage: null, bytes: 0, time: 0, rate: 0 },
    dicts: null, dictChoice: { cs: true, en: true }, dictTimer: null, dictPanel: null
  };

  function t(key, vars) { return window.OwlI18n.t(key, vars); }
  function lang() { return window.OwlI18n.getLang(); }
  function locale() { return lang() === 'cs' ? 'cs-CZ' : 'en-US'; }

  function h(tag, attrs) {
    const node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (name) {
      const value = attrs[name];
      if (name === 'onclick') node.addEventListener('click', value);
      else if (name === 'text') node.textContent = value;
      else if (name === 'disabled' || name === 'checked') node[name] = !!value;
      else if (value !== null && value !== undefined) node.setAttribute(name, value);
    });
    Array.prototype.slice.call(arguments, 2).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }

  function api(method, path, body) { return W.deps.api(method, path, body); }

  function errorKey(message) {
    const code = String(message || 'unknown').split(':')[0].trim();
    const key = 'wz_error_' + code;
    return t(key) === key ? 'wz_error_unknown' : key;
  }

  function detailOf(message) {
    const text = String(message || '');
    const at = text.indexOf(':');
    return at >= 0 ? text.slice(at + 1).trim() : '';
  }

  function showError(err) {
    const message = (err && err.message) || String(err);
    W.notice = { kind: 'error', key: errorKey(message), detail: detailOf(message) };
  }

  function formatBytes(bytes) {
    const gb = bytes / 1073741824;
    if (gb >= 1) return gb.toLocaleString(locale(), { maximumFractionDigits: 1 }) + ' GB';
    return (bytes / 1048576).toLocaleString(locale(), { maximumFractionDigits: 1 }) + ' MB';
  }

  function hasBridge() { return !!(window.pywebview && window.pywebview.api); }

  function pickFolder() {
    if (hasBridge()) return window.pywebview.api.pick_folder();
    return Promise.resolve(window.prompt(t('wz_loc_type_path')) || null);
  }

  function openLogs() {
    if (W.probe && hasBridge()) window.pywebview.api.open_folder(W.probe.logs_dir);
  }

  function loadProbe() {
    return api('GET', '/api/wizard/probe').then(function (data) { W.probe = data; return data; });
  }

  // ---- installation progress -------------------------------------------------------
  function stopPolling() {
    if (W.timer) { clearTimeout(W.timer); W.timer = null; }
  }

  function finishedAll(events) {
    return (events || []).some(function (e) {
      return e.stage === 'mark' && (e.state === 'done' || e.state === 'skipped');
    });
  }

  function updateSpeed() {
    const events = (W.progress && W.progress.events) || [];
    const last = events[events.length - 1];
    const s = W.speed;
    if (!last || last.state !== 'progress' || !last.total) { s.rate = 0; return; }
    const now = Date.now();
    if (s.stage === last.stage && last.done >= s.bytes && now > s.time) {
      const rate = (last.done - s.bytes) * 1000 / (now - s.time);
      s.rate = s.rate ? s.rate * 0.7 + rate * 0.3 : rate;
    } else {
      s.rate = 0;
    }
    s.stage = last.stage; s.bytes = last.done; s.time = now;
  }

  function poll() {
    stopPolling();
    api('GET', '/api/wizard/progress').then(function (data) {
      W.progress = data;
      updateSpeed();
      if (data.running) {
        W.timer = setTimeout(poll, POLL_MS);
        return null;
      }
      if (!data.error && finishedAll(data.events)) {
        return loadProbe().then(function () { W.step = 'selftest'; });
      }
      return null;
    }).catch(function (err) {
      showError(err);
      W.timer = setTimeout(poll, POLL_MS * 3);
    }).then(render);
  }

  function startInstall() {
    W.notice = null;
    W.progress = { events: [], running: true, error: null };
    W.step = 'install';
    render();
    api('POST', '/api/wizard/install').then(poll).catch(function (err) { showError(err); render(); });
  }

  function pauseInstall() {
    api('POST', '/api/wizard/cancel').catch(function () { return null; }).then(poll);
  }

  // ---- screens -----------------------------------------------------------------------
  function go(next) { W.notice = null; W.step = next; render(); }

  function button(label, onclick, opts) {
    const o = opts || {};
    return h('button', { type: 'button', 'class': o.primary ? 'primary' : null,
                         disabled: o.disabled || !!W.busy, onclick: onclick, text: label });
  }

  function buttons() {
    return h.apply(null, ['div', { 'class': 'row wz-buttons' }].concat(Array.prototype.slice.call(arguments)));
  }

  function header() {
    const index = STEPS.indexOf(W.step);
    return h('div', { 'class': 'wz-header' },
      h('h2', { text: t('wz_title') }),
      h('span', { 'class': 'wz-steps', text: t('wz_step', { n: index + 1, total: STEPS.length }) + ' · ' +
                                             t('wz_step_' + W.step) }));
  }

  function noticeBox() {
    if (!W.notice) return null;
    return h('div', { 'class': 'wz-notice wz-' + W.notice.kind, role: W.notice.kind === 'error' ? 'alert' : 'status' },
      h('div', { text: t(W.notice.key) }),
      W.notice.detail ? h('div', { 'class': 'wz-detail', text: W.notice.detail }) : null);
  }

  function screenWelcome() {
    return [h('h3', { text: t('wz_welcome_heading') }),
      h('p', { text: t('wz_welcome_intro') }),
      h('p', { text: t('wz_welcome_download') }),
      h('p', { text: t('wz_welcome_once') }),
      h('p', { 'class': 'wz-muted', text: t('wz_welcome_privacy') }),
      buttons(button(t('wz_btn_next'), function () { go('hardware'); }, { primary: true }))];
  }

  function screenHardware() {
    const p = W.probe;
    const tier = p.tier;
    const gpuLines = p.gpus.length ? p.gpus.map(function (g) {
      return h('div', { text: t('wz_hw_gpu_line', { name: g.name, driver: g.driver,
        vram: (g.vram_total_mib / 1024).toLocaleString(locale(), { maximumFractionDigits: 0 }) }) });
    }) : [h('div', { text: t('wz_hw_no_gpu') })];
    const driver = p.gpus.length ? p.gpus[0].driver : '';
    const reason = tier.reason && tier.reason !== 'ok' ? t('wz_reason_' + tier.reason, { driver: driver }) : '';
    const unsupported = tier.name === 'unsupported';
    return [h('h3', { text: t('wz_hw_heading') }),
      h('dl', { 'class': 'wz-facts' },
        h('dt', { text: t('wz_hw_gpu') }), h.apply(null, ['dd', {}].concat(gpuLines)),
        h('dt', { text: t('wz_hw_ram') }), h('dd', { text: formatBytes(p.ram_mib * 1048576) }),
        h('dt', { text: t('wz_hw_tier') }),
        h('dd', {}, h('strong', { text: t('wz_tier_' + tier.name) }), h('div', { text: t('wz_tier_desc_' + tier.name) })),
        h('dt', { text: t('wz_hw_speed') }), h('dd', { text: t('wz_speed_' + tier.name) })),
      reason ? h('p', { 'class': 'wz-warning', text: reason }) : null,
      tier.name === 'cpu' && tier.reason === 'driver_too_old' ? h('p', { text: t('wz_hw_cpu_meanwhile') }) : null,
      unsupported ? h('p', { 'class': 'wz-warning',
                             text: p.cpu_tier_enabled ? t('wz_hw_unsupported_help') : t('wz_hw_gpu_only') }) : null,
      buttons(button(t('wz_btn_back'), function () { go('welcome'); }),
              button(t('wz_btn_next'), function () { go('location'); }, { primary: true, disabled: unsupported }))];
  }

  function chooseFolder() {
    pickFolder().then(function (folder) {
      if (!folder) return null;
      W.busy = t('wz_loc_moving'); W.notice = null; render();
      return api('POST', '/api/wizard/location', { path: folder }).then(loadProbe);
    }).catch(showError).then(function () { W.busy = ''; render(); });
  }

  function haveEngine() {
    const box = document.getElementById('wzCopy');
    const copy = !!(box && box.checked);
    pickFolder().then(function (folder) {
      if (!folder) return null;
      W.busy = t('wz_loc_checking'); W.notice = null; render();
      return api('POST', '/api/wizard/adopt', { path: folder, copy: copy }).then(function () {
        W.notice = { kind: 'info', key: 'wz_loc_adopted', detail: '' };
        return loadProbe();
      });
    }).catch(showError).then(function () { W.busy = ''; render(); });
  }

  function screenLocation() {
    const p = W.probe;
    const need = p.install ? 0 : Math.max(0, p.required_bytes - (p.model_ready ? MODEL_BYTES : 0));
    return [h('h3', { text: t('wz_loc_heading') }),
      h('dl', { 'class': 'wz-facts' },
        h('dt', { text: t('wz_loc_folder') }), h('dd', { 'class': 'wz-path', text: p.data_root }),
        h('dt', { text: t('wz_loc_free', { free: formatBytes(p.free_bytes) }) }),
        h('dd', { text: t('wz_loc_need', { need: formatBytes(need) }) })),
      p.free_bytes < need ? h('p', { 'class': 'wz-warning', text: t('wz_loc_low') }) : null,
      p.env_override ? h('p', { 'class': 'wz-muted', text: t('wz_loc_env') }) : null,
      h('p', { 'class': 'wz-muted', text: t('wz_loc_have_help') }),
      h('label', { 'class': 'wz-check' }, h('input', { type: 'checkbox', id: 'wzCopy' }), ' ' + t('wz_loc_copy')),
      W.busy ? h('p', { 'class': 'wz-busy', text: W.busy }) : null,
      buttons(button(t('wz_btn_back'), function () { go('hardware'); }),
              p.env_override ? null : button(t('wz_btn_choose_folder'), chooseFolder),
              button(t('wz_btn_have_engine'), haveEngine),
              button(t('wz_btn_install'), startInstall, { primary: true }))];
  }

  function stageList() {
    const latest = {};
    ((W.progress && W.progress.events) || []).forEach(function (e) { latest[e.stage] = e; });
    return h.apply(null, ['ol', { 'class': 'wz-stages' }].concat(STAGES.map(function (stage) {
      const e = latest[stage];
      const state = !e ? 'pending' : (e.state === 'failed' && e.message === 'cancelled' ? 'paused' : e.state);
      let detail = null;
      if (e && (state === 'progress' || state === 'start')) {
        const parts = [];
        if (e.total > 0) {
          const bytes = e.total > 100000;
          parts.push(t('wz_inst_of', { done: bytes ? formatBytes(e.done) : e.done,
                                       total: bytes ? formatBytes(e.total) : e.total }));
          if (bytes && W.speed.stage === stage && W.speed.rate > 0) {
            parts.push(t('wz_inst_speed', { rate: formatBytes(W.speed.rate) }));
          }
        }
        if (e.message && e.message !== 'checking') parts.push(e.message);
        detail = h('div', { 'class': 'wz-stage-detail' },
          e.total > 0 ? h('progress', { max: String(e.total), value: String(Math.min(e.done, e.total)) }) : null,
          h('span', { text: parts.join(' · ') }));
      }
      return h('li', { 'class': 'wz-stage wz-' + state },
        h('span', { 'class': 'wz-stage-name', text: t('wz_stage_' + stage) }),
        h('span', { 'class': 'wz-stage-state', text: t('wz_state_' + state) }), detail);
    })));
  }

  function screenInstall() {
    const running = !!(W.progress && W.progress.running);
    const error = W.progress && W.progress.error;
    const paused = !!error && errorKey(error) === 'wz_error_cancelled';
    const nothingYet = !(W.progress && W.progress.events && W.progress.events.length);
    const lines = [h('h3', { text: t('wz_inst_heading') }), h('p', { 'class': 'wz-muted', text: t('wz_inst_intro') })];
    if (!running && !error && W.probe && W.probe.interrupted && nothingYet) lines.push(h('p', { text: t('wz_inst_interrupted') }));
    if (paused) {
      lines.push(h('p', { text: t('wz_inst_paused') }));
    } else if (error) {
      lines.push(h('div', { 'class': 'wz-notice wz-error', role: 'alert' },
        h('div', { text: t('wz_inst_failed') + ' ' + t(errorKey(error)) }),
        h('div', { 'class': 'wz-detail', text: detailOf(error) })));
    }
    lines.push(stageList());
    lines.push(buttons(
      running ? button(t('wz_btn_pause'), pauseInstall) : null,
      running ? null : button(error && !paused ? t('wz_btn_retry') : t('wz_btn_continue'), startInstall, { primary: true }),
      button(t('wz_btn_open_logs'), openLogs)));
    return lines;
  }

  function screenSelftest() {
    const record = W.probe && W.probe.install;
    const seconds = record ? record.selftest_seconds : null;
    const tierName = record ? record.tier : W.probe.tier.name;
    return [h('h3', { text: t('wz_st_heading') }),
      h('p', { text: seconds !== null && seconds !== undefined ?
        t('wz_st_result', { seconds: Number(seconds).toLocaleString(locale(), { maximumFractionDigits: 1 }) }) :
        t('wz_st_unknown') }),
      h('p', { text: t('wz_st_estimate', { speed: t('wz_speed_' + tierName) }) }),
      buttons(button(t('wz_btn_next'), function () { go('dicts'); }, { primary: true }))];
  }

  // ---- dictionaries (optional step and Settings) ---------------------------------------
  function loadDicts() {
    return api('GET', '/api/dictionaries').then(function (data) { W.dicts = data.languages; return W.dicts; });
  }

  function anyDictRunning() {
    return (W.dicts || []).some(function (d) { return d.running; });
  }

  function pollDicts() {
    if (W.dictTimer) { clearTimeout(W.dictTimer); W.dictTimer = null; }
    loadDicts().then(function () {
      if (anyDictRunning()) W.dictTimer = setTimeout(pollDicts, POLL_MS);
    }).catch(showError).then(function () {
      if (W.step === 'dicts' && !W.root.hidden) render();
      if (W.dictPanel) renderDictPanel();
    });
  }

  function dictLabel(d) {
    return t('wz_dict_item', { language: t('wz_dict_lang_' + d.language), size: formatBytes(d.size),
                               licence: d.licence });
  }

  function dictState(d) {
    if (d.running) {
      return t('wz_dict_downloading', { done: formatBytes(d.done), total: formatBytes(d.total || d.size) });
    }
    if (d.installed) return t('wz_dict_installed');
    return t('wz_dict_missing');
  }

  function dictError(d) {
    return d.error ? h('div', { 'class': 'wz-notice wz-error', role: 'alert' },
      h('div', { text: t(errorKey(d.error)) }), h('div', { 'class': 'wz-detail', text: detailOf(d.error) })) : null;
  }

  function installDicts(languages) {
    return Promise.all(languages.map(function (language) {
      return api('POST', '/api/dictionaries/' + language);
    })).catch(showError).then(pollDicts);
  }

  function screenDicts() {
    if (W.dicts === null) { pollDicts(); return [h('h3', { text: t('wz_dict_heading') })]; }
    const rows = W.dicts.map(function (d) {
      const box = h('input', { type: 'checkbox', checked: d.installed || W.dictChoice[d.language],
                               disabled: d.installed || d.running });
      box.addEventListener('change', function () { W.dictChoice[d.language] = box.checked; });
      return h('li', { 'class': 'wz-dict' },
        h('label', {}, box, ' ' + dictLabel(d)),
        h('span', { 'class': 'wz-stage-state', text: dictState(d) }),
        d.running ? h('progress', { max: String(d.total || d.size), value: String(d.done) }) : null,
        dictError(d));
    });
    const wanted = W.dicts.filter(function (d) { return !d.installed && W.dictChoice[d.language]; })
      .map(function (d) { return d.language; });
    const running = anyDictRunning();
    return [h('h3', { text: t('wz_dict_heading') }),
      h('p', { text: t('wz_dict_intro') }),
      h('p', { 'class': 'wz-muted', text: t('wz_dict_source') }),
      h.apply(null, ['ul', { 'class': 'wz-dicts' }].concat(rows)),
      buttons(button(t('wz_btn_skip'), function () { go('done'); }, { disabled: running }),
              wanted.length ? button(t('wz_btn_download'), function () { installDicts(wanted); },
                                     { primary: true, disabled: running })
                            : button(t('wz_btn_next'), function () { go('done'); },
                                     { primary: true, disabled: running }))];
  }

  function renderDictPanel() {
    const panel = W.dictPanel;
    if (!panel || !W.dicts) return;
    panel.textContent = '';
    const rows = W.dicts.map(function (d) {
      const action = d.installed
        ? h('button', { type: 'button', disabled: d.running, text: t('wz_btn_remove_dict'), onclick: function () {
            W.deps.confirmDialog(t('wz_dict_remove_confirm', { language: t('wz_dict_lang_' + d.language) }))
              .then(function (yes) {
                if (!yes) return null;
                return api('DELETE', '/api/dictionaries/' + d.language).then(pollDicts);
              }).catch(function (err) { W.deps.toast(t(errorKey(err.message))); });
          } })
        : h('button', { type: 'button', disabled: d.running, text: t('wz_btn_install_dict'),
                        onclick: function () { installDicts([d.language]); } });
      return h('li', { 'class': 'wz-dict' },
        h('span', { text: dictLabel(d) }),
        h('span', { 'class': 'wz-stage-state', text: dictState(d) }),
        action, dictError(d));
    });
    panel.appendChild(h('h2', { text: t('wz_dict_settings_heading') }));
    panel.appendChild(h('p', { 'class': 'wz-muted', text: t('wz_dict_intro') + ' ' + t('wz_dict_source') }));
    panel.appendChild(h.apply(null, ['ul', { 'class': 'wz-dicts' }].concat(rows)));
  }

  function renderDictionaries(container) {
    W.dictPanel = container;
    pollDicts();
  }

  function screenDone() {
    return [h('h3', { text: t('wz_done_heading') }),
      h('p', { text: t('wz_done_body') }),
      h('p', { 'class': 'wz-muted', text: t('wz_done_note') }),
      buttons(button(t('wz_btn_start_using'), finish, { primary: true }))];
  }

  function finish() {
    stopPolling();
    W.deps.showView('queue');
  }

  const SCREENS = { welcome: screenWelcome, hardware: screenHardware, location: screenLocation,
                    install: screenInstall, selftest: screenSelftest, dicts: screenDicts,
                    done: screenDone };

  function render() {
    if (!W.root) return;
    W.root.textContent = '';
    const body = W.probe || W.step === 'welcome' ? SCREENS[W.step]() : [];
    W.root.appendChild(h.apply(null, ['div', { 'class': 'wz' }, header(), noticeBox()].concat(body)));
  }

  // ---- public API ------------------------------------------------------------------
  function init(deps) {
    W.deps = deps;
    W.root = document.getElementById('viewWizard');
    new MutationObserver(function () { if (!W.root.hidden) render(); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  }

  function show() {
    W.notice = null;
    return Promise.all([loadProbe(), api('GET', '/api/wizard/progress')]).then(function (both) {
      W.progress = both[1];
      if (W.probe.installed) W.step = 'done';
      else if (W.progress.running || W.probe.interrupted) W.step = 'install';
      else if (['selftest', 'dicts', 'done'].indexOf(W.step) >= 0) W.step = 'welcome';
      render();
      if (W.progress.running) poll();
    }).catch(function (err) { showError(err); render(); });
  }

  function reinstall() {
    return W.deps.confirmDialog(t('wz_eng_reinstall_confirm')).then(function (yes) {
      if (!yes) return null;
      return api('POST', '/api/engine/reinstall').then(function () {
        W.step = 'location';
        W.deps.showView('wizard');
      });
    }).catch(function (err) { W.deps.toast(t(errorKey(err.message))); });
  }

  function move() {
    return pickFolder().then(function (folder) {
      if (!folder) return null;
      return W.deps.confirmDialog(t('wz_eng_move_confirm', { folder: folder })).then(function (yes) {
        if (!yes) return null;
        W.deps.toast(t('wz_loc_moving'));
        return api('POST', '/api/engine/move', { path: folder }).then(function () {
          W.deps.toast(t('wz_eng_moved'));
          W.step = 'install';
          W.deps.showView('wizard');
        });
      });
    }).catch(function (err) { W.deps.toast(t(errorKey(err.message))); });
  }

  window.OwlWizard = { init: init, show: show, render: render, reinstall: reinstall, move: move,
                       renderDictionaries: renderDictionaries };
})();
```

Create `owlocr/web/static/wizard.css`:

```css
/* Setup wizard (plan D). Uses the colour variables of style.css, so both themes work. */
.wz { max-width: 760px; padding: 4px 0 24px; line-height: 1.5; }
.wz-header { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 14px; }
.wz-header h2 { font-size: 1.1rem; margin: 0; flex: 1 1 auto; }
.wz-steps { color: var(--muted); font-size: 0.8rem; }
.wz h3 { font-size: 1rem; margin: 0 0 10px; }
.wz p { margin: 0 0 10px; max-width: 70ch; }
.wz-muted { color: var(--muted); font-size: 0.87rem; }
.wz-warning { color: var(--warn); border-left: 4px solid var(--warn); padding: 6px 10px; background: var(--panel-2); }
.wz-facts { display: grid; grid-template-columns: max-content 1fr; gap: 6px 18px; margin: 0 0 12px; }
.wz-facts dt { font-weight: 600; }
.wz-facts dd { margin: 0; }
.wz-path { font-family: Consolas, monospace; word-break: break-all; }
.wz-check { display: block; margin: 8px 0 4px; font-size: 0.87rem; }
.wz-busy { font-style: italic; }
.wz-buttons { margin-top: 18px; }
.wz-notice { padding: 8px 12px; margin: 0 0 12px; border-radius: 6px; background: var(--panel-2); }
.wz-error { border-left: 4px solid var(--err); }
.wz-info { border-left: 4px solid var(--ok); }
.wz-detail { font-family: Consolas, monospace; font-size: 0.75rem; word-break: break-all; opacity: 0.85; }
.wz-stages { list-style: none; padding: 0; margin: 10px 0; }
.wz-stage { display: grid; grid-template-columns: 1fr max-content; gap: 2px 12px; padding: 6px 0;
  border-bottom: 1px solid var(--border); }
.wz-stage-state { font-size: 0.8rem; color: var(--muted); }
.wz-stage-detail { grid-column: 1 / 3; font-size: 0.8rem; }
.wz-stage-detail progress { width: 100%; height: 10px; display: block; margin: 4px 0; accent-color: var(--accent); }
.wz-done .wz-stage-state, .wz-skipped .wz-stage-state { color: var(--ok); }
.wz-failed .wz-stage-state { color: var(--err); font-weight: 600; }
.wz-progress .wz-stage-name, .wz-start .wz-stage-name { font-weight: 600; }
.wz-dicts { list-style: none; padding: 0; margin: 10px 0; }
.wz-dict { display: grid; grid-template-columns: 1fr max-content max-content; gap: 4px 12px; align-items: center;
  padding: 6px 0; border-bottom: 1px solid var(--border); }
.wz-dict progress, .wz-dict .wz-notice { grid-column: 1 / 4; width: 100%; }
.wz-dicts-panel { margin-top: 22px; max-width: 760px; }
```

Edit plan B's `owlocr/web/static/index.html`:

1. Directly after `<link rel="stylesheet" href="static/style.css">` add the line
   `<link rel="stylesheet" href="static/wizard.css">`.
2. Replace the whole placeholder section (from `<section id="viewWizard" class="view" hidden>` to its closing `</section>`, which contains `wizard_title`, `wizard_text`, `wizardToSettings` and `wizardToQueue`) with the single line
   `<section id="viewWizard" class="view" hidden></section>`.
3. Directly after the closing `</div>` of `<div class="engine-actions">` (the div that holds `btnVerify`, `btnReinstall`, `btnMove` and `btnRemoveEngine`) add the line
   `<div id="dictSettings" class="wz-dicts-panel"></div>`.
4. Directly before `<script src="static/app.js"></script>` add the two lines
   `<script src="static/wizard_i18n.js"></script>` and `<script src="static/wizard.js"></script>`, so the order is i18n, owl, review, wizard_i18n, wizard, app and the file still ends with `</script></body></html>`.

Edit plan B's `owlocr/web/static/app.js`:

1. In `showView(name)`, after the line `if (name === 'about') renderAbout();` add:

```javascript
    if (name === 'wizard') window.OwlWizard.show();
    if (name === 'settings') window.OwlWizard.renderDictionaries($('dictSettings'));
```

2. In `wire()`, replace these lines

```javascript
    $('btnRemoveEngine').addEventListener('click', function () {
      engineAction('/api/engine/remove', 'confirm_remove_engine');
    });
    $('btnReinstall').addEventListener('click', function () { showView('wizard'); });
    $('btnMove').addEventListener('click', function () { showView('wizard'); });
```

with

```javascript
    $('btnRemoveEngine').addEventListener('click', async function () {
      if (await engineAction('/api/engine/remove', 'confirm_remove_engine')) showView('wizard');
    });
    $('btnReinstall').addEventListener('click', function () { window.OwlWizard.reinstall(); });
    $('btnMove').addEventListener('click', function () { window.OwlWizard.move(); });
```

   and delete the two lines that wire `wizardToSettings` and `wizardToQueue`.

3. In `start()`, directly after the `window.OwlReview.init({ ... });` statement add:

```javascript
    window.OwlWizard.init({ api: api, toast: toast, confirmDialog: confirmDialog, showView: showView });
```

Plan B's Verify button stays as it is: it calls `POST /api/engine/verify` and toasts the number of problems; Reinstall repairs them.

Edit plan B's `owlocr/web/static/i18n.js`: in both the `"cs"` and the `"en"` table delete the four members `"wizard_title"`, `"wizard_text"`, `"wizard_to_settings"` and `"wizard_to_queue"` (whole lines; they sit in the middle of the tables, so the JSON stays valid).

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_wizard_strings.py tests/test_wizard_integration.py tests/test_ui_page.py tests/test_ui_strings.py -q`
Expected: all pass (`10 passed` in the strings file, `4 passed` in the integration file, plan B's page and string tests unchanged: the new `dictSettings` div holds no visible text).

Then look at it once in a browser, without downloading anything (`OWLOCR_DEMO_INSTALL=1` makes the Install step walk through the stages in about 25 seconds and install nothing):

```
$env:OWLOCR_HOME = "$env:TEMP\owl-wizard-demo\data"; $env:OWLOCR_CONFIG = "$env:TEMP\owl-wizard-demo\config"
$env:OWLOCR_DEMO_INSTALL = "1"; Remove-Item Env:OWLOCR_ENGINE_WORKER -ErrorAction SilentlyContinue
py -3.11 -m owlocr --server-only --port 5791
```

Open `http://127.0.0.1:5791/` and check: the wizard opens by itself (not installed); Welcome → Next; Hardware shows the RTX 4080 SUPER with 16 GB and "Graphics card – full quality"; Next; Location shows the temp folder and free space; Install runs the ten stages with a moving bar; Pause shows "Paused" and Continue finishes; Self-test → Next shows "Spell-check dictionaries (recommended)" with Czech (about 3.6 MB, GNU GPL) and English (about 0.5 MB, SCOWL) both ticked; Skip → Done → "Start using Owl OCR" shows the queue; switching the header language to English re-renders the wizard; Settings shows the Dictionaries section with two Install buttons (installing one downloads about 3.6 MB from raw.githubusercontent.com into the temporary data folder; Remove takes it away again); Settings → Reinstall asks for confirmation; click Queue during the wizard: the yellow notice shows "Engine není nainstalovaný…" with "Dokončit nastavení"; clicking it returns to the wizard at the same step. Stop the server with Ctrl+C and remove the four environment variables (`Remove-Item Env:OWLOCR_HOME, Env:OWLOCR_CONFIG, Env:OWLOCR_DEMO_INSTALL`).

- [ ] **Step 5: Commit**

```
git add owlocr/web/static/wizard.js owlocr/web/static/wizard.css owlocr/web/static/index.html owlocr/web/static/app.js owlocr/web/static/i18n.js tests/test_wizard_strings.py tests/test_wizard_integration.py
git commit -m "Replace the wizard placeholder with the setup wizard, the dictionary step and the Settings actions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 23: Entry point of the packaged app

**Files:**
- Create: `packaging/launcher.py`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: plan B's `owlocr.__main__.main(argv=None) -> int` (flags `--web`, `--server-only`, `--port N`; it installs null streams itself too), `owlocr.uninstall.main()`.
- Produces: the script PyInstaller freezes. `OwlOCR.exe --remove-data` runs the uninstall clean-up before anything of the app starts (no window, no single-instance mutex); every other start goes to `owlocr.__main__.main()`. Null streams replace `sys.stdout` / `sys.stderr` when they are `None` in the windowed build (design 12), before any other import.

- [ ] **Step 1: Write the failing test**

Create `tests/test_launcher.py`:

```python
"""packaging/launcher.py, the entry point PyInstaller freezes, run from source."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from owlocr import __version__
from tests.conftest import FAKE_WORKER, REPO

LAUNCHER = REPO / "packaging" / "launcher.py"


def launcher_env(home, config) -> dict:
    env = dict(os.environ)
    env.update(PYTHONPATH=str(REPO), OWLOCR_HOME=str(home), OWLOCR_CONFIG=str(config),
               OWLOCR_ENGINE_WORKER=str(FAKE_WORKER))
    return env


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fetch(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except OSError:
        return 0, b""


def wait_health(port: int, timeout_s: float):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, body = fetch(f"http://127.0.0.1:{port}/api/health")
        if status == 200:
            return json.loads(body)
        time.sleep(0.5)
    return None


def test_remove_data_deletes_only_owl_data(tmp_path):
    home, config = tmp_path / "data", tmp_path / "config"
    (home / "engine" / "venv").mkdir(parents=True)
    (home / "models" / "unlimited_ocr").mkdir(parents=True)
    (home / "notes.txt").write_text("keep me", encoding="utf-8")
    config.mkdir()
    (config / "settings.json").write_text("{}", encoding="utf-8")
    done = subprocess.run([sys.executable, str(LAUNCHER), "--remove-data"], env=launcher_env(home, config),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert not (home / "engine").exists() and not (home / "models").exists()
    assert (home / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert not (config / "settings.json").exists()


@pytest.mark.slow
def test_server_only_serves_health_wizard_and_static_files(tmp_path):
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(LAUNCHER), "--server-only", "--port", str(port)],
                            env=launcher_env(tmp_path / "data", tmp_path / "config"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_health(port, 60) == {"ok": True, "version": __version__}
        status, body = fetch(f"http://127.0.0.1:{port}/api/wizard/probe")
        assert status == 200
        assert json.loads(body)["tier"]["name"] in ("gpu_full", "gpu_reduced", "cpu", "unsupported")
        for asset in ("static/wizard.js", "static/wizard_i18n.js", "static/wizard.css", "static/selftest.png"):
            assert fetch(f"http://127.0.0.1:{port}/{asset}")[0] == 200, asset
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_launcher.py -q`
Expected: `2 failed` (the launcher file does not exist: the remove test gets a non-zero exit code with `can't open file`, the server test gets `None` from `wait_health`).

- [ ] **Step 3: Write minimal implementation**

Create `packaging/launcher.py`:

```python
"""Entry point of the packaged Owl OCR (PyInstaller starts this file).

    OwlOCR.exe                 normal start (window)
    OwlOCR.exe --server-only   only the local server, no window (smoke tests)
    OwlOCR.exe --remove-data   used by the uninstaller: deletes the engine and the app's data
"""
import sys


class _NullStream:
    """A windowed build has no console: sys.stdout and sys.stderr are None (design 12)."""

    def write(self, *_args, **_kwargs):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()


def main() -> int:
    if "--remove-data" in sys.argv[1:]:
        from owlocr.uninstall import main as remove_data
        return remove_data()
    from owlocr.__main__ import main as app_main
    result = app_main()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_launcher.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/launcher.py tests/test_launcher.py
git commit -m "Add the entry point of the packaged app with --remove-data" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 24: The owl icon

**Files:**
- Create: `packaging/make_icon.py`
- Test: `tests/test_make_icon.py`

**Interfaces:**
- Consumes: Pillow (a plan A requirement).
- Produces: `GRID` (16 × 16 strings), `COLOURS`, `SIZES = (16, 24, 32, 48, 64, 128, 256)`, `owl_image() -> Image`, `save_icon(out: Path) -> Path`, `main(argv) -> int`. `build.py` writes `build\owl.ico` with it before PyInstaller runs; the `.ico` is generated, never committed. Every size is a nearest-neighbour enlargement passed to Pillow through `append_images`, so small sizes stay sharp (checked with Pillow 12.3 on the owner's PC: all seven sizes are stored, and at 32 px every 2 × 2 block is one grid pixel).

- [ ] **Step 1: Write the failing test**

Create `tests/test_make_icon.py`:

```python
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packaging"))
import make_icon  # noqa: E402


def test_grid_is_square_and_uses_known_colours():
    assert len(make_icon.GRID) == 16
    assert all(len(row) == 16 for row in make_icon.GRID)
    assert set("".join(make_icon.GRID)) <= set(make_icon.COLOURS)


def test_icon_has_every_size_and_sharp_pixels(tmp_path):
    out = make_icon.save_icon(tmp_path / "owl.ico")
    with Image.open(out) as ico:
        assert set(ico.info["sizes"]) == {(s, s) for s in make_icon.SIZES}
        ico.size = (32, 32)
        img = ico.convert("RGBA")
        img.load()
    # nearest-neighbour: every 2 x 2 block of the 32 px icon is one grid pixel
    for y in range(0, 32, 2):
        for x in range(0, 32, 2):
            block = {img.getpixel((x + dx, y + dy)) for dx in (0, 1) for dy in (0, 1)}
            assert len(block) == 1
    assert img.getpixel((8, 12)) == make_icon.COLOURS["K"]       # left pupil, grid column 4, row 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_make_icon.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'make_icon'`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/make_icon.py`:

```python
"""Draws the pixel-art owl icon of Owl OCR and saves it as a Windows .ico file.

    py -3.11 packaging\\make_icon.py build\\owl.ico

The owl is a 16 x 16 pixel grid. Every icon size is scaled from it with nearest-neighbour
resampling, so the pixels stay sharp.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

GRID = (
    "..DD........DD..",
    "..DbD......DbD..",
    "..DbBDDDDDDBbD..",
    ".DBBBBBBBBBBBBD.",
    ".DBLLLLBBLLLLBD.",
    "DBLWWWLLLLWWWLBD",
    "DBLWKWLLLLWKWLBD",
    "DBLWWWLYYLWWWLBD",
    "DBBLLLLYYLLLLBBD",
    "DbBBBBBBBBBBBBbD",
    "DbBTLTLTLTLTBBbD",
    "DbBLTLTLTLTLBBbD",
    ".DbBTLTLTLTBBbD.",
    ".DbBBBBBBBBBBbD.",
    "..DDFFDDDDFFDD..",
    "................",
)
COLOURS = {
    ".": (0, 0, 0, 0),
    "D": (59, 42, 26, 255),       # outline
    "B": (139, 90, 43, 255),      # feathers
    "b": (107, 68, 32, 255),      # ear tufts and wings
    "L": (232, 199, 154, 255),    # face and belly
    "W": (255, 250, 240, 255),    # eyes
    "K": (26, 26, 26, 255),       # pupils
    "Y": (242, 178, 51, 255),     # beak
    "T": (201, 160, 107, 255),    # belly pattern
    "F": (224, 123, 36, 255),     # feet
}
SIZES = (16, 24, 32, 48, 64, 128, 256)


def owl_image() -> Image.Image:
    if len(GRID) != 16 or any(len(row) != 16 for row in GRID):
        raise ValueError("the owl grid must be 16 x 16")
    image = Image.new("RGBA", (16, 16))
    image.putdata([COLOURS[ch] for row in GRID for ch in row])
    return image


def save_icon(out: Path) -> Path:
    base = owl_image()
    frames = [base.resize((s, s), Image.Resampling.NEAREST) for s in SIZES]
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    return out


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent / "build" / "owl.ico"
    print("icon written to", save_icon(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_make_icon.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/make_icon.py tests/test_make_icon.py
git commit -m "Add the pixel-art owl icon generator" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 25: Third-party notices

**Files:**
- Create: `packaging/notices.py`, `packaging/THIRD_PARTY_NOTICES.md` (generated)
- Test: `tests/test_notices.py`

**Interfaces:**
- Consumes: `requirements.txt` (plan A, extended by plans B and C with the app's runtime packages), `importlib.metadata` of the build Python, `packaging.requirements.Requirement` (installed with pytest and PyInstaller).
- Produces: `FONTS` (DejaVu Sans 2.37 with `owlocr/export/fonts/DejaVuSans-LICENSE.txt`), `font_notices(root=REPO)`, `roots_from_requirements(path=REQUIREMENTS) -> tuple[str, ...]` (refuses engine packages such as torch), `closure(roots, extra=()) -> list[Distribution]` (follows dependencies whose markers apply on this Windows/Python), `license_name(dist) -> str`, `license_texts(dist) -> list[(title, text)]` (every file under `*.dist-info/licenses/` plus `LICENSE*`, `COPYING*`, `NOTICE*`, `AUTHORS*`), `python_license()`, `render(dists, python_text, fonts=()) -> str`, `main(argv) -> int`; the generated `packaging/THIRD_PARTY_NOTICES.md` (bundled next to `OwlOCR.exe` by the spec).

The exact package list is the second value looked up at build time: it is whatever `requirements.txt` and its dependencies resolve to in the build Python, printed by `--check`. PyInstaller is always added because its bootloader is part of `OwlOCR.exe`. Plan C's packages (spylls MIT, pikepdf MPL-2.0 with its bundled third-party licence files, reportlab BSD, python-docx MIT, numpy BSD) arrive through `requirements.txt`; the DejaVu Sans font of plan C is not a Python package and is listed from `FONTS` with its licence text; the section about downloaded components names the optional dictionaries (Czech GNU GPL, English SCOWL) that are never part of the installer.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notices.py`:

`````python
import sys

import pytest

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import notices  # noqa: E402


def test_closure_follows_dependencies():
    names = {notices.norm(d.metadata["Name"]) for d in notices.closure(("flask",))}
    assert {"flask", "werkzeug", "jinja2", "markupsafe", "itsdangerous", "click", "blinker"} <= names


def test_render_contains_summary_texts_and_model_notice():
    text = notices.render(notices.closure(("flask",)), "PSF LICENSE AGREEMENT FOR PYTHON")
    assert "| Flask |" in text and "| Werkzeug |" in text
    assert "### Flask " in text and "````text" in text
    assert "PSF LICENSE AGREEMENT FOR PYTHON" in text
    assert "Apache License" in text and "modeling_deepseekv2.py" in text
    assert "07dea832e22aefee32ad281d4b80551282e1c168" in text


def test_license_name_is_never_empty():
    for dist in notices.closure(("flask",)):
        assert notices.license_name(dist).strip()


def test_roots_come_from_requirements(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("# app\nPillow>=12.1,<13\npypdfium2>=5.10,<6  # PDF\n-r other.txt\n\nFlask>=3\n", encoding="utf-8")
    assert notices.roots_from_requirements(req) == ("Pillow", "pypdfium2", "Flask")


def test_engine_packages_are_refused_as_roots(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("torch==2.10.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="engine packages"):
        notices.roots_from_requirements(req)


def test_committed_notices_cover_every_requirement():
    text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    rows = {notices.norm(line.split("|")[1].strip()) for line in text.splitlines() if line.startswith("| ")}
    for root in notices.roots_from_requirements():
        assert notices.norm(root) in rows, root
    assert "pyinstaller" in rows


def test_fonts_are_listed_with_their_licence(tmp_path):
    licence = tmp_path / "owlocr" / "export" / "fonts" / "DejaVuSans-LICENSE.txt"
    licence.parent.mkdir(parents=True)
    licence.write_text("Bitstream Vera Fonts Copyright ... public domain", encoding="utf-8")
    fonts = notices.font_notices(tmp_path)
    text = notices.render(notices.closure(("flask",)), "", fonts)
    assert "| DejaVu Sans (font) | 2.37 |" in text
    assert "### DejaVu Sans 2.37 (font)" in text and "Bitstream Vera" in text


def test_committed_notices_list_the_plan_c_packages_font_and_dictionaries():
    text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    rows = {notices.norm(line.split("|")[1].strip()) for line in text.splitlines() if line.startswith("| ")}
    assert {"spylls", "pikepdf", "reportlab", "python-docx", "numpy", "dejavu sans (font)"} <= rows
    assert "LibreOffice dictionaries" in text and "SCOWL" in text
`````

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_notices.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'notices'`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/notices.py`:

`````python
"""Generates packaging/THIRD_PARTY_NOTICES.md from the metadata of the packages bundled in the app.

    py -3.11 packaging\\notices.py            writes packaging\\THIRD_PARTY_NOTICES.md
    py -3.11 packaging\\notices.py --check    lists the bundled packages, fails if a root is missing

The roots are the app's runtime dependencies listed in requirements.txt; their own dependencies
are followed automatically. PyInstaller is added because its bootloader is part of OwlOCR.exe.
"""
from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "packaging" / "THIRD_PARTY_NOTICES.md"
REQUIREMENTS = REPO / "requirements.txt"
EXTRA = ("pyinstaller",)       # its bootloader is part of OwlOCR.exe; its own dependencies are not
ENGINE_ONLY = ("torch", "torchvision", "transformers", "tokenizers", "safetensors", "accelerate")
# Bundled files that are not Python packages: (name, version, licence, licence file in the repo).
FONTS = (("DejaVu Sans", "2.37", "Bitstream Vera Fonts licence and public domain (DejaVu changes)",
          "owlocr/export/fonts/DejaVuSans-LICENSE.txt"),)
LICENSE_FILE = re.compile(r"\.dist-info/(licenses/.+|[^/]*(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*)$", re.I)

HEADER = """# Third-party notices

Owl OCR is released under the MIT License (see `LICENSE`). The installer and the portable zip
contain the third-party software listed below. This file is generated by
`packaging/notices.py` from the metadata of the installed packages; do not edit it by hand.
"""

ENGINE_SECTION = """## Downloaded by the setup wizard (not part of the installer)

- **Unlimited-OCR model** by Baidu (https://huggingface.co/baidu/Unlimited-OCR, revision
  07dea832e22aefee32ad281d4b80551282e1c168): MIT License. The file `modeling_deepseekv2.py`
  (Copyright 2023 DeepSeek-AI and The HuggingFace Inc. team) is under the Apache License,
  Version 2.0; its text is in `licenses/Apache-2.0.txt` and, after installation, in the model
  folder as `LICENSE-Apache-2.0.txt`. On computers that read with the processor Owl OCR modifies
  `modeling_unlimitedocr.py`; the modified file says so in its first lines and the original is
  kept as `modeling_unlimitedocr.py.orig`.
- **Spell-check dictionaries** (optional, downloaded only when the user asks, from the
  LibreOffice dictionaries project at pinned commits, see `owlocr/pipeline/dictionaries.json`):
  Czech `cs_CZ` under the GNU GPL, English `en_US` under the SCOWL licence. Each is stored
  unmodified together with its licence text in the dictionaries folder of the data root.
- **uv** by Astral (Apache-2.0 or MIT), **CPython 3.11** (PSF License), **PyTorch** (BSD-3-Clause),
  **transformers** (Apache-2.0) and the other packages in `worker/requirements-engine.txt` are
  installed from their official sources into the separate engine folder, each with its own
  licence files.
"""


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def roots_from_requirements(path: Path = REQUIREMENTS) -> tuple[str, ...]:
    """Package names of a requirements file; `-r` includes, options and comments are skipped."""
    roots = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            roots.append(Requirement(line).name)
    bad = [r for r in roots if norm(r) in ENGINE_ONLY]
    if bad:
        raise ValueError(f"engine packages must not be app requirements: {bad}")
    return tuple(roots)


def closure(roots: tuple[str, ...], extra: tuple[str, ...] = ()) -> list[md.Distribution]:
    seen: dict[str, md.Distribution] = {}
    pending = list(roots)
    while pending:
        name = norm(pending.pop())
        if name in seen:
            continue
        dist = md.distribution(name)
        seen[name] = dist
        for line in dist.requires or []:
            req = Requirement(line)
            if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                continue
            pending.append(req.name)
    for name in extra:
        seen.setdefault(norm(name), md.distribution(name))
    return sorted(seen.values(), key=lambda d: norm(d.metadata["Name"]))


def license_texts(dist: md.Distribution) -> list[tuple[str, str]]:
    texts = []
    for f in dist.files or []:
        rel = str(f).replace("\\", "/")
        if LICENSE_FILE.search(rel):
            try:
                texts.append((rel.rsplit("/", 1)[-1], Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    if not texts:
        long_text = (dist.metadata.get("License") or "").strip()
        if "\n" in long_text:
            texts.append(("License (from package metadata)", long_text))
    return texts


def license_name(dist: md.Distribution) -> str:
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"].strip()
    classifiers = [c.split(" :: ")[-1] for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    if classifiers:
        return ", ".join(dict.fromkeys(classifiers))
    short = (meta.get("License") or "").strip()
    if short and "\n" not in short and len(short) <= 80:
        return short
    return "see the licence text below"


def python_license() -> str:
    path = Path(sys.base_prefix) / "LICENSE.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def font_notices(root: Path = REPO) -> list[tuple[str, str, str, str]]:
    """(name, version, licence, licence text) of every bundled font."""
    return [(name, version, licence, (root / rel).read_text(encoding="utf-8", errors="replace"))
            for name, version, licence, rel in FONTS]


def render(dists: list[md.Distribution], python_text: str,
           fonts: list[tuple[str, str, str, str]] | tuple = ()) -> str:
    lines = [HEADER, "## Summary", "", "| Package | Version | Licence |", "|---|---|---|"]
    lines.append(f"| Python | {sys.version.split()[0]} | PSF License |")
    for d in dists:
        lines.append(f"| {d.metadata['Name']} | {d.version} | {license_name(d)} |")
    for name, version, licence, _text in fonts:
        lines.append(f"| {name} (font) | {version} | {licence} |")
    lines += ["", ENGINE_SECTION, "## Licence texts", ""]
    if python_text:
        lines += [f"### Python {sys.version.split()[0]}", "", "````text", python_text.strip(), "````", ""]
    for name, version, _licence, text in fonts:
        lines += [f"### {name} {version} (font)", "", "````text", text.strip(), "````", ""]
    for d in dists:
        lines += [f"### {d.metadata['Name']} {d.version}", ""]
        texts = license_texts(d)
        if not texts:
            lines += [f"Licence: {license_name(d)}. The package ships no licence file.", ""]
        for title, text in texts:
            lines += [f"`{title}`", "", "````text", text.strip(), "````", ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    try:
        dists = closure(roots_from_requirements(), EXTRA)
    except md.PackageNotFoundError as exc:
        print(f"MISSING: {exc}. Install the app requirements into this Python first.")
        return 1
    if "--check" in argv:
        for d in dists:
            print(f"{d.metadata['Name']}=={d.version}  [{license_name(d)}]")
        return 0
    OUT.write_text(render(dists, python_license(), font_notices()), encoding="utf-8")
    print(f"{len(dists)} packages written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
`````

Look up the package list and generate the file (both with the Python the build uses):

```
py -3.11 -m pip install -r requirements.txt pyinstaller
py -3.11 packaging\notices.py --check
py -3.11 packaging\notices.py
```

`--check` prints one line per bundled package (`name==version  [licence]`); it must contain Flask, pywebview, pythonnet, clr_loader, pypdfium2, Pillow, spylls, pikepdf, reportlab, python-docx, numpy and every other package of `requirements.txt`, and must not contain torch, transformers or any other engine package. (Checked while writing this plan with the spike's packages: pikepdf 10.14.0 MPL-2.0, reportlab 5.0.1 BSD, python-docx 1.2.0 MIT, spylls 0.1.7 MIT, numpy 2.4.6 BSD-3-Clause and others, plus lxml as a dependency of python-docx.) If it prints `MISSING: ...`, install the requirements into this Python and run it again. The last command prints `<N> packages written to ...THIRD_PARTY_NOTICES.md`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_notices.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/notices.py packaging/THIRD_PARTY_NOTICES.md tests/test_notices.py
git commit -m "Generate third-party notices from the bundled packages" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 26: PyInstaller spec

**Files:**
- Create: `packaging/owlocr.spec`
- Test: `tests/test_spec.py`

**Interfaces:**
- Consumes: `packaging/launcher.py`, `owlocr/web/static/` (served by plan B from `Path(server.py).parent / "static"`, so it is bundled as `owlocr/web/static`), `owlocr/engine/pins.json`, plan C's `owlocr/pipeline/dictionaries.json` (read with `Path(__file__).with_name("dictionaries.json")`) and `owlocr/export/fonts/` (DejaVu Sans and its licence, read with `Path(__file__).with_name("fonts")`), `worker/owl_worker.py`, `worker/device_patch.py`, `worker/requirements-engine.txt`, `licenses/`, `LICENSE`, `packaging/THIRD_PARTY_NOTICES.md`, `build/owl.ico` (made by `build.py`).
- Produces: `dist\OwlOCR\OwlOCR.exe` plus `dist\OwlOCR\_internal\` when `build.py` runs it. Data files land under `_internal` at the same relative paths as in the repository, which is exactly where plan A's `paths.resource_path()` looks (`sys._MEIPASS`).

Decisions: ONEDIR (`exclude_binaries=True` + `COLLECT`), windowed (`console=False`), no UPX; `collect_all` for `webview`, `clr_loader`, `pythonnet` (as in Wolfie's build), `pypdfium2`, `pypdfium2_raw` (the PDFium DLL lives there since pypdfium2 5), `reportlab`, `docx` (its `templates/default.docx`), `spylls`, `pikepdf`; `collect_submodules("owlocr")` and `clr` as hidden imports; `EXCLUDES` lists torch, torchvision, torchaudio, transformers, tokenizers, safetensors, accelerate, triton and the other engine-only packages, and `build.py` additionally fails the build if any of them appears in `_internal`. The spec only reads files from the repository and from `build\`, never from git-ignored engine folders.

The second half of `tests/test_spec.py` guards against a forgotten data file: it scans every `owlocr/**/*.py` for files the code reads — `resource_path("...")` and `resource("...")` calls (an f-string such as `f"worker/{name}"` stands for every file of that folder), `*_REL = "..."` constants, `Path(__file__).with_name("...")` and `Path(__file__).parent / "..."` — and fails when one of them is missing in the repository or is not bundled at exactly the path the code looks for it (a bundled folder's contents go into its destination, a bundled file into `<destination>/<name>`). While writing this plan the test was checked by deleting the `dictionaries.json` line from the spec: it failed with `owlocr/pipeline/dictionaries.json: bundled as None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_spec.py`:

```python
import re

from tests.conftest import REPO

SPEC = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
ENGINE_LIBRARIES = ("torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors",
                    "accelerate")


def test_spec_compiles_and_is_onedir_windowed():
    compile(SPEC, "owlocr.spec", "exec")
    assert "exclude_binaries=True" in SPEC and "COLLECT(" in SPEC      # onedir, never onefile
    assert "console=False" in SPEC and "upx=False" in SPEC


def test_spec_excludes_engine_libraries():
    excludes = re.search(r"EXCLUDES = \[(.*?)\]", SPEC, re.S).group(1)
    for name in ENGINE_LIBRARIES:
        assert f'"{name}"' in excludes, name


def test_spec_collects_what_the_app_needs():
    for package in ("webview", "clr_loader", "pythonnet", "pypdfium2", "pypdfium2_raw", "reportlab", "docx", "spylls"):
        assert f'"{package}"' in SPEC, package
    for data in ('"owlocr" / "web" / "static"', '"pins.json"', '"owl_worker.py"', '"device_patch.py"',
                 '"requirements-engine.txt"', '"licenses"', '"LICENSE"', '"THIRD_PARTY_NOTICES.md"'):
        assert data in SPEC, data
    assert 'packaging" / "launcher.py"' in SPEC


# ---- every data file the code reads is bundled at the path the code expects ------------------
DATA_ENTRY = re.compile(r'\(str\(ROOT((?:\s*/\s*"[^"]+")+)\),\s*"([^"]+)"\)')
READS = (
    re.compile(r'resource(?:_path)?\(\s*(f?)"([^"]*)"'),                    # paths.resource_path, Deps.resource
    re.compile(r'_REL\s*=\s*()"([^"]+)"'),                                   # *_REL constants
)
BESIDE_MODULE = (
    re.compile(r'Path\(__file__\)(?:\.resolve\(\))?\.with_name\(\s*"([^"]+)"\)'),
    re.compile(r'Path\(__file__\)(?:\.resolve\(\))?\.parent\s*/\s*"([^"]+)"'),
)


def bundled_entries() -> list[tuple[str, str]]:
    entries = []
    for parts, dest in DATA_ENTRY.findall(SPEC):
        src = "/".join(re.findall(r'"([^"]+)"', parts))
        entries.append((src, dest))
    return entries


def files_the_code_reads() -> set[str]:
    wanted: set[str] = set()
    for source in sorted((REPO / "owlocr").rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for pattern in READS:
            for is_f, value in pattern.findall(text):
                if is_f:                                     # f"worker/{name}": every file of that folder
                    folder = value.split("{", 1)[0].rstrip("/")
                    wanted |= {p.relative_to(REPO).as_posix() for p in (REPO / folder).iterdir()
                               if p.is_file() and p.suffix != ".pyc"}
                elif value:
                    wanted.add(value)
        module_dir = source.parent.relative_to(REPO).as_posix()
        for pattern in BESIDE_MODULE:
            wanted |= {f"{module_dir}/{name}" for name in pattern.findall(text)}
    return wanted


def bundle_path(rel: str, entries) -> str | None:
    for src, dest in entries:
        if rel == src:                      # a folder's contents go into dest, a file into dest/<name>
            path = dest if (REPO / src).is_dir() else f"{dest}/{src.rsplit('/', 1)[-1]}"
        elif rel.startswith(src + "/"):
            path = f"{dest}{rel[len(src):]}"
        else:
            continue
        return path[2:] if path.startswith("./") else path
    return None


def test_the_code_reads_the_expected_data_files():
    wanted = files_the_code_reads()
    for rel in ("owlocr/web/static", "owlocr/engine/pins.json", "owlocr/pipeline/dictionaries.json",
                "owlocr/export/fonts", "worker/owl_worker.py", "worker/requirements-engine.txt",
                "licenses/Apache-2.0.txt", "owlocr/web/static/selftest.png"):
        assert rel in wanted, rel


def test_every_data_file_the_code_reads_is_bundled_where_the_code_looks():
    entries = bundled_entries()
    problems = []
    for rel in sorted(files_the_code_reads()):
        if not (REPO / rel).exists():
            problems.append(f"{rel}: read by the code but missing in the repository")
        elif bundle_path(rel, entries) != rel:
            problems.append(f"{rel}: bundled as {bundle_path(rel, entries)}")
    assert problems == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_spec.py -q`
Expected: collection error `FileNotFoundError: ... packaging\owlocr.spec`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/owlocr.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec of Owl OCR. Build with:  py packaging\build.py   (never with a .bat file)
#
# ONEDIR and windowed. torch, transformers and the other engine libraries are EXCLUDED on
# purpose: the engine lives in its own venv that the setup wizard creates. build.py fails the
# build if any of them ends up in the output anyway.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "build" / "owl.ico"

EXCLUDES = [
    "torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors",
    "accelerate", "triton", "einops", "easydict", "addict", "matplotlib",
    "tensorflow", "jax", "IPython", "pytest",
]

datas = [
    (str(ROOT / "owlocr" / "web" / "static"), "owlocr/web/static"),
    (str(ROOT / "owlocr" / "engine" / "pins.json"), "owlocr/engine"),
    (str(ROOT / "owlocr" / "pipeline" / "dictionaries.json"), "owlocr/pipeline"),
    (str(ROOT / "owlocr" / "export" / "fonts"), "owlocr/export/fonts"),
    (str(ROOT / "worker" / "owl_worker.py"), "worker"),
    (str(ROOT / "worker" / "device_patch.py"), "worker"),
    (str(ROOT / "worker" / "requirements-engine.txt"), "worker"),
    (str(ROOT / "licenses"), "licenses"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "packaging" / "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = collect_submodules("owlocr") + ["clr"]

for package in ("webview", "clr_loader", "pythonnet", "pypdfium2", "pypdfium2_raw", "reportlab",
                "docx", "spylls", "pikepdf"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OwlOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="OwlOCR",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_spec.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/owlocr.spec tests/test_spec.py
git commit -m "Add the PyInstaller onedir spec without engine libraries" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 27: Inno Setup installer script

**Files:**
- Create: `packaging/installer.iss`
- Test: `tests/test_installer_script.py`

**Interfaces:**
- Consumes: `dist\OwlOCR\` (Task 28 passes `/DSourceDir`), `build\owl.ico` (`/DIconFile`), `LICENSE` (`/DRepoDir`), `/DAppVersion`, `/DOutputDir`; Inno Setup 6.3 or newer (for `x64compatible`; the owner has 6.7.3 in `%LOCALAPPDATA%\Programs\Inno Setup 6`, with `Languages\Czech.isl`).
- Produces: `dist\OwlOCR-<version>-setup.exe`: per-user install into `{localappdata}\Programs\OwlOCR` with `PrivilegesRequired=lowest`, Start menu entry, optional (unchecked) desktop icon, English and Czech setup languages, "Launch Owl OCR" at the end, and an uninstaller that asks (default No, silent uninstall = No) whether to delete the engine, queue and settings as well; on Yes it runs `OwlOCR.exe --remove-data` before the program files are removed, so the app itself deletes exactly its own data (it knows the data root, including a folder chosen in the wizard, and its UTF-8 `location.txt`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_script.py`:

```python
from tests.conftest import REPO

ISS = (REPO / "packaging" / "installer.iss").read_text(encoding="utf-8")


def test_installer_script():
    assert "PrivilegesRequired=lowest" in ISS
    assert r"DefaultDirName={localappdata}\Programs\OwlOCR" in ISS
    assert r'Name: "{autoprograms}\Owl OCR"' in ISS
    assert 'Name: "desktopicon"' in ISS and "Flags: unchecked" in ISS
    assert "'--remove-data'" in ISS and "usUninstall" in ISS and "IDNO" in ISS
    assert r"compiler:Languages\Czech.isl" in ISS
    assert "OutputBaseFilename=OwlOCR-{#AppVersion}-setup" in ISS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_installer_script.py -q`
Expected: collection error `FileNotFoundError: ... packaging\installer.iss`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/installer.iss`:

```ini
; Inno Setup 6 script of Owl OCR. Compiled by packaging\build.py, which passes the defines below.
; Per-user install without administrator rights into %LOCALAPPDATA%\Programs\OwlOCR.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef RepoDir
  #define RepoDir ".."
#endif
#ifndef SourceDir
  #define SourceDir RepoDir + "\dist\OwlOCR"
#endif
#ifndef OutputDir
  #define OutputDir RepoDir + "\dist"
#endif
#ifndef IconFile
  #define IconFile RepoDir + "\build\owl.ico"
#endif

[Setup]
AppId={{6C1E2B7A-4F3D-4E9A-9B1C-2D7F0A8E5C31}
AppName=Owl OCR
AppVersion={#AppVersion}
AppVerName=Owl OCR {#AppVersion}
AppPublisher=romelsteel
AppPublisherURL=https://github.com/romelsteel/owl-ocr
AppSupportURL=https://github.com/romelsteel/owl-ocr/issues
AppUpdatesURL=https://github.com/romelsteel/owl-ocr/releases
DefaultDirName={localappdata}\Programs\OwlOCR
DefaultGroupName=Owl OCR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=OwlOCR-{#AppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\OwlOCR.exe
UninstallDisplayName=Owl OCR
LicenseFile={#RepoDir}\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[CustomMessages]
english.RemoveDataQuestion=Also delete the Owl OCR engine (about 10 GB), the queue and the settings?%n%nYour documents and the files Owl OCR wrote next to them are never deleted.
czech.RemoveDataQuestion=Smazat také engine Owl OCR (asi 10 GB), frontu a nastavení?%n%nVaše dokumenty a soubory, které Owl OCR uložil vedle nich, se nikdy nemažou.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Owl OCR"; Filename: "{app}\OwlOCR.exe"
Name: "{autodesktop}\Owl OCR"; Filename: "{app}\OwlOCR.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OwlOCR.exe"; Description: "{cm:LaunchProgram,Owl OCR}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if SuppressibleMsgBox(CustomMessage('RemoveDataQuestion'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      Exec(ExpandConstant('{app}\OwlOCR.exe'), '--remove-data', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_installer_script.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```
git add packaging/installer.iss tests/test_installer_script.py
git commit -m "Add the per-user Inno Setup installer script" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 28: Build script and the first build

**Files:**
- Create: `packaging/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `packaging/make_icon.py`, `packaging/notices.py`, `packaging/owlocr.spec`, `packaging/installer.iss`, `owlocr/__init__.py` (`__version__`), `owlocr/engine/pins.json`, `tests/fake_worker.py`, plan B's `__main__` flags `--server-only` and `--port`.
- Produces: `py packaging\build.py [--no-installer]`; helpers `version()`, `check_environment()`, `app_running()`, `clean()`, `run_pyinstaller()`, `forbidden_found(app_dir) -> list[str]`, `REQUIRED_BUNDLE`, `missing_bundle_files(app_dir) -> list[str]`, `free_port()`, `get_json(url)`, `get_status(url)`, `wait_health(port, timeout_s)`, `kill_tree(pid)`, `window_titles(pid)`, `smoke_env()`, `smoke_test(exe, version) -> list[str]`, `make_zip(app_dir, out)`, `find_iscc()`, `build_installer(iscc, version)`, `sha256(path)`, `write_sums(files, out)`, `main(argv)`. Output in `dist\`: `OwlOCR\`, `OwlOCR-<version>-portable-win64.zip`, `OwlOCR-<version>-setup.exe`, `SHA256SUMS.txt`.

Steps of `main`: refuse anything but Windows and Python 3.11, an unfilled `pins.json` or missing source files (including plan C's `dictionaries.json` and DejaVu font); refuse while `OwlOCR.exe` runs; clean `build\pyinstaller`, `build\smoke`, `dist\OwlOCR` and old artefacts; make the icon and the notices; run PyInstaller; fail if an engine library ended up in `_internal` or if a file of `REQUIRED_BUNDLE` is missing there (`missing_bundle_files`: static UI, pins, dictionaries manifest, DejaVu font and licence, worker scripts, licences, notices); smoke test (design 12): start `OwlOCR.exe --server-only --port <free port>` with private `OWLOCR_HOME` / `OWLOCR_CONFIG` under `build\smoke` and `OWLOCR_ENGINE_WORKER` pointing at the fake worker (torch is never started), wait up to 90 s for `/api/health` with the right version, check that `index.html`, the wizard scripts and the self-test page are served, that `/api/wizard/probe` answers and that `/api/dictionaries` lists `cs` and `en` (so the dictionaries manifest was found in the frozen app); then start `OwlOCR.exe --port <port>` normally and wait up to 90 s for a visible window whose title contains "Owl" and for `/api/health`; kill both process trees; zip the onedir folder; run Inno Setup when `ISCC.exe` is found (PATH, `%LOCALAPPDATA%\Programs\Inno Setup 6`, `Program Files (x86)`, `Program Files`), otherwise print where to download it; write `SHA256SUMS.txt`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build.py`:

```python
import hashlib
import http.server
import json
import sys
import threading
import zipfile

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import build  # noqa: E402


def test_version_matches_package():
    import owlocr
    assert build.version() == owlocr.__version__


def test_forbidden_found(tmp_path):
    internal = tmp_path / "OwlOCR" / "_internal"
    for name in ("webview", "flask", "torch", "transformers-4.57.1.dist-info", "torchvision.libs"):
        (internal / name).mkdir(parents=True)
    assert build.forbidden_found(tmp_path / "OwlOCR") == ["torch", "torchvision.libs", "transformers-4.57.1.dist-info"]
    assert build.forbidden_found(tmp_path / "missing") == []


def test_make_zip_and_sums(tmp_path):
    app = tmp_path / "OwlOCR"
    (app / "_internal").mkdir(parents=True)
    (app / "OwlOCR.exe").write_bytes(b"exe")
    (app / "_internal" / "base_library.zip").write_bytes(b"lib")
    out = build.make_zip(app, tmp_path / "OwlOCR-0.1.0-portable-win64.zip")
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["OwlOCR/OwlOCR.exe", "OwlOCR/_internal/base_library.zip"]
    sums = build.write_sums([out], tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert sums == f"{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}\n"


def test_wait_health():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "version": "0.1.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert build.wait_health(server.server_address[1], 5) == {"ok": True, "version": "0.1.0"}
    finally:
        server.shutdown()
    assert build.wait_health(build.free_port(), 1) is None


def test_find_iscc_returns_an_existing_file_or_none():
    found = build.find_iscc()
    assert found is None or found.is_file()


def test_missing_bundle_files(tmp_path):
    app = tmp_path / "OwlOCR"
    for rel in build.REQUIRED_BUNDLE:
        (app / "_internal" / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / "_internal" / rel).write_bytes(b"x")
    assert build.missing_bundle_files(app) == []
    (app / "_internal" / "owlocr" / "export" / "fonts" / "DejaVuSans.ttf").unlink()
    assert build.missing_bundle_files(app) == ["owlocr/export/fonts/DejaVuSans.ttf"]


def test_required_bundle_matches_the_spec():
    spec = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
    for rel in ("owlocr/pipeline", "owlocr/export/fonts", "owlocr/web/static", "worker", "licenses"):
        assert f'"{rel}")' in spec, rel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_build.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'build'`.

- [ ] **Step 3: Write minimal implementation**

Create `packaging/build.py`:

```python
"""Builds Owl OCR for Windows (design 12). Never use a .bat file for this.

    py packaging\\build.py                  icon, notices, PyInstaller, smoke test, zip, installer, sums
    py packaging\\build.py --no-installer   everything except Inno Setup

Output in dist\\: OwlOCR\\ (onedir app), OwlOCR-<version>-portable-win64.zip,
OwlOCR-<version>-setup.exe (when Inno Setup 6 is installed) and SHA256SUMS.txt.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
BUILD = REPO / "build"
APP_DIR = DIST / "OwlOCR"
EXE = APP_DIR / "OwlOCR.exe"
ICON = BUILD / "owl.ico"
CREATE_NO_WINDOW = 0x08000000
FORBIDDEN = ("torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors", "accelerate")
INNO_URL = "https://jrsoftware.org/isdl.php"
# Data files that must be inside _internal at these paths (plans A-D read them from there).
REQUIRED_BUNDLE = (
    "owlocr/web/static/index.html", "owlocr/web/static/wizard.js", "owlocr/web/static/wizard_i18n.js",
    "owlocr/web/static/selftest.png", "owlocr/engine/pins.json", "owlocr/pipeline/dictionaries.json",
    "owlocr/export/fonts/DejaVuSans.ttf", "owlocr/export/fonts/DejaVuSans-LICENSE.txt",
    "worker/owl_worker.py", "worker/device_patch.py", "worker/requirements-engine.txt",
    "licenses/Apache-2.0.txt", "LICENSE", "THIRD_PARTY_NOTICES.md",
)


def version() -> str:
    text = (REPO / "owlocr" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def step(title: str) -> None:
    print(f"\n=== {title}", flush=True)


def check_environment() -> None:
    if sys.platform != "win32":
        raise SystemExit("Owl OCR is built on Windows only.")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(f"Build with Python 3.11 (this is {sys.version.split()[0]}): py -3.11 packaging\\build.py")
    pins = json.loads((REPO / "owlocr" / "engine" / "pins.json").read_text(encoding="utf-8"))["uv"]
    if len(pins["sha256"]) != 64:
        raise SystemExit("owlocr/engine/pins.json is not filled in; run py -3.11 packaging\\pin_uv.py")
    for required in (REPO / "LICENSE", REPO / "licenses" / "Apache-2.0.txt", REPO / "worker" / "owl_worker.py",
                     REPO / "worker" / "device_patch.py", REPO / "owlocr" / "web" / "static" / "selftest.png",
                     REPO / "owlocr" / "pipeline" / "dictionaries.json", REPO / "owlocr" / "export" / "fonts" / "DejaVuSans.ttf"):
        if not required.is_file():
            raise SystemExit(f"missing {required}")


def app_running() -> bool:
    done = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OwlOCR.exe", "/NH"], capture_output=True,
                          text=True, creationflags=CREATE_NO_WINDOW)
    return "owlocr.exe" in done.stdout.lower()


def clean() -> None:
    for path in (BUILD / "pyinstaller", BUILD / "smoke", APP_DIR):
        if path.exists():
            shutil.rmtree(path)
    DIST.mkdir(parents=True, exist_ok=True)
    for old in list(DIST.glob("OwlOCR-*")) + [DIST / "SHA256SUMS.txt"]:
        if old.is_file():
            old.unlink()


def run_pyinstaller() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(BUILD / "pyinstaller"), str(REPO / "packaging" / "owlocr.spec")],
                   check=True, cwd=str(REPO))


def forbidden_found(app_dir: Path) -> list[str]:
    internal = app_dir / "_internal"
    found = []
    for entry in internal.iterdir() if internal.is_dir() else []:
        name = entry.name.lower()
        base = re.split(r"[-.]", name, maxsplit=1)[0]
        if name in FORBIDDEN or base in FORBIDDEN:
            found.append(entry.name)
    return sorted(found)


def missing_bundle_files(app_dir: Path) -> list[str]:
    internal = app_dir / "_internal"
    return [rel for rel in REQUIRED_BUNDLE if not (internal / rel).is_file()]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_json(url: str, timeout: float = 5.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def wait_health(port: int, timeout_s: float) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = get_json(f"http://127.0.0.1:{port}/api/health", timeout=2.0)
        if data and data.get("ok"):
            return data
        time.sleep(0.5)
    return None


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)


def window_titles(pid: int) -> list[str]:
    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def callback(hwnd, _lparam):
        owner = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            titles.append(buffer.value)
        return True

    user32.EnumWindows(callback, 0)
    return titles


def smoke_env() -> dict[str, str]:
    """Private data and config folders, and the fake worker: the smoke test never touches the
    owner's engine or settings and never starts torch."""
    home = BUILD / "smoke"
    env = dict(os.environ)
    env.update(OWLOCR_HOME=str(home / "data"), OWLOCR_CONFIG=str(home / "config"),
               OWLOCR_ENGINE_WORKER=str(REPO / "tests" / "fake_worker.py"))
    return env


def get_status(url: str, timeout: float = 5.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except OSError:
        return 0


def smoke_test(exe: Path, expected_version: str) -> list[str]:
    problems: list[str] = []
    port = free_port()
    proc = subprocess.Popen([str(exe), "--server-only", "--port", str(port)], env=smoke_env(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        health = wait_health(port, 90)
        if health is None:
            problems.append("--server-only: /api/health did not answer within 90 s")
        elif health.get("version") != expected_version:
            problems.append(f"--server-only: version {health.get('version')} != {expected_version}")
        else:
            for asset in ("index.html", "static/wizard.js", "static/wizard_i18n.js", "static/selftest.png"):
                url = f"http://127.0.0.1:{port}/" + ("" if asset == "index.html" else asset)
                if get_status(url) != 200:
                    problems.append(f"--server-only: {asset} is not served (static files not bundled?)")
            probe = get_json(f"http://127.0.0.1:{port}/api/wizard/probe", timeout=30)
            if not probe or "tier" not in probe:
                problems.append("--server-only: /api/wizard/probe failed")
            dicts = get_json(f"http://127.0.0.1:{port}/api/dictionaries")
            if not dicts or [d["language"] for d in dicts["languages"]] != ["cs", "en"]:
                problems.append("--server-only: /api/dictionaries failed (dictionaries.json not bundled?)")
    finally:
        kill_tree(proc.pid)
    port = free_port()
    proc = subprocess.Popen([str(exe), "--port", str(port)], env=smoke_env())
    try:
        deadline, titles = time.monotonic() + 90, []
        while time.monotonic() < deadline and not any("Owl" in t for t in titles):
            time.sleep(1)
            titles = window_titles(proc.pid)
        if not any("Owl" in t for t in titles):
            problems.append(f"window: no visible 'Owl OCR' window within 90 s (titles: {titles})")
        if wait_health(port, 30) is None:
            problems.append("window: /api/health did not answer")
    finally:
        kill_tree(proc.pid)
    return problems


def make_zip(app_dir: Path, out: Path) -> Path:
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(Path(app_dir.name) / path.relative_to(app_dir)))
    return out


def find_iscc() -> Path | None:
    candidates = [shutil.which("ISCC")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe"))
    candidates += [r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def build_installer(iscc: Path, app_version: str) -> Path:
    subprocess.run([str(iscc), f"/DAppVersion={app_version}", f"/DRepoDir={REPO}", f"/DSourceDir={APP_DIR}",
                    f"/DOutputDir={DIST}", f"/DIconFile={ICON}", str(REPO / "packaging" / "installer.iss")],
                   check=True)
    return DIST / f"OwlOCR-{app_version}-setup.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sums(files: list[Path], out: Path) -> Path:
    out.write_text("".join(f"{sha256(f)}  {f.name}\n" for f in files), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    app_version = version()
    step(f"Owl OCR {app_version}: checks")
    check_environment()
    if app_running():
        print("Close Owl OCR first (OwlOCR.exe is running).")
        return 1
    step("clean")
    clean()
    step("icon and third-party notices")
    subprocess.run([sys.executable, str(REPO / "packaging" / "make_icon.py"), str(ICON)], check=True)
    subprocess.run([sys.executable, str(REPO / "packaging" / "notices.py")], check=True)
    step("PyInstaller (onedir, windowed)")
    run_pyinstaller()
    bad = forbidden_found(APP_DIR)
    if bad:
        print("FAILED: engine libraries ended up in the app:", bad)
        return 1
    missing = missing_bundle_files(APP_DIR)
    if missing:
        print("FAILED: data files missing from the app:", missing)
        return 1
    step("smoke test of the built app")
    problems = smoke_test(EXE, app_version)
    if problems:
        for problem in problems:
            print("FAILED:", problem)
        return 1
    print("smoke test passed")
    step("portable zip")
    artefacts = [make_zip(APP_DIR, DIST / f"OwlOCR-{app_version}-portable-win64.zip")]
    step("installer")
    iscc = find_iscc()
    if "--no-installer" in argv:
        print("skipped (--no-installer)")
    elif iscc is None:
        print(f"Inno Setup 6 is not installed. Download it from {INNO_URL}, install it for the current user "
              "and run this build again. The portable zip is ready.")
    else:
        artefacts.append(build_installer(iscc, app_version))
    step("checksums")
    print(write_sums(artefacts, DIST / "SHA256SUMS.txt").read_text(encoding="utf-8"))
    for artefact in artefacts:
        print(f"{artefact}  {artefact.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_build.py -q`
Expected: `7 passed`.

Then the first real build (about 5 to 10 minutes; a window of Owl OCR opens and closes by itself during the smoke test; the build never touches the engine):

```
py -3.11 -m pip install pyinstaller
py packaging\build.py
```

Expected end of the output: `smoke test passed`, the three artefacts with their sizes (the zip and the installer about 60 to 150 MB each, far below GitHub's 2 GiB limit) and their SHA256 lines. If it prints `FAILED: engine libraries ended up in the app: [...]`, find which import pulls them in (`build\pyinstaller\OwlOCR\warn-OwlOCR.txt` and `xref-OwlOCR.html`), remove that import from the app and build again; never widen `EXCLUDES` to hide a real dependency. If a smoke check fails, read `build\smoke\data\logs\` and fix the cause. `dist\` and `build\` are git-ignored; nothing to commit from them.

- [ ] **Step 5: Commit**

```
git add packaging/build.py tests/test_build.py
git commit -m "Add the build script with smoke test, portable zip, installer and checksums" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 29: README in English and Czech

**Files:**
- Modify: `README.md` (replace the whole initial file)
- Create: `README.cs.md`
- Test: `tests/test_readme.py`

**Interfaces:**
- Consumes: the measurements of `docs/research/2026-09-28-spike-results.md` (CER 0.3–2.6 % on generated pages in Quality, 6.5 % for small print in Fast, about 3 wrong words per 100 on real scans against about 10 for the old text layer, 25–45 s per book page, up to 108 s for dense pages, model download 60 s at about 112 MB/s), design 6.4 (tiers, driver 570.65), design 11 (block-level searchable PDF), design 12 (SmartScreen, licences), the wizard labels of Task 21 ("I already have the engine" / "Engine už mám").
- Produces: user documentation, including a short section on the optional dictionaries (downloaded separately from the LibreOffice dictionaries project under their own licences, Czech about 3.6 MB GNU GPL, English about 0.5 MB SCOWL, what the app does without them). The two SmartScreen screenshots it shows (`docs/images/smartscreen-1.png`, `smartscreen-2.png`) are taken during the real installation in Task 31. The row "Processor only" and its speed are updated by Task 30 according to the CPU acceptance result.

- [ ] **Step 1: Write the failing test**

Create `tests/test_readme.py`:

```python
from tests.conftest import REPO

EN = (REPO / "README.md").read_text(encoding="utf-8")
CS = (REPO / "README.cs.md").read_text(encoding="utf-8")


def test_english_readme_covers_the_required_topics():
    for needle in ("570.65", "16 GB", "10 GB", "6.7 GB", "2.9 GB", "SmartScreen", "Run anyway",
                   "3 wrong words in 100", "another real word", "block by block", "## Privacy",
                   "## Uninstalling", "MIT License", "Apache", "I already have the engine",
                   "docs/images/smartscreen-1.png", "docs/images/smartscreen-2.png", "README.cs.md",
                   "LibreOffice dictionaries", "GNU GPL", "SCOWL", "only these checks are"):
        assert needle in EN, needle


def test_czech_readme_covers_the_required_topics():
    for needle in ("570.65", "16 GB", "10 GB", "6,7 GB", "2,9 GB", "SmartScreen", "Přesto spustit",
                   "3 chybná slova ze 100", "jiným skutečným slovem", "po blocích", "## Soukromí",
                   "## Odinstalace", "MIT", "Apache", "Engine už mám",
                   "docs/images/smartscreen-1.png", "docs/images/smartscreen-2.png", "README.md",
                   "LibreOffice dictionaries", "GNU GPL", "SCOWL", "jen tyto kontroly vynechá"):
        assert needle in CS, needle


def test_hardware_tables_have_the_same_rows():
    rows = lambda text: [l for l in text.splitlines() if l.startswith("| ") and "---" not in l]
    assert len(rows(EN)) == len(rows(CS))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_readme.py -q`
Expected: `3 failed` (the initial README lacks the topics; `README.cs.md` does not exist: `FileNotFoundError` at collection, reported as an error for the module).

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `README.md` with:

````markdown
# Owl OCR

Owl OCR turns scans, photos of pages, screenshots and PDFs into text on your own Windows PC.
It uses Baidu's open-source [Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR) model,
works offline after a one-time download, and never sends your documents anywhere.

*Česky: [README.cs.md](README.cs.md)*

## What it does

- Reads scanned PDFs (it was built for Czech books and letters), PDFs that already contain text,
  photos of pages, screenshots and other images (PNG, JPG, WEBP, BMP, TIFF).
- Writes Markdown, plain text, Word (.docx) and a searchable PDF, or copies the text to the clipboard.
- A queue for many files and whole folders: progress, pause, resume, cancel. A long book can be
  read over several sittings; closing the app keeps the queue.
- Two modes: **Quality** (the default on graphics cards with 10 GB or more) and **Fast** (less
  graphics memory; slightly less accurate on small print).
- A review screen shows the scan next to the recognised text, marks words the Czech dictionary does
  not know, and lets you correct the text before exporting.
- Czech and English user interface.

## Hardware

| Setup | What you need | Default mode | Time per book page |
|---|---|---|---|
| Graphics card, full quality | NVIDIA RTX 30, 40 or 50 series (or a professional card of the same generations) with at least 10 GB of graphics memory | Quality | about 25 to 45 s, dense pages up to 110 s (measured on an RTX 4080 SUPER) |
| Graphics card, memory-saving | NVIDIA RTX 20 series or newer with 8 to 10 GB of graphics memory | Fast | about 30 to 70 s (estimate) |
| Processor only | any 64-bit Windows 10/11 PC with at least 16 GB of RAM | Fast | not measured yet; roughly 1 to 5 minutes per page |
| Not supported | less than 16 GB of RAM and no suitable graphics card | | |

The graphics card needs NVIDIA driver **570.65 or newer**. With an older driver Owl OCR asks you to
update it and can read with the processor in the meantime. The setup wizard detects all of this
and chooses for you.

## First start: the one-time download

On the first start a setup wizard downloads the reading engine once:

| Part | Size |
|---|---|
| uv (installer tool) and Python 3.11 | about 45 MB |
| PyTorch for graphics cards (or for the processor) | about 2.9 GB (0.1 GB) |
| Other libraries | a few hundred MB |
| Unlimited-OCR model | 6.7 GB |

That is about **10 GB of download** and **16 GB of disk space**. At 100 Mbit/s the download
takes roughly a quarter of an hour; on a fast connection the model alone downloaded in about a
minute. The wizard can be paused and continues where it stopped, even after closing the app.
You can put the engine on another drive, and if you already have the model downloaded, choose
"I already have the engine" so it is only checked, not downloaded again.

Later starts download nothing and work without internet.

## Spell-check dictionaries (optional)

After the self-test the wizard offers a Czech dictionary (recommended, about 3.6 MB) and an English
one (about 0.5 MB). They are not part of Owl OCR: they are downloaded separately from the
[LibreOffice dictionaries](https://github.com/LibreOffice/dictionaries) project at pinned versions
and come under their own licences (Czech: GNU GPL, English: SCOWL), which are stored next to them.
With a dictionary Owl OCR repairs typical reading errors such as `ď` and `ť` and marks unknown
words in the review screen. Without one Owl OCR works just the same, only these checks are
skipped. Settings → Dictionaries installs or removes them at any time.

## Installing

Download from the [Releases](https://github.com/romelsteel/owl-ocr/releases) page either:

- `OwlOCR-<version>-setup.exe`: installs for your user only, into
  `%LOCALAPPDATA%\Programs\OwlOCR`, without administrator rights, with a Start menu entry; or
- `OwlOCR-<version>-portable-win64.zip`: unpack anywhere and run `OwlOCR.exe`.

`SHA256SUMS.txt` lists the checksums of both files. In PowerShell:
`Get-FileHash .\OwlOCR-<version>-setup.exe -Algorithm SHA256`.

### "Windows protected your PC"

Owl OCR is not code-signed (a certificate costs money every year), so Windows SmartScreen shows a
blue warning the first time you start the installer or `OwlOCR.exe`:

![SmartScreen warning](docs/images/smartscreen-1.png)

Click **More info**, check that the file name is right, then click **Run anyway**:

![Run anyway](docs/images/smartscreen-2.png)

If you prefer, compare the file's SHA256 checksum with `SHA256SUMS.txt` first.

## How accurate is it?

Measured on the developer's PC with Quality mode:

- Generated Czech pages with known text: 0.3 % to 2.6 % of characters wrong (character error rate),
  including poor scans, a phone photo and a screenshot. Small print is the hardest case; Fast mode
  gets 6.5 % wrong there.
- Real scans of a Czech botany textbook: about **3 wrong words in 100** (between 1.7 and 4.5 per
  page), against about 10 in 100 for the text layer the PDF already had. Most errors are a single
  wrong or missing accent. Owl OCR repairs some of them with rules and marks words the dictionary
  does not know.

**Honest caveat:** sometimes the model replaces a real word with another real word
("významcové" instead of "výtrusnice"). No dictionary can detect that. The text has been read by a
machine and has not been checked: check it before you quote it. The review screen makes that easier.

Pages turned by 90 degrees are rotated automatically before reading. Handwriting and non-Latin
scripts are not supported.

## Searchable PDF: a limitation

The model reports the position of each **block** of text, not of each word. The searchable PDF
therefore places the invisible text block by block: searching and copying work, but a highlighted
search hit covers roughly the right area rather than exactly the word.

## Privacy

- Your documents are read on your PC and never leave it. Owl OCR has no account, no telemetry and
  no cloud service.
- The internet is used only by the setup wizard for the one-time download from huggingface.co
  (or modelscope.cn if that fails), download.pytorch.org, pypi.org and github.com.

## Where Owl OCR keeps its files

| What | Where |
|---|---|
| Program (installer) | `%LOCALAPPDATA%\Programs\OwlOCR` |
| Engine, model, queue, logs | `%LOCALAPPDATA%\OwlOCR` or the folder you chose in the wizard |
| Settings | `%APPDATA%\OwlOCR` |
| Results | next to the source file, or the folder set in Settings |

Settings → Engine can verify the engine, reinstall it (nothing intact is downloaded again), move
it to another folder, or remove it.

## Uninstalling

Windows Settings → Apps → Owl OCR → Uninstall. The uninstaller asks whether to delete the engine
(about 10 GB), the queue and the settings as well. Your documents and the files Owl OCR wrote next
to them are never deleted.

Portable version: delete the unpacked folder, then `%LOCALAPPDATA%\OwlOCR` (or your chosen data
folder) and `%APPDATA%\OwlOCR`.

## Building from source

Windows, Python 3.11 and (for the installer) [Inno Setup 6](https://jrsoftware.org/isdl.php):

```
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest
py packaging\build.py
```

The build writes `dist\OwlOCR\`, the portable zip, the installer and `SHA256SUMS.txt`.

## Licence

Owl OCR is released under the MIT License (`LICENSE`). The Unlimited-OCR model is published by
Baidu under the MIT License; one of its files (`modeling_deepseekv2.py`) is under the Apache
License 2.0 (`licenses/Apache-2.0.txt`). On processor-only computers Owl OCR modifies
`modeling_unlimitedocr.py` so it can run without a graphics card; the modified file says so.
All bundled third-party software is listed in `packaging/THIRD_PARTY_NOTICES.md` (next to `OwlOCR.exe` in the installed app).
````

Create `README.cs.md`:

````markdown
# Owl OCR

Owl OCR převádí skeny, fotky stránek, snímky obrazovky a PDF na text přímo ve vašem počítači
s Windows. Používá otevřený model [Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR)
od společnosti Baidu, po jednorázovém stažení funguje bez internetu a vaše dokumenty nikam
neposílá.

*English: [README.md](README.md)*

## Co umí

- Čte naskenovaná PDF (vznikl kvůli českým knihám a dopisům), PDF, která už text obsahují, fotky
  stránek, snímky obrazovky a další obrázky (PNG, JPG, WEBP, BMP, TIFF).
- Ukládá Markdown, prostý text, Word (.docx) a prohledávatelné PDF, nebo zkopíruje text do schránky.
- Fronta pro mnoho souborů i celé složky: průběh, pozastavení, pokračování, zrušení. Dlouhou knihu
  lze číst na několikrát; zavřením aplikace se fronta neztratí.
- Dva režimy: **Kvalita** (výchozí na grafických kartách s 10 GB a více) a **Rychlý** (méně
  grafické paměti; na drobném písmu o něco méně přesný).
- Kontrolní obrazovka ukazuje sken vedle přečteného textu, označí slova, která český slovník
  nezná, a text jde před uložením opravit.
- Rozhraní v češtině a angličtině.

## Hardware

| Způsob čtení | Co je potřeba | Výchozí režim | Čas na stránku knihy |
|---|---|---|---|
| Grafická karta, plná kvalita | NVIDIA řady RTX 30, 40 nebo 50 (nebo profesionální karta stejných generací) s alespoň 10 GB grafické paměti | Kvalita | asi 25 až 45 s, husté stránky až 110 s (změřeno na RTX 4080 SUPER) |
| Grafická karta, úsporný režim | NVIDIA řady RTX 20 nebo novější s 8 až 10 GB grafické paměti | Rychlý | asi 30 až 70 s (odhad) |
| Jen procesor | jakýkoli 64bitový počítač s Windows 10/11 a alespoň 16 GB operační paměti | Rychlý | zatím neměřeno; odhadem 1 až 5 minut na stránku |
| Nepodporováno | méně než 16 GB operační paměti a žádná vhodná grafická karta | | |

Grafická karta potřebuje ovladač NVIDIA **570.65 nebo novější**. Se starším ovladačem vás
Owl OCR požádá o aktualizaci a mezitím může číst procesorem. Průvodce nastavením to všechno
zjistí a vybere za vás.

## První spuštění: jednorázové stažení

Při prvním spuštění průvodce nastavením jednou stáhne čtecí engine:

| Část | Velikost |
|---|---|
| uv (instalační nástroj) a Python 3.11 | asi 45 MB |
| PyTorch pro grafické karty (nebo pro procesor) | asi 2,9 GB (0,1 GB) |
| Další knihovny | několik set MB |
| Model Unlimited-OCR | 6,7 GB |

Celkem asi **10 GB stahování** a **16 GB místa na disku**. Při 100 Mbit/s trvá stahování zhruba
čtvrt hodiny; na rychlém připojení se samotný model stáhl asi za minutu. Průvodce jde pozastavit
a pokračuje tam, kde skončil, i po zavření aplikace. Engine můžete uložit na jiný disk, a pokud už
model stažený máte, zvolte „Engine už mám“ – soubory se jen zkontrolují a znovu se nestahují.

Další spuštění už nic nestahují a fungují bez internetu.

## Slovníky pro kontrolu pravopisu (volitelné)

Po zkoušce průvodce nabídne český slovník (doporučený, asi 3,6 MB) a anglický (asi 0,5 MB).
Nejsou součástí Owl OCR: stahují se zvlášť z projektu
[LibreOffice dictionaries](https://github.com/LibreOffice/dictionaries) v pevně daných verzích a
platí pro ně jejich vlastní licence (čeština: GNU GPL, angličtina: SCOWL), které se ukládají
vedle nich. Se slovníkem Owl OCR opraví typické chyby čtení, například `ď` a `ť`, a na kontrolní
obrazovce označí neznámá slova. Bez slovníku Owl OCR funguje stejně, jen tyto kontroly vynechá.
V Nastavení → Slovníky je můžete kdykoli nainstalovat nebo odebrat.

## Instalace

Na stránce [Releases](https://github.com/romelsteel/owl-ocr/releases) stáhněte buď:

- `OwlOCR-<verze>-setup.exe`: nainstaluje se jen pro vašeho uživatele do
  `%LOCALAPPDATA%\Programs\OwlOCR`, bez práv správce, se zástupcem v nabídce Start; nebo
- `OwlOCR-<verze>-portable-win64.zip`: rozbalte kamkoli a spusťte `OwlOCR.exe`.

Soubor `SHA256SUMS.txt` obsahuje kontrolní součty obou souborů. V PowerShellu:
`Get-FileHash .\OwlOCR-<verze>-setup.exe -Algorithm SHA256`.

### „Systém Windows ochránil váš počítač“

Owl OCR není digitálně podepsaný (certifikát stojí každý rok peníze), a proto Windows SmartScreen
při prvním spuštění instalátoru nebo `OwlOCR.exe` zobrazí modré varování:

![Varování SmartScreen](docs/images/smartscreen-1.png)

Klikněte na **Další informace**, zkontrolujte název souboru a klikněte na **Přesto spustit**:

![Přesto spustit](docs/images/smartscreen-2.png)

Pokud chcete, porovnejte nejdřív kontrolní součet SHA256 souboru se `SHA256SUMS.txt`.

## Jak je přesný?

Změřeno na vývojářově počítači v režimu Kvalita:

- Vygenerované české stránky se známým textem: 0,3 % až 2,6 % chybných znaků, včetně špatných
  skenů, fotky z telefonu a snímku obrazovky. Nejtěžší je drobné písmo; režim Rychlý tam má 6,5 %
  chybných znaků.
- Skutečné skeny české učebnice botaniky: asi **3 chybná slova ze 100** (1,7 až 4,5 podle
  stránky), zatímco textová vrstva, kterou PDF už mělo, měla asi 10 chyb ze 100. Většinou jde
  o jediný chybný nebo chybějící háček či čárku. Část chyb Owl OCR opraví pravidly a slova, která
  slovník nezná, označí.

**Upřímné upozornění:** model občas nahradí skutečné slovo jiným skutečným slovem („významcové“
místo „výtrusnice“). To žádný slovník nepozná. Text přečetl stroj a nikdo ho nezkontroloval:
než ho budete citovat, zkontrolujte ho. Kontrolní obrazovka to usnadní.

Stránky otočené o 90 stupňů se před čtením samy natočí. Rukopis a jiná písma než latinka
nejsou podporovány.

## Prohledávatelné PDF: omezení

Model hlásí polohu každého **bloku** textu, ne každého slova. Prohledávatelné PDF proto umisťuje
neviditelný text po blocích: hledání i kopírování fungují, ale zvýraznění nalezeného slova pokryje
jen přibližně správnou oblast, ne přesně to slovo.

## Soukromí

- Dokumenty se čtou ve vašem počítači a nikdy ho neopustí. Owl OCR nemá účet, telemetrii ani
  cloudovou službu.
- Internet používá jen průvodce nastavením pro jednorázové stažení z huggingface.co (nebo
  z modelscope.cn, když to nejde), download.pytorch.org, pypi.org a github.com.

## Kde má Owl OCR své soubory

| Co | Kde |
|---|---|
| Program (instalátor) | `%LOCALAPPDATA%\Programs\OwlOCR` |
| Engine, model, fronta, záznamy | `%LOCALAPPDATA%\OwlOCR` nebo složka zvolená v průvodci |
| Nastavení | `%APPDATA%\OwlOCR` |
| Výsledky | vedle zdrojového souboru, nebo ve složce z Nastavení |

V Nastavení → Engine jde engine zkontrolovat, přeinstalovat (nic, co je v pořádku, se znovu
nestahuje), přesunout do jiné složky nebo odebrat.

## Odinstalace

Nastavení Windows → Aplikace → Owl OCR → Odinstalovat. Odinstalátor se zeptá, zda smazat také
engine (asi 10 GB), frontu a nastavení. Vaše dokumenty a soubory, které Owl OCR uložil vedle nich,
se nikdy nemažou.

Přenosná verze: smažte rozbalenou složku a potom `%LOCALAPPDATA%\OwlOCR` (nebo zvolenou složku
pro data) a `%APPDATA%\OwlOCR`.

## Sestavení ze zdrojového kódu

Windows, Python 3.11 a (pro instalátor) [Inno Setup 6](https://jrsoftware.org/isdl.php):

```
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest
py packaging\build.py
```

Sestavení vytvoří `dist\OwlOCR\`, přenosný zip, instalátor a `SHA256SUMS.txt`.

## Licence

Owl OCR je vydán pod licencí MIT (`LICENSE`). Model Unlimited-OCR zveřejnila společnost Baidu pod
licencí MIT; jeden z jeho souborů (`modeling_deepseekv2.py`) je pod licencí Apache 2.0
(`licenses/Apache-2.0.txt`). Na počítačích bez vhodné grafické karty Owl OCR upraví
`modeling_unlimitedocr.py`, aby běžel i bez ní; upravený soubor to na začátku uvádí.
Veškerý přibalený software třetích stran je uveden v `packaging/THIRD_PARTY_NOTICES.md` (v nainstalované aplikaci vedle `OwlOCR.exe`).
````

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_readme.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add README.md README.cs.md tests/test_readme.py
git commit -m "Write the user README in English and Czech" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 30: CPU acceptance test and the decision

**Files:**
- Create: `tests/acceptance/__init__.py` (empty), `tests/acceptance/prepare_cpu_root.py`, `tests/acceptance/test_cpu_acceptance.py`, `docs/research/2026-09-28-cpu-acceptance.md` (written by the test)
- Modify, depending on the result: `owlocr/hardware.py`, `owlocr/web/static/wizard_i18n.js`, `README.md`, `README.cs.md`

**Interfaces:**
- Consumes: `bootstrap.run` with `tier_by_name("cpu", "acceptance_test")`, plan A's `default_engine()`, `EngineInfo.cuda_available`, `EngineInfo.torch`, `hardware.ram_total_mib()`, the fixture page `01_letter_clean` and its ground truth.
- Produces: `engine\cpu-acceptance\` (git-ignored, beside the GPU engine and never touching it), `engine\cpu-acceptance\result.json`, the record `docs/research/2026-09-28-cpu-acceptance.md` and the release decision.

**Decision rule** (design 6.4 and 16): on the owner's PC with the GPU hidden, reading `01_letter_clean.png` in Fast mode with fp32 on the processor must reach **CER ≤ 3 %** and take **≤ 300 s** of wall-clock time for the page. Both hold → the CPU tier ships in 0.1.0 (`CPU_TIER_ENABLED = True`). Either fails → 0.1.0 ships GPU-only: `choose_tier` returns `unsupported` for computers without a suitable NVIDIA card (the wizard then shows `wz_hw_gpu_only` and keeps Next disabled) and the READMEs say so.

The test runs manually, never in the normal test run: it is marked `slow` and skipped unless `OWLOCR_CPU_ACCEPTANCE=1`. The GPU is hidden with `CUDA_VISIBLE_DEVICES=-1` (an empty value does not hide it on this PC); the separate root also gets the cpu-only torch build, and the test asserts that the engine reports no CUDA. `prepare_cpu_root.py` hard-links the 6.7 GB weights file from the development engine and copies the small files, so the device patch (which writes through a temporary file) can never change the GPU engine's model code.

- [ ] **Step 1: Write the failing test**

Create `tests/acceptance/__init__.py` as an empty file.

Create `tests/acceptance/prepare_cpu_root.py`:

```python
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
```

Create `tests/acceptance/test_cpu_acceptance.py`:

```python
"""CPU acceptance test (design 6.4 and 16). Run MANUALLY on the owner's PC, never in the normal
test run. It reads one generated page with the processor only and applies the decision rule:

    CER <= 3 %  and  seconds per page <= 300   ->  the CPU tier ships in v1
    otherwise                                  ->  v1 ships GPU-only (plan D, task 30, step 3)

    $env:OWLOCR_HOME = "$PWD\\engine\\cpu-acceptance\\data"
    $env:OWLOCR_CONFIG = "$PWD\\engine\\cpu-acceptance\\config"
    $env:OWLOCR_CPU_ACCEPTANCE = "1"
    py -3.11 -m pytest -m slow tests\\acceptance\\test_cpu_acceptance.py -s

The test hides the GPU itself with CUDA_VISIBLE_DEVICES=-1 (an empty value does not hide it on
this PC, plan A task 16). The CPU engine root also has the cpu-only torch build, and the test
asserts that the engine reports no CUDA, so the GPU cannot be used even by mistake.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

import pytest

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.png"
TRUTH = REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.gt.txt"
MAX_CER = 0.03
MAX_SECONDS = 300.0

manual = pytest.mark.skipif(os.environ.get("OWLOCR_CPU_ACCEPTANCE") != "1",
                            reason="manual test: set OWLOCR_CPU_ACCEPTANCE=1 (see the module docstring)")

TAGS = re.compile(r"<\|ref\|>.*?<\|/ref\|>|<\|det\|>.*?<\|/det\|>", re.S)
SPECIAL = re.compile(r"<\|[^|>]*\|>|<PAGE>")
HTML = re.compile(r"</?(table|thead|tbody|tr|td|th)[^>]*>", re.I)
MARKDOWN = re.compile(r"^\s{0,3}#{1,6}\s+|\*\*|__", re.M)


def clean_ocr(raw: str) -> str:
    """Same cleaning as the spike's score.py, so the numbers are comparable."""
    text = TAGS.sub(" ", raw)
    text = SPECIAL.sub(" ", text)
    text = HTML.sub(" ", text)
    return MARKDOWN.sub("", text)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(truth: str, hypothesis: str) -> float:
    return edit_distance(truth, hypothesis) / max(len(truth), 1)


def test_helpers():
    assert edit_distance("kůň", "kun") == 2
    assert cer("abc", "abc") == 0.0
    assert normalize(clean_ocr("<|det|>text [1, 2, 3, 4]<|/det|>Ahoj\n  světe")) == "Ahoj světe"


def cpu_name() -> str:
    import platform
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor()


def write_record(report: dict) -> Path:
    """docs/research/2026-09-28-cpu-acceptance.md: the numbers and the decision, no local paths."""
    decision = ("the CPU tier ships in 0.1.0" if report["ships"]
                else "0.1.0 ships GPU-only (hardware.CPU_TIER_ENABLED = False)")
    text = f"""# CPU acceptance test

Date: {time.strftime("%Y-%m-%d")}. Machine: {report["cpu"]}, {report["ram_gb"]} GB RAM, GPU hidden with
`CUDA_VISIBLE_DEVICES=-1`, torch {report["torch"]}, float32, separate engine root created with the cpu index.
Page: `tests/fixtures/pages/01_letter_clean.png`, Fast mode.

| Measure | Value |
|---|---|
| Model load | {report["load_seconds"]} s |
| Seconds per page (wall clock) | {report["seconds_per_page"]} s |
| Output tokens | {report["output_tokens"]} |
| Character error rate | {report["cer"] * 100:.2f} % |
| Timed out | {report["timed_out"]} |

Decision rule (plan D, task 30): CER at most 3 % and at most 300 s per page, then the CPU tier ships;
otherwise 0.1.0 ships GPU-only.

Result: **{decision}**.
"""
    out = REPO / "docs" / "research" / "2026-09-28-cpu-acceptance.md"
    out.write_text(text, encoding="utf-8")
    return out


@pytest.mark.slow
@manual
def test_cpu_reads_the_letter_page():
    from owlocr import hardware, paths
    from owlocr.engine import bootstrap
    from owlocr.engine.client import default_engine

    record = bootstrap.read_install()
    assert record and record["tier"] == "cpu", "run tests\\acceptance\\prepare_cpu_root.py first"
    engine = default_engine()
    try:
        info = engine.start()
        assert info.cuda_available is False
        load_s = engine.load()
        started = time.monotonic()
        result = engine.ocr_page(PAGE, "fast", max_new_tokens=6000, time_limit_s=1800.0)
        wall_s = time.monotonic() - started
    finally:
        engine.stop()
    truth = TRUTH.read_text(encoding="utf-8")
    score = cer(normalize(truth), normalize(clean_ocr(result.text)))
    report = {"page": PAGE.name, "mode": "fast", "device": "cpu", "dtype": "float32", "torch": info.torch,
              "cpu": cpu_name(), "ram_gb": round(hardware.ram_total_mib() / 1024),
              "load_seconds": round(load_s, 1), "seconds_per_page": round(wall_s, 1),
              "engine_seconds": round(result.seconds, 1), "output_tokens": result.output_tokens,
              "cer": round(score, 4), "timed_out": result.timed_out,
              "ships": score <= MAX_CER and wall_s <= MAX_SECONDS}
    (paths.data_root().parent / "result.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nCPU ACCEPTANCE:", json.dumps(report, ensure_ascii=False))
    print("record written to", write_record(report))
    assert result.text.strip(), "the engine returned no text"
    assert score <= MAX_CER, f"CER {score:.2%} is above {MAX_CER:.0%}"
    assert wall_s <= MAX_SECONDS, f"{wall_s:.0f} s per page is above {MAX_SECONDS:.0f} s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/acceptance -q`
Expected: `1 passed, 1 skipped` (the helper test passes; the acceptance test is skipped without `OWLOCR_CPU_ACCEPTANCE=1`).

Then prepare the CPU engine and run the real measurement. This downloads uv, Python 3.11, the cpu build of torch (about 0.12 GB) and the dependencies into `engine\cpu-acceptance\`, runs the device patch and the installer's own self-test on the processor (up to 30 minutes), and never uses the GPU:

```
py -3.11 tests\acceptance\prepare_cpu_root.py
```

Expected: one line per stage (`tools start` … `mark done`), then `CPU engine ready: {... "tier": "cpu" ...}`. If the self-test stage fails with `selftest_failed` or `patch_refused`, that is itself a failed acceptance: record it by running the test below anyway (it fails early) and continue with Step 3, outcome B.

```
$env:OWLOCR_HOME = "$PWD\engine\cpu-acceptance\data"; $env:OWLOCR_CONFIG = "$PWD\engine\cpu-acceptance\config"
$env:OWLOCR_CPU_ACCEPTANCE = "1"
py -3.11 -m pytest -m slow tests\acceptance\test_cpu_acceptance.py -s
Remove-Item Env:OWLOCR_HOME, Env:OWLOCR_CONFIG, Env:OWLOCR_CPU_ACCEPTANCE
```

Expected: a line `CPU ACCEPTANCE: {...}` with `seconds_per_page`, `cer` and `ships`, the line `record written to ...docs\research\2026-09-28-cpu-acceptance.md`, and the test passes (outcome A) or fails on the CER or time assertion (outcome B).

- [ ] **Step 3: Write minimal implementation**

Apply exactly one outcome. `N` below is `seconds_per_page` from the printed result rounded to a whole number, and `CPU` is the `cpu` value of the result (for the owner's PC `Intel(R) Core(TM) Ultra 7 265K`).

**Outcome A – the test passed (the CPU tier ships).** `CPU_TIER_ENABLED` stays `True`. In `owlocr/web/static/wizard_i18n.js` set the two speed strings (keep the JSON quoting):
- in `"cs"`: `"wz_speed_cpu": "asi N s na stránku (změřeno na procesoru CPU)",`
- in `"en"`: `"wz_speed_cpu": "about N s per page (measured on CPU)",`

In `README.md`, in the row that starts with `| Processor only |`, replace `not measured yet; roughly 1 to 5 minutes per page` with `about N s (measured on CPU)`. In `README.cs.md`, in the row that starts with `| Jen procesor |`, replace `zatím neměřeno; odhadem 1 až 5 minut na stránku` with `asi N s (změřeno na procesoru CPU)`.

**Outcome B – the test failed (0.1.0 ships GPU-only).** In `owlocr/hardware.py` change the line `CPU_TIER_ENABLED = True ...` to

```python
CPU_TIER_ENABLED = False            # CPU acceptance test failed (docs/research/2026-09-28-cpu-acceptance.md)
```

In `README.md`: delete the whole table row that starts with `| Processor only |`; replace the row that starts with `| Not supported |` with
`| Not supported | computers without an NVIDIA graphics card of the RTX 20 series or newer with at least 8 GB of graphics memory | | |`;
replace the sentence `With an older driver Owl OCR asks you to update it and can read with the processor in the meantime.` with `With an older driver the setup wizard asks you to update it.`; and directly below the table add the paragraph
`Owl OCR 0.1 reads only on an NVIDIA graphics card. Reading with the processor was tested and was too slow or too inaccurate (docs/research/2026-09-28-cpu-acceptance.md); the setup wizard tells you when a computer is not suitable.`

In `README.cs.md`: delete the row that starts with `| Jen procesor |`; replace the row that starts with `| Nepodporováno |` with
`| Nepodporováno | počítače bez grafické karty NVIDIA řady RTX 20 nebo novější s alespoň 8 GB grafické paměti | | |`;
replace the sentence `Se starším ovladačem vás Owl OCR požádá o aktualizaci a mezitím může číst procesorem.` with `Se starším ovladačem vás průvodce nastavením požádá o aktualizaci.`; and directly below the table add the paragraph
`Owl OCR 0.1 čte jen na grafické kartě NVIDIA. Čtení procesorem bylo vyzkoušeno a bylo příliš pomalé nebo nepřesné (docs/research/2026-09-28-cpu-acceptance.md); průvodce nastavením řekne, když počítač nevyhovuje.`

In both outcomes the wizard needs no other change: it shows `wz_hw_gpu_only` by itself when the probe reports `cpu_tier_enabled: false`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_hardware_tiers.py tests/test_wizard_strings.py tests/test_readme.py tests/acceptance -q`
Expected: all pass (the tier table tests force `CPU_TIER_ENABLED = True` through their autouse fixture, so they pass in both outcomes; the acceptance test is skipped again).

- [ ] **Step 5: Commit**

```
git add tests/acceptance docs/research/2026-09-28-cpu-acceptance.md owlocr/hardware.py owlocr/web/static/wizard_i18n.js README.md README.cs.md
git commit -m "Record the CPU acceptance test and apply its decision" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 31: Release 0.1.0

**Files:**
- Create: `packaging/scrub_local_paths.py`, `docs/release-notes-0.1.0.md`, `docs/images/smartscreen-1.png`, `docs/images/smartscreen-2.png`
- Test: `tests/test_scrub.py`, `tests/test_release_ready.py`

**Interfaces:**
- Consumes: everything above; `dist\` from `packaging\build.py`; `gh` (GitHub CLI, logged in as `romelsteel`).
- Produces: the public repository `romelsteel/owl-ocr` with a fresh one-commit history and the GitHub release `v0.1.0` with the installer, the portable zip and `SHA256SUMS.txt`.

Why a fresh history (design 12): the current history contains a research file with local paths and the owner's Windows user name. Scrubbing the working tree is not enough, because old commits keep the text; the public repository therefore starts from a single new commit, and the old private repository is renamed and stays private.

**Every outward-facing step (renaming the repository, creating the new repository, pushing, changing visibility, creating the release) needs the owner's explicit confirmation at that moment. Ask, wait for a clear yes, then run exactly that one command. A yes for one step is not a yes for the next.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_scrub.py`:

```python
import os
import sys

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import scrub_local_paths as scrub  # noqa: E402

USER = "jana"          # any name: the real one is read from USERNAME at run time


def test_windows_paths_become_userprofile():
    text = r"Python 3.11.9 only (`C:\Users\jana\AppData\Local\Programs\Python\Python311`)"
    assert scrub.scrub_text(text, USER) == (r"Python 3.11.9 only (`%USERPROFILE%\AppData\Local\Programs\Python\Python311`)", 1)
    assert scrub.scrub_text(r"`C:\Users\Jana\Desktop\OCR project` is empty", USER)[0] == r"`%USERPROFILE%\Desktop\OCR project` is empty"
    assert scrub.scrub_text("C:/Users/jana/x", USER)[0] == "%USERPROFILE%/x"


def test_escaped_and_mangled_forms():
    assert scrub.scrub_text('"C:\\\\Users\\\\jana\\\\Desktop"', USER)[0] == '"%USERPROFILE%\\\\Desktop"'
    mangled = r"C:\Users\jana\.claude\projects\C--Users-jana-Desktop-Claude-code\memory"
    assert scrub.scrub_text(mangled, USER) == (r"%USERPROFILE%\.claude\projects\C--Users-<user>-Desktop-Claude-code\memory", 2)


def test_other_names_and_words_are_left_alone():
    text = r"janapi C:\Users\janak\x and C:\Users\Public"
    assert scrub.scrub_text(text, USER) == (text, 0)


def test_the_script_does_not_contain_the_user_name():
    user = os.environ.get("USERNAME", "").strip().lower()
    source = (REPO / "packaging" / "scrub_local_paths.py").read_text(encoding="utf-8").lower()
    assert user and user not in source
```

Create `tests/test_release_ready.py`:

```python
"""Checks before a public release (plan D, task 31). Run with OWLOCR_RELEASE_CHECK=1."""
import os
import subprocess
import sys

import pytest

from owlocr import __version__
from tests.conftest import REPO

pytestmark = pytest.mark.skipif(os.environ.get("OWLOCR_RELEASE_CHECK") != "1",
                                reason="release check: set OWLOCR_RELEASE_CHECK=1")
DIST = REPO / "dist"
ARTEFACTS = (f"OwlOCR-{__version__}-setup.exe", f"OwlOCR-{__version__}-portable-win64.zip")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def test_smartscreen_screenshots_exist():
    for n in (1, 2):
        shot = REPO / "docs" / "images" / f"smartscreen-{n}.png"
        assert shot.is_file() and shot.stat().st_size > 10_000, shot


def test_no_local_paths_or_user_name_in_tracked_files():
    done = subprocess.run([sys.executable, str(REPO / "packaging" / "scrub_local_paths.py"), "--check"],
                          cwd=REPO, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_nothing_from_samples_is_tracked():
    assert [f for f in tracked() if f.startswith("samples/")] == []


def test_cpu_decision_is_recorded():
    record = (REPO / "docs" / "research" / "2026-09-28-cpu-acceptance.md").read_text(encoding="utf-8")
    assert "Result: **" in record


def test_release_notes_and_version():
    notes = (REPO / "docs" / f"release-notes-{__version__}.md").read_text(encoding="utf-8")
    assert f"Owl OCR {__version__}" in notes


def test_artefacts_exist_are_small_enough_and_match_the_sums():
    sums = (DIST / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    for name in ARTEFACTS:
        path = DIST / name
        assert path.is_file(), name
        assert path.stat().st_size < 2 * 1024**3, name             # GitHub's per-file limit
        assert any(line.endswith("  " + name) for line in sums), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_scrub.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'scrub_local_paths'`.

Run: `$env:OWLOCR_RELEASE_CHECK = "1"; py -3.11 -m pytest tests/test_release_ready.py -q; Remove-Item Env:OWLOCR_RELEASE_CHECK`
Expected: failures for the missing screenshots, the missing scrub script, the missing release notes and the missing `dist\` artefacts.

- [ ] **Step 3: Write minimal implementation (the release checklist)**

Work through the list in this order. Stop at the first item that does not match its expected result and fix the cause first.

0. **Scrubber and release notes.** Create `packaging/scrub_local_paths.py`:

```python
"""Removes the owner's local paths and Windows user name from tracked text files before the
repository becomes public (design 12, "Going public").

    py -3.11 packaging\\scrub_local_paths.py           rewrite the files, list what changed
    py -3.11 packaging\\scrub_local_paths.py --check   only list; exit code 1 when something is found

The user name is read from the environment (USERNAME), so it never has to be written into this
public file. C:\\Users\\<name>\\ becomes %USERPROFILE%\\ and a path mangled as C--Users-<name>-
(Claude's project folders) becomes C--Users-<user>-.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip", ".exe", ".dll", ".safetensors", ".bin",
                   ".tif", ".tiff", ".webp", ".bmp", ".gif", ".docx"}


def patterns(user: str) -> list[tuple[re.Pattern, str]]:
    name = re.escape(user)
    return [
        (re.compile(rf"[A-Za-z]:\\\\Users\\\\{name}\\\\", re.I), r"%USERPROFILE%\\\\"),   # escaped in JSON/Python
        (re.compile(rf"[A-Za-z]:\\Users\\{name}(?=\\|\b)", re.I), r"%USERPROFILE%"),
        (re.compile(rf"[A-Za-z]:/Users/{name}(?=/|\b)", re.I), "%USERPROFILE%"),
        (re.compile(rf"[A-Za-z]--Users-{name}-", re.I), "C--Users-<user>-"),
    ]


def scrub_text(text: str, user: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in patterns(user):
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [REPO / name for name in out.decode("utf-8").split("\0") if name]


def main(argv: list[str]) -> int:
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        print("USERNAME is not set")
        return 2
    check_only = "--check" in argv
    found = 0
    for path in tracked_files():
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, count = scrub_text(text, user)
        if count:
            found += count
            print(f"{path.relative_to(REPO)}: {count}")
            if not check_only:
                path.write_text(new, encoding="utf-8")
    print(f"{found} occurrence(s) {'found' if check_only else 'replaced'}")
    return 1 if (check_only and found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

   Create `docs/release-notes-0.1.0.md`:

```markdown
Owl OCR 0.1.0 is the first public release: offline OCR for Windows built on Baidu's open-source
Unlimited-OCR model, made for scanned Czech documents and fine with English.

## Download

- `OwlOCR-0.1.0-setup.exe`: installs for your user only, no administrator rights needed.
- `OwlOCR-0.1.0-portable-win64.zip`: unpack anywhere and run `OwlOCR.exe`.
- `SHA256SUMS.txt`: checksums of both files.

Windows SmartScreen warns about the installer because it is not code-signed: click
**More info** and then **Run anyway**. The README explains why and shows how to check the checksum.

## What you need

An NVIDIA graphics card with at least 8 GB of memory (10 GB or more for Quality mode) and
driver 570.65 or newer, or a PC with at least 16 GB of RAM and no suitable graphics card: the
processor-only mode is included in this release (the setup wizard tells you which mode your
computer gets). Processor-only mode is slow: about 30 s for a short page on a fast processor;
dense pages and slower PCs take several times longer. On the first start the wizard downloads
the reading engine once: about 10 GB, 16 GB of disk space. After that Owl OCR works offline.

## In this release

- Scanned and born-digital PDFs, photos, screenshots and images; Markdown, text, Word and
  searchable PDF; copy to clipboard.
- Queue with pause, resume and cancel that survives closing the app.
- Markdown export can link pictures in the Obsidian style (Settings, "Image links").
- Quality and Fast modes, review screen, dictionary marks (Czech and English), Czech and English interface.
- About 3 wrong words in 100 on real Czech scans. The text is read by a machine: check it
  before you quote it. See the README for the details and the known limits.

## Česky

První veřejná verze Owl OCR: offline OCR pro Windows postavené na otevřeném modelu Unlimited-OCR
od Baidu, dělané pro naskenované české dokumenty. Instalátor (`OwlOCR-0.1.0-setup.exe`) nepotřebuje
práva správce, přenosná verze je v zipu. Při prvním spuštění se jednou stáhne asi 10 GB. Podrobnosti
jsou v souboru README.cs.md.
```

   Then `py -3.11 -m pytest tests/test_scrub.py -q` → `4 passed`, and commit:
   ```
   git add packaging/scrub_local_paths.py tests/test_scrub.py tests/test_release_ready.py docs/release-notes-0.1.0.md
   git commit -m "Add release checks, path scrubber and release notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
   ```
1. **All tests.** `py -3.11 -m pytest` → 0 failed (the `gpu` tests are deselected by the default options; the acceptance and release checks are skipped).
2. **GPU accuracy test.** First check free VRAM: `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` must print at least `9500`; if not, close games, video and recording software and check again (never run the GPU tests with less). Then, with the development engine of plan A:
   ```
   $env:OWLOCR_HOME = "$PWD\engine"; $env:OWLOCR_CONFIG = "$PWD\engine\config"
   py -3.11 -m pytest -m gpu -q
   Remove-Item Env:OWLOCR_HOME, Env:OWLOCR_CONFIG
   ```
   Expected: all `gpu` tests pass (design 1.3 point 4: CER ≤ 3 % and ≥ 95 % of accented letters in Quality mode).
3. **Build.** Close any running Owl OCR, then `py packaging\build.py`. Expected: `smoke test passed`, `dist\OwlOCR-0.1.0-setup.exe`, `dist\OwlOCR-0.1.0-portable-win64.zip`, `dist\SHA256SUMS.txt`.
4. **Real installation by the owner** (not from an AI session: writes to `%LOCALAPPDATA%` from a session are redirected, so only a normal start shows the real behaviour). Ask the owner to:
   1. Open `dist` in Explorer and double-click `OwlOCR-0.1.0-setup.exe`.
   2. When the blue SmartScreen window appears, press Win+Shift+S and save a screenshot of it as `docs\images\smartscreen-1.png`; click **More info**, take the second screenshot as `docs\images\smartscreen-2.png`, then click **Run anyway**.
   3. Install with the defaults (per-user, no administrator prompt must appear) and tick "Launch Owl OCR" at the end.
   4. In the wizard: Welcome → Next; Hardware must show the RTX 4080 SUPER and "Graphics card – full quality" → Next; Location: keep `%LOCALAPPDATA%\OwlOCR`, tick "Copy instead of move" (so the development engine in the repository keeps working), click "I already have the engine" and choose `%USERPROFILE%\Desktop\OCR project\engine`; expected "Model found and checked. It will not be downloaded." → Install. Expected: tools, python, venv, torch (about 2.9 GB download), deps, worker run; model shows "already done"; patch shows "already done"; the self-test reads the page; Self-test shows the seconds; Done → Start using Owl OCR.
   5. The dictionary step offers Czech and English, both ticked: keep the defaults and click "Download selected"; both rows must turn to "installed" within a few seconds, then Next → Done.
   6. Drop one scanned PDF on the window, start the queue and wait until the job is done; open the folder and check the Markdown and text files.
   7. With the Czech dictionary installed, process one Czech page that has a reading error (for example `tests\fixtures\pages\03_small_print_clean.png`, where the spike measured a few wrong accents, or a real textbook page) and open it in the review screen: words the dictionary does not know must be underlined as suspicious, and a repaired word shows its original on hover.
   8. Export that document as a searchable PDF (`<name>.ocr.pdf`), open it in a PDF reader (Microsoft Edge or Adobe Acrobat Reader), press Ctrl+F and search for a Czech word with diacritics that is on the page (for example `lékařské` on the letter page, or `přičemž`); the reader must find it and highlight roughly the right area (block-level placement, README).
   9. Close the window. Within a few seconds no engine Python may remain: in Task Manager → Details there is no `python.exe` whose path is under `%LOCALAPPDATA%\OwlOCR\engine`. From a session this can be read (reading is not redirected):
      ```
      Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, ExecutablePath
      ```
      Expected: no line with `\OwlOCR\engine\`.
   10. Start Owl OCR again from the Start menu, start a job, and while it reads end `OwlOCR.exe` in Task Manager (End task). Expected: the engine's `python.exe` is gone within 5 seconds (Job Object, design 5.6) and on the next start the job continues where it stopped.
   11. (R-T31-2) Drag a file from Explorer onto the window: it joins the queue. Switch the language CZ/EN and the light/dark theme; the About screen shows the version and the folders.
   12. (R-T31-2) Clipboard test, only with the owner's agreement (it overwrites the clipboard): "Copy text" on the finished job, paste into Notepad, Czech letters intact.
   13. (R-T31-2) Settings, "Odkazy na obrázky: Obsidian", re-export a page with a picture from the review screen; "Otevřít složku s obrázky" opens the `_images` folder.
   14. (R-T31-2) Click Queue during the wizard (before finishing): the notice offers "Dokončit nastavení" (only if a fresh wizard run is available; otherwise note as checked in task 22).
5. **Commit the screenshots.** `git add docs/images/smartscreen-1.png docs/images/smartscreen-2.png` and `git commit -m "Add SmartScreen screenshots for the README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
6. **Scrub local paths.** `py -3.11 packaging\scrub_local_paths.py` (it prints each changed file; expected at least `docs\research\2026-09-27-unlimited-ocr-factsheet.md`), review `git diff` (only paths may change: `C:\Users\<name>\` becomes `%USERPROFILE%\`), then `git commit -am "Remove local paths before publishing" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`. `py -3.11 packaging\scrub_local_paths.py --check` must now print `0 occurrence(s) found`. Then look for the user name outside paths: `git grep -n -i $env:USERNAME` and show every hit to the owner; the owner's real name in `LICENSE` and `pyproject.toml` is intended, anything else (for example an e-mail address) is removed or kept only on the owner's word, then committed the same way.
7. **Release check.** `$env:OWLOCR_RELEASE_CHECK = "1"; py -3.11 -m pytest tests/test_release_ready.py -q; Remove-Item Env:OWLOCR_RELEASE_CHECK` → `7 passed` (R-T31-3 adds `test_no_user_name_in_artefacts`).
8. **Fresh history, locally.** Ask the owner which author e-mail the public commit should carry (the current `git config user.email` is a personal address; GitHub's private address `<id>+romelsteel@users.noreply.github.com` is shown at https://github.com/settings/emails). Then:
   ```
   git switch --orphan public-main
   git restore --source main --staged --worktree .
   git -c user.email="<the address the owner chose>" commit -m "Owl OCR 0.1.0" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
   git log --oneline public-main
   git ls-files samples
   py -3.11 packaging\scrub_local_paths.py --check
   ```
   Replace `main` in the restore command with the name of the branch that holds the finished work if it is not `main` (for example `plan-d-install-release`). Expected: exactly one commit; `git ls-files samples` prints nothing; the scrub check prints `0 occurrence(s) found`. `.gitignore` keeps `engine\`, `dist\`, `build\`, `samples\` and `.claude\` out.
   Before step 9, with the owner's OK, run `gh auth status` (read-only) and confirm the account is `romelsteel` (R-T31-4).

9. **Keep the old history private.** Ask the owner: "Rename the private repository romelsteel/owl-ocr to romelsteel/owl-ocr-dev so its history stays private?" Only after a yes:
   ```
   gh repo rename owl-ocr-dev --repo romelsteel/owl-ocr --yes
   git remote set-url origin https://github.com/romelsteel/owl-ocr-dev.git
   ```
10. **Create the new, still private repository.** Ask the owner: "Create a new private repository romelsteel/owl-ocr for the public history?" Only after a yes:
    ```
    gh repo create romelsteel/owl-ocr --private --description "Offline OCR for Windows built on Baidu's Unlimited-OCR model"
    git remote add public https://github.com/romelsteel/owl-ocr.git
    ```
11. **Push the fresh history.** Ask the owner: "Push the single commit of public-main as main of romelsteel/owl-ocr?" Only after a yes:
    ```
    git push public public-main:main
    gh api repos/romelsteel/owl-ocr/commits --jq length
    ```
    Expected: `1`.
12. **Make it public.** Ask the owner: "Make romelsteel/owl-ocr public now?" Only after a yes:
    ```
    gh repo edit romelsteel/owl-ocr --visibility public --accept-visibility-change-consequences
    ```
13. **Create the release.** Ask the owner: "Create the GitHub release v0.1.0 with the installer, the portable zip and SHA256SUMS.txt?" Only after a yes:
    ```
    gh release create v0.1.0 dist\OwlOCR-0.1.0-setup.exe dist\OwlOCR-0.1.0-portable-win64.zip dist\SHA256SUMS.txt --repo romelsteel/owl-ocr --target main --title "Owl OCR 0.1.0" --notes-file docs\release-notes-0.1.0.md
    gh release view v0.1.0 --repo romelsteel/owl-ocr --json assets --jq ".assets[].name"
    ```
    Expected: the three file names.

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:OWLOCR_RELEASE_CHECK = "1"; py -3.11 -m pytest tests/test_release_ready.py tests/test_scrub.py -q; Remove-Item Env:OWLOCR_RELEASE_CHECK`
Expected: `11 passed`. Also open https://github.com/romelsteel/owl-ocr in a private browser window: the README renders with both screenshots, and the Releases page offers the three files.

- [ ] **Step 5: Commit**

Everything was committed during Step 3. Confirm with `git status` (clean on `public-main`). Pushing anything more, now or later, again needs the owner's explicit instruction.

---

## Contract notes

Additions to and interpretations of `2026-09-28-owl-ocr-interfaces.md`. Nothing in the contract was renamed or reshaped.

| # | Item | Kind | Detail |
|---|---|---|---|
| 1 | `Tier.reason` | interpretation | a code the UI translates: `ok`, `driver_too_old`, `gpu_too_old`, `vram_too_small`, `no_nvidia_gpu`, `ram_too_small` (the acceptance script uses `acceptance_test`) |
| 2 | `owlocr/hardware.py` | addition | `tier_by_name(name, reason="ok")`, `compute_cap_from_name(name)`, `parse_driver_version(text)`, `parse_nvidia_smi(text, with_compute_cap)`, constants `CREATE_NO_WINDOW`, `TORCH_INDEXES`, `MIN_DRIVER_CU128 = (570, 65)`, `GPU_FULL_MIN_VRAM_MIB = 9984`, `GPU_REDUCED_MIN_VRAM_MIB = 7936`, `CPU_MIN_RAM_MIB = 15360`, `CPU_TIER_ENABLED`. Plan A's `free_vram_mib`, `REQUIRED_FREE_VRAM_MIB` and `_CREATE_NO_WINDOW` are untouched |
| 3 | Tier table | interpretation | thresholds tolerate the sizes Windows reports ("10 GB" → 9,984 MiB, "8 GB" → 7,936 MiB, "16 GB RAM" → 15,360 MiB); a Turing card (compute capability 7.5) with more than 10 GB is `gpu_reduced`, never `gpu_full`; with several GPUs the best one decides; an old driver with enough RAM gives `cpu` with reason `driver_too_old` (the "offer the CPU tier meanwhile" of design 6.4), so `/api/wizard/install` needs no body |
| 4 | Engine installer modules | addition | `owlocr/engine/install_kit.py` (building blocks), `owlocr/engine/stages.py` (`CHECKS`, `ACTIONS` and the ten check/action pairs), `owlocr/engine/uvtool.py` (download, command runner). `BootstrapError` is defined in `install_kit` and imported into `bootstrap`, so `owlocr.engine.bootstrap.BootstrapError` is the contract class |
| 5 | `owlocr/engine/bootstrap.py` | addition | `REQUIRED_FREE_BYTES`, `required_free_bytes(already_present)`, `load_pins()`, `was_interrupted()`, `reset_install()`, `sync_worker_files()`, private `_run(tier, on_event, cancel, deps)` with injectable `install_kit.Deps` (uv path, command runner, downloader, store, engine factory, free VRAM, free disk) |
| 6 | `install.json` | decision | keys `format`, `fingerprint`, `tier`, `device`, `dtype`, `default_mode`, `torch_index`, `python_version`, `uv`, `engine_id`, `revision`, `torch`, `torchvision`, `transformers`, `requirements_sha256`, `patched`, `selftest_seconds`, `app_version`, `installed_at`. No `python` key: plan A's `default_engine()` reads `python` as the interpreter path and uses `engine_python()` when it is absent; `engine_id`, `device`, `dtype` are the keys it needs |
| 7 | `is_installed()` | decision | also accepts plan A's development record (`"tier": "development"` from `scripts/dev_engine.py`) when its Python, its worker and the model are present, so development keeps working after plan D |
| 8 | Stage `patch` | decision | patches only `modeling_unlimitedocr.py` (the other two files contain no CUDA-only code and are checked, not modified, so `modeling_deepseekv2.py` stays unmodified Apache code); on GPU tiers it restores the pristine file when an earlier CPU installation patched it. The manifest keeps the pristine hashes under `modeling_unlimitedocr.py.orig` and the patched size and sha256 under the file's own name, in plan A's manifest format |
| 9 | `worker/device_patch.py` | addition | run-time override through `OWLOCR_DEVICE` / `OWLOCR_DTYPE`; the worker does not need to set them because the patch bakes in its arguments |
| 10 | Self-test | decision | page `owlocr/web/static/selftest.png` (= `01_letter_clean.png`), tier default mode, at most 1,500 new tokens, time limit 180 s (GPU) or 1,800 s (CPU), pass = at least 3 of 5 expected words; it uses plan A's `SubprocessEngine` and always stops it |
| 11 | `settings.mode_default` | decision | set to the tier's default mode at the end of the first installation, unless it differs from `DEFAULTS["mode_default"]` (the user changed it) |
| 12 | HTTP additions | addition | `GET /api/wizard/probe` also returns `required_bytes`, `interrupted`, `installed`, `model_ready`, `install`, `env_override`, `logs_dir`, `cpu_tier_enabled`; `POST /api/wizard/adopt` accepts `"copy": true`; `POST /api/wizard/install` returns `{"started": false}` when an installation already runs; new `POST /api/engine/reinstall` → `{}` and `POST /api/engine/move {"path"}` → `{"data_root", "free_bytes"}`; errors are `{"error": "<code>: <details>"}` with 400/409/500 |
| 13 | Runner use | decision | before touching engine files the routes call plan B's `Runner.stop_engine()` (thread stays alive) and refuse with 409 while the queue runs; `Runner.shutdown()` is never called by plan D |
| 14 | `owlocr/jobs/engines.py` (plan B) | change | `engine_installed()` uses `bootstrap.is_installed()` instead of building `default_engine()`, because `default_engine()` does not check the model; plan B's test `test_answer_is_cached_until_forgotten` is replaced accordingly; `forget_installed()` is called after every installation, adoption, move, reinstall and removal |
| 15 | UI | decision | wizard strings live in `owlocr/web/static/wizard_i18n.js` (`wz_` keys, strict JSON between markers) and are merged into plan B's `OWL_STRINGS`; `window.OwlWizard = {init, show, render, reinstall, move, renderDictionaries, verify, remove, errorText}` (task 22: Verify, Reinstall, Move and Remove share one busy state that disables the four engine buttons; `errorText(err)` translates every `wz_error_*` code, unknown codes fall back to the generic text); plan B's placeholder view, its two buttons and its four `wizard_*` strings are removed; `app.js` hands `api`, `toast`, `confirmDialog`, `showView` to the wizard |
| 16 | `OWLOCR_DEMO_INSTALL=1` | addition | makes the Install step walk through the stages without installing anything (UI smoke test) |
| 17 | `packaging/launcher.py` | addition | PyInstaller entry; `OwlOCR.exe --remove-data` (used by the uninstaller) runs `owlocr.uninstall.main()`; everything else goes to plan B's `owlocr.__main__.main()` |
| 18 | `owlocr/engine/relocate.py`, `owlocr/uninstall.py` | addition | `DATA_ITEMS`, `LocationError`, `free_bytes`, `has_data`, `validate_location`, `choose_location`, `move_data_root`; `remove_all_data`, `main` |
| 19 | CPU acceptance | deviation | the GPU is hidden with `CUDA_VISIBLE_DEVICES=-1`, not `""`, because an empty value does not hide it on the owner's PC (plan A, task 16) and Windows shells cannot set an empty variable |
| 20 | Engine requirements | decision | plan A's `worker/requirements-engine.txt` is used unchanged; a change of it re-runs the deps stage (sha256 stamp) and makes `is_installed()` false until the wizard ran again |
| 21 | Worker updates | decision | `make_blueprint` calls `bootstrap.sync_worker_files()` once at server start, so an app update brings newer worker scripts into an installed engine without the wizard |
| 22 | Third-party notices | decision | the roots are read from `requirements.txt`; PyInstaller is always listed (bootloader) |
| 23 | Dictionary download (design 9.3, plan C contract note 7) | addition | plan C's `dictionaries.download` / `remove` are called by the new blueprint `owlocr/web/dictionaries_api.py`: `GET /api/dictionaries` → `{"languages": [{"language", "name", "installed", "size", "licence", "source", "running", "done", "total", "error"}]}`, `POST /api/dictionaries/<language>` → `{"started"}` (download in a background thread, progress by polling the GET route), `DELETE /api/dictionaries/<language>` → `{}`; errors `dictionary_failed`, `dictionary_running`, `unknown_language`. After a failed download of a language that was not installed before, `dictionaries.remove` deletes the verified partial files. No new reset function was needed: plan C's `spellcheck._reset_cache()` exists and `download` / `remove` call it; the job calls it once more after success |
| 24 | Moving the data root | decision | a move keeps the uv cache, Python and the model; the venv is rebuilt by the wizard's Continue without downloading, because venvs store absolute paths |
| 25 | Wizard step "Dictionaries" | addition | an optional seventh step between Self-test and Done (design 6.1 lists six): Czech and English pre-ticked, sizes and licence names from the manifest, Skip always possible; `OwlWizard.renderDictionaries(container)` draws the Settings section into a new empty `<div id="dictSettings" class="wz-dicts-panel">` of plan B's Settings view; `app.js` calls it when Settings opens. Moving the data root also moves `dictionaries` (it is in `DATA_ITEMS`) |
| 26 | Packaging of plan C's files | decision | the spec bundles `owlocr/pipeline/dictionaries.json` and `owlocr/export/fonts/` at their repository paths (plan C reads them next to their modules via `__file__`); `tests/test_spec.py` scans the code for every data file read through `resource_path`, `*_REL` constants or `__file__`-relative paths and fails when one is not bundled where the code looks; `build.py` checks `REQUIRED_BUNDLE` inside `_internal` and the smoke test calls `/api/dictionaries`; the notices list DejaVu Sans 2.37 (Bitstream Vera licence and public domain) from `notices.FONTS` and name the dictionaries as optional downloads |
| 27 | `remove_engine()` / `reset_install()` (R-T8-1) | decision | both raise `BootstrapError("development: …")` before deleting anything when `install.json` holds `"tier": "development"` (plan A's `scripts/dev_engine.py` record), so a development engine is never removed or reset by the app; the routes answer 409 |
| 28 | Queue follows the data root (R-T16-1/2, R-T17-1) | decision | `JobQueue.relocate(path)` points the queue at a new `queue.json` and saves it there; `make_blueprint(runner, controller=None, probe_fn=None, queue=None)`; after `/api/wizard/location` or `/api/engine/move` changes the data root, the queue saves to the new `queue.json` and the old one is deleted |
| 29 | Engine factory and queue start (R-T19-1/2, task 19) | decision | `create_app` registers `make_blueprint(runner, queue=queue)` and `make_dictionaries_blueprint()`; `engines.engine_factory()` raises `EngineError("not_installed")` when `bootstrap.is_installed()` is false (unless `OWLOCR_ENGINE_WORKER` is set), so the runner shows plan B's not-installed notice instead of starting a broken engine; `POST /api/run/start` answers 409 `{"error": "busy: another engine action is running"}` while the wizard blueprint's `file_ops_busy()` is true |
| 30 | Not-installed notice and finish button (R-T22-2, task 22) | decision | plan B's yellow notice is also shown when `/api/status` says `installed === false` and the wizard view is not shown (a synthetic `{code: 'not_installed'}`; hidden while the wizard is shown); its button `noticeWizard` ("Dokončit nastavení" / "Finish setup", key `notice_finish_setup`) opens the wizard at the step it was left on; the dictionary step pre-ticks Czech and English (both can be unticked) |
| 31 | Image-link setting and images folder (task 22b, plan C note 19) | addition | job JSON gains `images_dir`: the existing `<md stem>_images` folder next to the job's Markdown output, else `null` (`server.images_dir(job)`); a done job shows "Otevřít složku s obrázky" (`btn_open_images`) only when it is set, opened through plan B's bridge `open_folder`; the Settings select `setImageLinks` (Markdown / Obsidian, key `set_image_links`) writes plan C's `image_links` |
| 32 | Build venv and bundle checks (tasks 23/26/28, R-T28-1..7) | addition | `OwlOCR.exe --check-imports` imports the export/UI libraries, writes a Word file and a searchable PDF and records the result in `<logs>\check-imports.txt`; `packaging\build.py` re-starts itself in `build\venv` (made from `requirements.txt` + `requirements-build.txt`, PyInstaller 6.21.0, stamp `owl-requirements.sha256`); the build fails on engine modules in `_internal` or in the PYZ, missing bundle files, bundled packages without a row in `THIRD_PARTY_NOTICES.md` and unwanted data (spylls `.dic`/`.aff`, `reportlab/fonts`), and warns when `C:\Users\<user>` appears in the output; `LICENSE` and `THIRD_PARTY_NOTICES.md` also sit next to `OwlOCR.exe`; the spec excludes setuptools, pkg_resources, distutils and `_distutils_hack` (build tools pulled in by cffi's compile helper) and PyInstaller, altgraph, pefile, ordlookup and win32ctypes (pulled in by the packages' own PyInstaller hook modules, which the spec filters out); the build also fails on unlisted top-level modules in the PYZ or top-level .pyd files and on any build-tool module left in the PYZ |
| 33 | RedirectionGuard and links in the engine folder (real install, 2026-09-29) | decision | the WebView2 runtime turns on Windows' RedirectionGuard (ProcessRedirectionTrustPolicy, EnforceRedirectionTrust) in `OwlOCR.exe` and every child process inherits it, so traversing a user-created junction fails with os error 448; uv's `python install` creates the junction `cpython-3.11-windows-x86_64-none` and then fails on it after Python is complete. The installer never leaves or follows user-created junctions in the engine folder: `install_kit.remove_python_links()` deletes every link directly in `engine\python` without following it (on success and on that specific failure of the python stage, and in `check_python`, `check_venv`, `do_venv`, `do_torch`, `do_deps`, so a leftover link heals on retry); `managed_python()` ignores links and picks the highest real `cpython-3.11.<patch>-*` folder; the python stage accepts exit code != 0 only when the output names the minor-version link or os error 448 and the full-version python.exe answers `Python 3.11.x`; every later uv call names that python.exe directly |

## Self-review

### Contract items marked plan D

| Contract item | Task |
|---|---|
| `bootstrap.STAGES` | 8 |
| `bootstrap.StageEvent` (`stage`, `state`, `done`, `total`, `message`; states `start`, `progress`, `done`, `skipped`, `failed`) | 8 |
| `bootstrap.install_path()` | 8 |
| `bootstrap.is_installed()` | 8, 13 |
| `bootstrap.read_install()` | 8 |
| `bootstrap.run(tier, on_event, cancel)` | 8 (orchestration), 9–12 (stages), 13 (end to end) |
| `bootstrap.remove_engine()` | 8, 13, 17 |
| `bootstrap.BootstrapError` | 7, 8 |
| `hardware.Gpu`, `hardware.Tier` | 1 |
| `hardware.probe_gpus()` (CSV parsing, missing `compute_cap`, name table, never WMI) | 1 |
| `hardware.ram_total_mib()` | 1 |
| `hardware.choose_tier()` (table of design 6.4, driver floor 570.65) | 2 |
| `hardware.free_vram_mib`, `REQUIRED_FREE_VRAM_MIB` (plan A, extended not changed) | 1 |
| `GET /api/wizard/probe` | 16 |
| `POST /api/wizard/location` | 14, 16 |
| `POST /api/wizard/adopt` | 16 |
| `POST /api/wizard/install` | 16 |
| `POST /api/wizard/cancel` | 16 |
| `GET /api/wizard/progress` | 16 |
| `POST /api/engine/verify` | 17 |
| `POST /api/engine/remove` | 17 |
| Wizard routes on plan B's app | 19 |
| Plan C contract note 7: dictionaries downloaded on demand by the wizard or Settings | 18, 19, 22 |
| Plan C contract note 16: `dictionaries.json`, `owlocr/export/fonts/*` bundled; DejaVu Sans and plan C's packages in the notices | 25, 26, 28 |

### Stages of design 6.2

| Stage | Action, verified by | Task |
|---|---|---|
| tools | pinned uv, sha256 | 5 (pin), 6 (download), 9 |
| python | `uv python install 3.11` into `engine\python`, `python --version` | 9 |
| venv | `uv venv`, venv Python runs as 3.11 and points into `engine\python` | 9 |
| torch | `uv pip install torch==2.10.0 torchvision==0.25.0 --index-url <tier>`, import test with the exact build | 10 |
| deps | `uv pip install -r requirements-engine.txt`, import test and requirements stamp | 10 |
| model | `store.download` (14 files, sizes and hashes, manifest last) | 11 |
| worker | copy `worker\*.py` unchanged, licence files into the model folder | 11 |
| patch | CPU tier only: `device_patch.py`, sentinel present (restore on GPU) | 3, 11 |
| selftest | engine reads the test page, expected words | 12, 20 |
| mark | `install.json` | 12 |
| every stage idempotent, skipped when its check passes, cancel, events, `logs\install.log` | | 8, 13 |

### Rules of design 6.3

| Rule | Task |
|---|---|
| 1 `manifest.json` written after all files verify (plan A's store); the patch keeps it consistent | 3, 11 |
| 2 `install.json` written after the self-test | 12 |
| 3 later starts check files, versions and sizes only, no hashing, no network | 8 (`is_installed`), 19 (`/api/status`) |
| 4 "Verify engine" re-hashes on request | 17, 22 (plan B's button) |
| 5 resumable downloads; HF then ModelScope; Xet off (plan A's store); uv download resumable | 6, 11 |
| 6 16 GB free space checked before starting | 8 |
| 7 adopt "I already have the engine", verified by hash, moved or copied into the data root | 16, 22, 31 (real run) |
| 8 an app update with unchanged pins reuses the engine; a changed pin re-runs only the affected stage | 8, 10, 12, 16 (`sync_worker_files`), 13 |

### Design section 6.1 (wizard steps) and 6.4 (tiers)

| Item | Task |
|---|---|
| 1 Welcome, 2 Hardware, 3 Location with "I already have the engine", 4 Install with pause and survival of a restart, 5 Self-test with seconds, 6 Done | 21, 22 |
| optional dictionary step (Czech recommended, skippable) and the Settings Dictionaries section | 18, 21, 22 |
| free-space check, data-root selection, moving an existing data root | 8, 14, 16, 17 |
| CPU acceptance test with decision rule and GPU-only fallback | 30 |

### Design section 12

| Row | Task |
|---|---|
| Build: `py packaging\build.py`, PyInstaller onedir, no `.bat` | 26, 28 |
| Installer: Inno Setup, per-user into `%LOCALAPPDATA%\Programs\OwlOCR`, no admin, Start Menu, uninstaller offering to remove engine and data | 15, 23, 27 |
| Portable: the onedir folder zipped | 28 |
| GitHub release limit 2 GiB per file | 28 (sizes printed), 31 (`test_release_ready`) |
| Windowed build: null streams | 23 (and plan B's `__main__`) |
| Smoke test: every build starts once, shows the window, answers `/api/health` (also `/api/dictionaries`, bundled data files checked) | 28 |
| Licences: MIT `LICENSE` (plan A), `THIRD_PARTY_NOTICES.md` (with DejaVu Sans and plan C's packages), Baidu MIT + Apache-2.0 text in the model folder, patched file marked as modified | 3, 4, 11, 25 |
| README: what it does, hardware table, first-run download, SmartScreen with screenshots, accuracy with the honest caveat, privacy (also searchable PDF limit, optional dictionaries and uninstall) | 29, 30, 31 |
| Going public: fresh history, local paths removed | 31 |
| Versioning: `0.1.0` | 28, 31 |

### Tasks and owner decisions added on 2026-09-28/29 (rulings.md)

| Item | Task |
|---|---|
| Czech UI text formal (vykání) everywhere, old and new; enforced by `test_czech_ui_speaks_formally` | 21 |
| "Dokončit nastavení" button in the not-installed notice (contract note 30) | 21, 22 |
| English dictionary pre-ticked next to Czech (both can be unticked) | 22 |
| Markdown image-link setting (Markdown / Obsidian) and "Otevřít složku s obrázky" in the queue (contract note 31) | 22b |
| Build in a clean `buildenv` from `requirements.txt` + `requirements-build.txt` | 25, 28 |
| PyInstaller pinned at 6.21.0 (pyinstaller-hooks-contrib 2026.6) | 25, 28 |

### Placeholder search

The finished plan (including the amendment for plan C's dictionaries and packaging) was searched for `TBD`, `TODO`, `FIXME`, `XXX`, "add error handling", "similar to task", "write tests for" and for unexpanded template markers; none remain. Every code step contains complete code. Values that can only be known at build or release time are obtained by exact commands: the uv version, URL and sha256 (Task 5, `packaging\pin_uv.py`), the bundled package list (Task 25, `packaging\notices.py --check`), the measured CPU speed and error rate (Task 30, written by the test into `docs/research/2026-09-28-cpu-acceptance.md`), the SmartScreen screenshots and the author e-mail of the public commit (Task 31, chosen by the owner).
