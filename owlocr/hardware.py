"""Hardware facts. Plan A: free VRAM only. Plan D adds the GPU/RAM probe and tiers."""
import subprocess

REQUIRED_FREE_VRAM_MIB = {"quality": 9500, "fast": 7500}

_CREATE_NO_WINDOW = 0x08000000


def free_vram_mib() -> int | None:
    """Free memory of the first NVIDIA GPU in MiB, or None when there is no NVIDIA GPU."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                return int(float(line))
            except ValueError:
                return None
    return None


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
