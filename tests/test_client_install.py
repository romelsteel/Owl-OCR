"""default_engine() and sweep_stale_worker()."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine, default_engine, sweep_stale_worker
from owlocr.engine.protocol import EngineError
from tests.conftest import FAKE_WORKER


def write_install(data: dict) -> None:
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps(data))


def test_not_installed_without_install_json():
    with pytest.raises(EngineError) as e:
        default_engine()
    assert e.value.kind == "not_installed"


def test_not_installed_when_python_missing():
    write_install({"engine_id": "unlimited_ocr", "device": "cuda"})
    with pytest.raises(EngineError) as e:
        default_engine()
    assert e.value.kind == "not_installed"


def test_standard_locations(owl_env):
    python = paths.engine_python()
    worker = paths.worker_dir() / "owl_worker.py"
    for f in (python, worker):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    write_install({"engine_id": "unlimited_ocr", "device": "cuda", "dtype": "bfloat16"})
    engine = default_engine()
    assert isinstance(engine, SubprocessEngine)
    assert engine.python == python and engine.worker_script == worker
    assert engine.model_dir == paths.model_dir("unlimited_ocr")
    assert (engine.device, engine.dtype) == ("cuda", "bfloat16")
    assert engine.log_file == paths.logs_dir() / "engine.log"


def test_overrides_and_cpu_default_dtype(tmp_path):
    write_install({"python": sys.executable, "worker_script": str(FAKE_WORKER),
                   "model_dir": str(tmp_path / "m"), "device": "cpu", "env": {"FAKE_WORKER": "slow"}})
    engine = default_engine()
    assert engine.python == Path(sys.executable)
    assert engine.worker_script == FAKE_WORKER
    assert engine.model_dir == tmp_path / "m"
    assert (engine.device, engine.dtype) == ("cpu", "float32")
    assert engine.env == {"FAKE_WORKER": "slow"}
    try:
        engine.load()
        assert engine.loaded
    finally:
        engine.stop()


def test_sweep_terminates_the_recorded_worker():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        paths.atomic_write_text(paths.engine_dir() / "worker.pid",
                                json.dumps({"pid": p.pid, "created": lifetime._process_create_time(p.pid)}))
        sweep_stale_worker()
        assert p.wait(timeout=5) == 1           # the exit code lifetime._terminate gives
        assert not lifetime.process_alive(p.pid)
        assert not (paths.engine_dir() / "worker.pid").exists()
    finally:
        p.kill()
        p.wait(timeout=5)


def test_sweep_spares_a_process_that_reused_the_pid():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        paths.atomic_write_text(paths.engine_dir() / "worker.pid", json.dumps({"pid": p.pid, "created": 12345}))
        sweep_stale_worker()
        time.sleep(0.3)
        assert p.poll() is None
        assert not (paths.engine_dir() / "worker.pid").exists()
    finally:
        p.kill()
        p.wait(timeout=5)


def test_sweep_without_or_with_broken_file():
    sweep_stale_worker()
    paths.atomic_write_text(paths.engine_dir() / "worker.pid", "garbage")
    sweep_stale_worker()
    assert not (paths.engine_dir() / "worker.pid").exists()


def _sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _record(worker: subprocess.Popen, owner: subprocess.Popen) -> None:
    paths.atomic_write_text(paths.engine_dir() / "worker.pid", json.dumps({
        "pid": worker.pid, "created": lifetime._process_create_time(worker.pid),
        "owner": owner.pid, "owner_created": lifetime._process_create_time(owner.pid)}))


def test_sweep_leaves_the_worker_of_a_running_owner_alone():
    """Another Owl OCR process (app or CLI) still owns the worker: it is not stale."""
    worker, owner = _sleeper(), _sleeper()
    try:
        _record(worker, owner)
        sweep_stale_worker()
        time.sleep(0.3)
        assert worker.poll() is None
        assert (paths.engine_dir() / "worker.pid").exists()      # still tracked for its owner
    finally:
        for p in (worker, owner):
            p.kill()
            p.wait(timeout=5)


def test_sweep_terminates_the_worker_of_a_gone_owner():
    worker, owner = _sleeper(), _sleeper()
    try:
        _record(worker, owner)
        owner.kill()
        owner.wait(timeout=5)
        sweep_stale_worker()
        assert worker.wait(timeout=5) == 1
        assert not (paths.engine_dir() / "worker.pid").exists()
    finally:
        worker.kill()
        worker.wait(timeout=5)


def test_pid_file_names_this_process_as_the_owner(tmp_path):
    engine = SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER, model_dir=tmp_path / "m",
                              device="cpu", dtype="float32", log_file=tmp_path / "engine.log")
    try:
        info = engine.start()
        data = json.loads((paths.engine_dir() / "worker.pid").read_text(encoding="utf-8"))
        assert data["pid"] == info.pid
        assert data["owner"] == os.getpid()
        assert data["owner_created"] == lifetime._process_create_time(os.getpid())
    finally:
        engine.stop()
