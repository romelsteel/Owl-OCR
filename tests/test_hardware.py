import subprocess
from types import SimpleNamespace

from owlocr import hardware


def test_required_free_vram():
    assert hardware.REQUIRED_FREE_VRAM_MIB == {"quality": 9500, "fast": 7500}


def _fake_run(stdout="", returncode=0, exc=None):
    def run(cmd, **kwargs):
        assert cmd[0] == "nvidia-smi"
        assert "--query-gpu=memory.free" in cmd
        if exc:
            raise exc
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


def test_free_vram_first_gpu(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("15234\n8000\n"))
    assert hardware.free_vram_mib() == 15234


def test_no_nvidia_smi(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run(exc=FileNotFoundError()))
    assert hardware.free_vram_mib() is None


def test_nvidia_smi_fails(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("", returncode=9))
    assert hardware.free_vram_mib() is None


def test_nvidia_smi_timeout(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run",
                        _fake_run(exc=subprocess.TimeoutExpired("nvidia-smi", 15)))
    assert hardware.free_vram_mib() is None


def test_garbage_output(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("[N/A]\n"))
    assert hardware.free_vram_mib() is None
