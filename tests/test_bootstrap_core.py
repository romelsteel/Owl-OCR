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
    assert started.wait(10)
    with pytest.raises(BootstrapError, match="already_running"):
        run()
    with pytest.raises(BootstrapError, match="already_running"):
        bootstrap.remove_engine()
    release.set()
    worker.join(10)
    assert not worker.is_alive()


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


def _development_record():
    kit.install_file().parent.mkdir(parents=True, exist_ok=True)
    kit.install_file().write_text(json.dumps({"tier": "development"}), encoding="utf-8")


def test_remove_engine_refuses_a_development_record():
    _development_record()
    engine_file = paths.engine_dir() / "keep.txt"
    model_file = paths.model_dir() / "keep.txt"
    model_file.parent.mkdir(parents=True, exist_ok=True)
    engine_file.write_text("x", encoding="utf-8")
    model_file.write_text("x", encoding="utf-8")
    with pytest.raises(BootstrapError, match="^development:"):
        bootstrap.remove_engine()
    assert engine_file.is_file() and model_file.is_file()


def test_reset_install_refuses_a_development_record():
    _development_record()
    with pytest.raises(BootstrapError, match="^development:"):
        bootstrap.reset_install()
    assert bootstrap.install_path().is_file()


@pytest.mark.parametrize("operation", ["remove_engine", "reset_install"])
def test_no_installation_while_the_engine_is_removed_or_reset(script, monkeypatch, tmp_path, operation):
    script()
    started, release = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        started.set()
        release.wait(10)
        return {}

    if operation == "remove_engine":
        monkeypatch.setattr(kit, "rmtree", slow)
    else:
        monkeypatch.setattr(bootstrap.store, "manifest_path", lambda *a: tmp_path)   # exists -> verify runs
        monkeypatch.setattr(bootstrap.store, "verify", slow)
        monkeypatch.setattr(kit, "rmtree", lambda path: None)
    errors = []

    def work():
        try:
            getattr(bootstrap, operation)()
        except Exception as exc:          # pragma: no cover - reported below
            errors.append(exc)

    worker = threading.Thread(target=work)
    worker.start()
    try:
        assert started.wait(10)
        with pytest.raises(BootstrapError, match="^already_running"):
            bootstrap.run(CPU, lambda event: None)
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and errors == []
    run()                                 # the lock is free again afterwards
