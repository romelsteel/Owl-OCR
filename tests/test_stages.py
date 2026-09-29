import json
import sys
import types
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


def _links():
    import os
    import stat as st
    if not kit.python_dir().exists():
        return []
    return [e.name for e in os.scandir(kit.python_dir())
            if os.lstat(e.path).st_file_attributes & st.FILE_ATTRIBUTE_REPARSE_POINT]


def test_python_tolerates_the_redirection_guard_failure(tools):
    logged = []
    c = StageContext(CPU, tools.deps_for_test(), None, lambda d, t, m: None, logged.append)
    stages.do_tools(c)
    tools.python_install_fault = "448"
    stages.do_python(c)                                   # does not raise
    assert _links() == []
    assert stages.check_python(c)
    assert any("RedirectionGuard" in line for line in logged)
    run(tools, ["venv", "torch", "deps"])
    assert tools.uv_calls()[1][:3] == ["venv", "--python", str(kit.managed_python())]


def test_python_still_fails_without_a_usable_python(tools):
    run(tools, ["tools"])
    tools.python_install_fault = "448-empty"
    with pytest.raises(BootstrapError, match="command_failed: uv.exe python install exited with 2"):
        stages.do_python(ctx(tools))


def test_python_still_fails_when_the_python_does_not_answer(tools):
    run(tools, ["tools"])
    tools.python_install_fault = "448"
    real_run = tools.run_cmd

    def run_cmd(args, env, on_line, cancel):
        if args[1:] == ["--version"]:
            tools.calls.append(list(args))
            on_line("error: not a Python")
            return 1
        return real_run(args, env, on_line, cancel)

    deps = tools.deps_for_test()
    deps.run_cmd = run_cmd
    with pytest.raises(BootstrapError, match=r"command_failed: uv.exe python install exited with 2: .*os error 448"):
        stages.do_python(ctx(tools, deps=deps))
    assert kit.managed_python() is not None                # the python.exe exists, it just failed the check


def test_python_still_fails_on_other_errors(tools):
    run(tools, ["tools"])
    tools.fail_when = lambda args: args[1:3] == ["python", "install"]
    with pytest.raises(BootstrapError, match="command_failed: .*simulated failure"):
        stages.do_python(ctx(tools))


def test_python_success_removes_the_minor_version_link(tools):
    run(tools, ["tools"])
    tools.python_install_fault = "link"
    stages.do_python(ctx(tools))
    assert _links() == []


def test_a_link_left_by_an_earlier_attempt_heals_on_retry(tools):
    from tests.install_fakes import make_junction

    run(tools, ["tools", "python"])
    folder = kit.managed_python().parent
    make_junction(kit.python_dir() / "cpython-3.11-windows-x86_64-none", folder)
    c = ctx(tools)
    assert stages.check_python(c)                         # the full Python is there: stage skipped
    assert _links() == []                                 # ... and the check removed the link
    make_junction(kit.python_dir() / "cpython-3.11-windows-x86_64-none", folder)
    run(tools, ["venv"])
    assert _links() == []
    for name in ("torch", "deps"):
        make_junction(kit.python_dir() / "cpython-3.11-windows-x86_64-none", folder)
        stages.ACTIONS[name](c)
        assert _links() == [], name


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


def test_torch_cancel_surfaces_as_cancelled(tools):
    import threading
    run(tools, ["tools", "python", "venv"])
    tools.block_torch = True
    cancel = threading.Event()
    cancel.set()
    c = StageContext(GPU, tools.deps_for_test(), cancel, lambda d, t, m: None, lambda line: None)
    with pytest.raises(BootstrapError, match="^cancelled$"):
        stages.do_torch(c)


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


def test_model_store_cancel_surfaces_as_cancelled(tools):
    from owlocr.engine import store

    deps = tools.deps_for_test()

    def cancelled(on_progress, cancel):
        raise store.StoreError("cancelled")

    deps.store_download = cancelled
    with pytest.raises(BootstrapError, match="^cancelled$"):      # not reported as model_download_failed
        stages.do_model(ctx(tools, deps=deps))


def test_model_check_accepts_the_manifest_left_by_the_cpu_patch(tools):
    """device_patch.py adds `modeling_unlimitedocr.py.orig` and a patched entry (git_sha1 None,
    key patched_by); the real store must still call the folder ready, without any download."""
    from owlocr.engine import registry, store

    folder = paths.model_dir()
    folder.mkdir(parents=True)
    (folder / "modeling_unlimitedocr.py").write_bytes(b"patched!")
    (folder / "modeling_unlimitedocr.py.orig").write_bytes(b"pristine")
    files = {"modeling_unlimitedocr.py.orig": {"size": 8, "sha256": None, "git_sha1": "abc"},
             "modeling_unlimitedocr.py": {"size": 8, "sha256": "d" * 64, "git_sha1": None,
                                          "patched_by": "owl-ocr device patch v1 applied"}}
    (folder / "manifest.json").write_text(
        json.dumps({"repo": "x", "commit": registry.UNLIMITED_OCR.revision, "files": files}), encoding="utf-8")
    assert store.is_ready() is True
    deps = tools.deps_for_test()
    deps.store_is_ready = store.is_ready
    deps.store_download = lambda on_progress, cancel: pytest.fail("must not download")
    c = ctx(tools, deps=deps)
    assert stages.check_model(c)


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
    stages.do_patch(ctx(tools, GPU))                              # even when forced
    assert not any(c[1].endswith("device_patch.py") for c in tools.calls)


