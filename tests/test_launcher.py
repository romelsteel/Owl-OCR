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
    (home / ".owlocr-root").write_text("x", encoding="utf-8")   # only a marked folder counts as ours (plan B/D)
    config.mkdir()
    (config / "settings.json").write_text("{}", encoding="utf-8")
    done = subprocess.run([sys.executable, str(LAUNCHER), "--remove-data"], env=launcher_env(home, config),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert not (home / "engine").exists() and not (home / "models").exists()
    assert (home / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert not (config / "settings.json").exists()


def test_remove_data_refuses_while_the_app_runs(tmp_path, monkeypatch):
    import ctypes
    from ctypes import wintypes

    home, config = tmp_path / "data", tmp_path / "config"
    (home / "engine").mkdir(parents=True)
    (home / ".owlocr-root").write_text("x", encoding="utf-8")
    config.mkdir()
    (config / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OWLOCR_CONFIG", str(config))
    from owlocr.__main__ import mutex_name
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateMutexW(None, False, mutex_name())
    try:
        done = subprocess.run([sys.executable, str(LAUNCHER), "--remove-data"],
                              env=launcher_env(home, config), capture_output=True, text=True, timeout=120)
    finally:
        kernel32.CloseHandle(handle)
    assert done.returncode == 1, done.stderr
    assert "running" in done.stdout
    assert (home / "engine").is_dir() and (config / "settings.json").exists()


def test_check_imports_passes_from_source(tmp_path):
    home, config = tmp_path / "data", tmp_path / "config"
    done = subprocess.run([sys.executable, str(LAUNCHER), "--check-imports"], env=launcher_env(home, config),
                          capture_output=True, text=True, timeout=180)
    report = home / "logs" / "check-imports.txt"
    assert report.is_file(), done.stderr
    assert done.returncode == 0, report.read_text(encoding="utf-8")
    assert "ok" in report.read_text(encoding="utf-8")


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


def test_remove_data_refuses_when_the_running_check_fails(monkeypatch, capsys):
    """M-2: a failing mutex check must not crash (bootloader dialog); it refuses and deletes nothing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("owl_launcher_under_test", LAUNCHER)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    def broken():
        raise OSError("ctypes unavailable")

    def must_not_run():
        raise AssertionError("data removal ran although the running check failed")

    monkeypatch.setattr(launcher, "app_is_running", broken)
    monkeypatch.setattr("owlocr.uninstall.main", must_not_run)
    monkeypatch.setattr(sys, "argv", ["OwlOCR.exe", "--remove-data"])
    assert launcher.main() == 1
    assert "Nothing was deleted" in capsys.readouterr().out
