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