def test_refused_patch(tools):
    run(tools, ["tools", "python", "venv", "model", "worker"])
    tools.patch_code = 2
    with pytest.raises(BootstrapError, match="patch_refused: REFUSED"):
        stages.do_patch(ctx(tools))


def test_patch_cancel_surfaces_as_cancelled(tools):
    from owlocr.engine import uvtool

    run(tools, ["tools", "python", "venv", "model", "worker"])
    tools.patch_code = uvtool.CANCELLED
    with pytest.raises(BootstrapError, match="^cancelled$"):
        stages.do_patch(ctx(tools))


# ---- selftest, mark ------------------------------------------------------------------

ALL_BUT_LAST = ["tools", "python", "venv", "torch", "deps", "model", "worker", "patch"]


def _engine_returning(result=None, error=None):
    engine = SimpleNamespace(stopped=False)
    engine.start = lambda: None
    engine.load = lambda: 0.1

    def ocr_page(*a, **k):
        if error is not None:
            raise error
        return result

    engine.ocr_page = ocr_page
    engine.stop = lambda timeout_s=5.0: setattr(engine, "stopped", True)
    return engine


def _page_result(**over):
    from owlocr.engine.protocol import PageResult

    values = dict(text=LETTER, seconds=1.0, prefix_tokens=1, output_tokens=1, hit_token_cap=False,
                  cancelled=False, timed_out=False, peak_vram_mib=0)
    values.update(over)
    return PageResult(**values)


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
    engine = _engine_returning(error=EngineError("died"))
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


def test_selftest_timeout_is_a_failure(tools):
    run(tools, ALL_BUT_LAST)
    deps = tools.deps_for_test()
    engine = _engine_returning(result=_page_result(text="", timed_out=True))
    deps.engine_factory = lambda tier: engine
    with pytest.raises(BootstrapError, match="selftest_failed: timed_out"):
        stages.do_selftest(ctx(tools, deps=deps))
    assert engine.stopped


def test_selftest_cancel_surfaces_as_cancelled(tools):
    from owlocr.engine.protocol import EngineError

    run(tools, ALL_BUT_LAST)
    deps = tools.deps_for_test()
    engine = _engine_returning(result=_page_result(text="", cancelled=True))
    deps.engine_factory = lambda tier: engine
    with pytest.raises(BootstrapError, match="^cancelled$"):
        stages.do_selftest(ctx(tools, deps=deps))
    assert engine.stopped
    # an engine error raised while the cancel flag is set is a cancellation, not a failure
    import threading
    cancel = threading.Event()
    cancel.set()
    engine = _engine_returning(error=EngineError("died"))
    deps.engine_factory = lambda tier: engine
    c = StageContext(CPU, deps, cancel, lambda d, t, m: None, lambda line: None)
    with pytest.raises(BootstrapError, match="^cancelled$"):
        stages.do_selftest(c)
    assert engine.stopped


def test_selftest_runs_again_for_another_tier(tools):
    run(tools, ALL_BUT_LAST + ["selftest"], CPU)
    assert not stages.check_selftest(ctx(tools, GPU))


def test_mark_writes_install_json(tools):
    run(tools, ALL_BUT_LAST + ["selftest", "mark"], CPU)
    record = json.loads(kit.install_file().read_text(encoding="utf-8"))
    assert record["tier"] == "cpu" and record["patched"] is True and record["selftest_seconds"] == 12.3
    assert record["fingerprint"] == stages.fingerprint(ctx(tools, CPU))
    assert "python" not in record                    # plan A's default_engine() would read it as a path


def test_mark_holds_the_settings_lock(tools, monkeypatch):
    from owlocr import settings

    events = []

    class Lock:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *exc):
            events.append("exit")

    monkeypatch.setitem(sys.modules, "owlocr.web.server", types.SimpleNamespace(SETTINGS_LOCK=Lock()))
    real_update = settings.update
    monkeypatch.setattr(settings, "update", lambda changes: (events.append("update"), real_update(changes))[1])
    run(tools, ALL_BUT_LAST + ["selftest"], CPU)
    assert CPU.default_mode == "fast"
    stages.do_mark(ctx(tools, CPU))
    assert events == ["enter", "update", "exit"]
    assert settings.get("mode_default") == "fast"


def test_selftest_word_matching():
    assert stages.selftest_words_found(LETTER) == list(kit.SELFTEST_WORDS)
    assert stages.selftest_words_found("VÁŽENÁ paní DOKTORKO") == ["Vážená", "doktorko"]
