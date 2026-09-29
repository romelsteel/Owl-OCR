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


# Boundary values of design 6.4 (off-by-one guards, final review triage #2).
@pytest.mark.parametrize("g, expected_name, expected_reason", [
    (gpu(total=9984, cap=8.6), "gpu_full", "ok"),
    (gpu(total=9983, cap=8.6), "gpu_reduced", "ok"),
    (gpu(total=7936, cap=8.6), "gpu_reduced", "ok"),
    (gpu(total=7935, cap=8.6), "cpu", "vram_too_small"),
    (gpu(total=16376, cap=7.5), "gpu_reduced", "ok"),
    (gpu(total=16376, cap=7.4), "cpu", "gpu_too_old"),
    (gpu(driver="570.65"), "gpu_full", "ok"),
    (gpu(driver="570.64"), "cpu", "driver_too_old"),
    (gpu(driver="not a version"), "cpu", "driver_too_old"),
    (gpu(name="NVIDIA Mystery Card", cap=None), "cpu", "gpu_too_old"),
])
def test_choose_tier_boundaries(monkeypatch, g, expected_name, expected_reason):
    monkeypatch.setattr(hardware, "CPU_TIER_ENABLED", True)
    tier = hardware.choose_tier([g], 32768)
    assert (tier.name, tier.reason) == (expected_name, expected_reason)


@pytest.mark.parametrize("ram, expected_name", [(15360, "cpu"), (15359, "unsupported")])
def test_cpu_ram_boundary(monkeypatch, ram, expected_name):
    monkeypatch.setattr(hardware, "CPU_TIER_ENABLED", True)
    assert hardware.choose_tier([], ram).name == expected_name
