"""SubprocessEngine against tests/fake_worker.py."""
import json
import sys
import threading
import time

import pytest

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine
from owlocr.engine.protocol import EngineError, EngineInfo, PageResult
from tests.conftest import FAKE_WORKER


def make_engine(tmp_path, flags: str = "") -> SubprocessEngine:
    return SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER, model_dir=tmp_path / "model",
                            device="cpu", dtype="float32", log_file=tmp_path / "logs" / "engine.log",
                            env={"FAKE_WORKER": flags})


@pytest.fixture
def page(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"fake image")
    return image


def test_start_load_ocr_stop(tmp_path, page):
    engine = make_engine(tmp_path)
    try:
        info = engine.start()
        assert isinstance(info, EngineInfo)
        assert info.torch == "fake" and info.cuda_available is False and info.gpu_name is None
        assert engine.is_running() and not engine.loaded
        assert isinstance(engine.load(), float)
        assert engine.loaded
        result = engine.ocr_page(page, "quality")
        assert isinstance(result, PageResult)
        assert result.text.endswith("fake text for page.png")
        assert result.prefix_tokens == 907
        assert not (result.cancelled or result.timed_out or result.hit_token_cap)
        assert engine.ocr_page(page, "fast").prefix_tokens == 277
    finally:
        engine.stop()
    assert not engine.is_running() and not engine.loaded
    assert not lifetime.process_alive(info.pid)


def test_constructing_does_not_start_a_process(tmp_path):
    engine = make_engine(tmp_path)
    assert not engine.is_running() and not engine.loaded
    assert engine.device == "cpu" and engine.dtype == "float32"
    assert engine.engine_id == "unlimited_ocr"


def test_app_environment_reaches_the_worker(tmp_path, page, monkeypatch):
    monkeypatch.setenv("FAKE_WORKER", "oom_on_quality")
    engine = SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER, model_dir=tmp_path / "m",
                              device="cpu", dtype="float32", log_file=tmp_path / "engine.log")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "out_of_memory"
    finally:
        engine.stop()


def test_load_starts_the_worker_when_needed(tmp_path, page):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        assert engine.is_running() and engine.loaded
    finally:
        engine.stop()


def test_worker_env_and_log(tmp_path):
    engine = make_engine(tmp_path)
    env = engine._worker_env()
    assert env["HF_HUB_OFFLINE"] == "1" and env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["PYTORCH_CUDA_ALLOC_CONF"] == "expandable_segments:True"
    assert env["PYTHONIOENCODING"] == "utf-8" and env["PYTHONUNBUFFERED"] == "1"
    assert env["HF_HOME"] == str(paths.hf_home())
    assert env["FAKE_WORKER"] == ""
    try:
        engine.start()
    finally:
        engine.stop()
    assert "engine start" in (tmp_path / "logs" / "engine.log").read_text(encoding="utf-8")


def test_ocr_before_load_is_not_loaded(tmp_path, page):
    engine = make_engine(tmp_path)
    with pytest.raises(EngineError) as e:
        engine.ocr_page(page, "quality")
    assert e.value.kind == "not_loaded"
    try:
        engine.start()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "not_loaded"
    finally:
        engine.stop()


def test_bad_mode(tmp_path, page):
    with pytest.raises(ValueError):
        make_engine(tmp_path).ocr_page(page, "turbo")


def test_bad_image(tmp_path):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(tmp_path / "missing.png", "quality")
        assert e.value.kind == "bad_image"
        assert engine.is_running()
    finally:
        engine.stop()


def test_progress_events(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    seen = []
    try:
        engine.load()
        result = engine.ocr_page(page, "quality", on_progress=seen.append)
    finally:
        engine.stop()
    assert seen == [50, 100, 150, 200]
    assert not result.cancelled


def test_cancel_returns_partial_result(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    try:
        engine.load()
        t0 = time.monotonic()
        result = engine.ocr_page(page, "quality", cancel=cancel)
        assert time.monotonic() - t0 < 1.8
    finally:
        engine.stop()
    assert result.cancelled and not result.timed_out


def test_time_limit(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    try:
        engine.load()
        result = engine.ocr_page(page, "quality", time_limit_s=0.5)
    finally:
        engine.stop()
    assert result.timed_out and not result.cancelled


def test_worker_that_exits_after_a_stuck_page(tmp_path, page):
    """A page that timed out before its first token on the GPU: the worker answers with
    engine_exiting and exits. The page still has its timed-out result, the engine is cleanly
    not running (no race with the exiting process, no "died"), and loading again works."""
    engine = make_engine(tmp_path, "stuck_first_pass")
    try:
        engine.load()
        result = engine.ocr_page(page, "quality", time_limit_s=0.5)
        assert result.timed_out and result.text == "" and result.output_tokens == 0
        assert not engine.loaded and not engine.is_running()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "not_loaded"
        engine.env["FAKE_WORKER"] = ""
        engine.load()
        assert engine.ocr_page(page, "quality").text
    finally:
        engine.stop()


def test_out_of_memory_is_an_engine_error(tmp_path, page):
    engine = make_engine(tmp_path, "oom_on_quality")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "out_of_memory"
        assert engine.ocr_page(page, "fast").text        # the worker is still fine
    finally:
        engine.stop()


def test_crash_is_died_and_restart_works(tmp_path, page):
    engine = make_engine(tmp_path, "crash_on_ocr")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "died"
        assert not engine.is_running() and not engine.loaded
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "died"
        engine.env["FAKE_WORKER"] = ""
        engine.load()
        assert engine.ocr_page(page, "quality").text
    finally:
        engine.stop()


def test_stop_terminates_a_worker_that_ignores_shutdown(tmp_path):
    engine = make_engine(tmp_path, "ignore_shutdown")
    info = engine.start()
    t0 = time.monotonic()
    engine.stop(timeout_s=1.0)
    assert time.monotonic() - t0 < 4
    assert not engine.is_running()
    deadline = time.monotonic() + 5
    while lifetime.process_alive(info.pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not lifetime.process_alive(info.pid)


def test_stop_from_another_thread_while_a_page_is_read(tmp_path, page):
    """Plan B's manual "Stop engine": stop() while ocr_page() runs in the runner thread."""
    engine = make_engine(tmp_path, "slow")
    engine.load()
    outcome = {}

    def read():
        try:
            outcome["result"] = engine.ocr_page(page, "quality")
        except EngineError as e:
            outcome["error"] = e

    reader = threading.Thread(target=read)
    reader.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    engine.stop()
    reader.join(timeout=10)
    assert time.monotonic() - t0 < 3
    assert not reader.is_alive() and not engine.is_running()
    # The worker cancels the page on `shutdown` and answers before it exits, so the blocked call
    # returns the partial result. (A worker that does not exit within timeout_s is killed, and
    # then the blocked call raises EngineError("died") instead.)
    assert "error" not in outcome
    assert outcome["result"].cancelled is True


def test_unload(tmp_path):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        engine.unload()
        assert engine.is_running() and not engine.loaded
    finally:
        engine.stop()


def test_stop_without_start_is_harmless(tmp_path):
    engine = make_engine(tmp_path)
    engine.stop()
    assert not engine.is_running() and not engine.loaded
    assert not (tmp_path / "logs" / "engine.log").exists()      # nothing was started
    assert not (paths.engine_dir() / "worker.pid").exists()


def test_concurrent_cleanup_closes_the_job_once(tmp_path):
    """stop() and a blocked call that sees the worker die can both run _cleanup() at once;
    the Job Object handle must still be closed exactly once."""
    closes = []
    both_in = threading.Barrier(2)

    class SlowJob:
        def close(self):
            closes.append(threading.current_thread().name)
            time.sleep(0.2)                  # keep the first closer inside close()

    engine = make_engine(tmp_path)
    engine._job = SlowJob()

    def cleanup():
        both_in.wait()
        engine._cleanup()

    threads = [threading.Thread(target=cleanup) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert len(closes) == 1
    assert engine._job is None


def test_missing_python_is_not_installed(tmp_path):
    engine = make_engine(tmp_path)
    engine.python = tmp_path / "no" / "python.exe"
    with pytest.raises(EngineError) as e:
        engine.start()
    assert e.value.kind == "not_installed"


def test_pid_file_written_and_removed(tmp_path):
    engine = make_engine(tmp_path)
    info = engine.start()
    pid_file = paths.engine_dir() / "worker.pid"
    try:
        data = json.loads(pid_file.read_text(encoding="utf-8"))
        assert data["pid"] == info.pid and isinstance(data["created"], int)
    finally:
        engine.stop()
    assert not pid_file.exists()


def test_failed_job_assignment_kills_the_worker(tmp_path, monkeypatch):
    started = []

    def failing_assign(self, pid):
        started.append(pid)
        raise OSError("AssignProcessToJobObject failed (test)")

    monkeypatch.setattr(lifetime.JobObject, "assign", failing_assign)
    engine = make_engine(tmp_path)
    with pytest.raises(EngineError) as e:
        engine.start()
    assert e.value.kind == "internal"
    assert len(started) == 1
    assert not engine.is_running() and engine._job is None
    assert not lifetime.process_alive(started[0])


def test_late_stop_cleanup_leaves_a_restarted_worker_alone(tmp_path, page):
    """stop() returns from proc.wait() late; meanwhile the runner got its cancelled result and
    loaded again. stop()'s cleanup must not close the new worker's job, pid file or log."""
    engine = make_engine(tmp_path, "slow")
    engine.load()
    old = engine._proc
    real_wait = old.wait

    def slow_wait(timeout=None):
        code = real_wait(timeout)
        time.sleep(3.0)                      # stop() is still "inside" wait while the runner reloads
        return code

    old.wait = slow_wait
    outcome = {}

    def runner():
        outcome["result"] = engine.ocr_page(page, "quality")
        while old.poll() is None:            # the old worker exits right after answering shutdown
            time.sleep(0.02)
        engine.load()
        outcome["pid"] = engine._info.pid

    reader = threading.Thread(target=runner)
    stopper = threading.Thread(target=engine.stop)
    try:
        reader.start()
        time.sleep(0.3)
        stopper.start()
        reader.join(timeout=10)
        stopper.join(timeout=10)
        assert outcome["result"].cancelled
        assert engine.is_running() and engine.loaded
        assert lifetime.process_alive(outcome["pid"])
        assert json.loads((paths.engine_dir() / "worker.pid").read_text(encoding="utf-8"))["pid"] == outcome["pid"]
    finally:
        engine.stop()
    assert not lifetime.process_alive(outcome.get("pid", 0))


def test_stop_kills_a_worker_that_ignores_shutdown_mid_page(tmp_path, page):
    """The kill half of stop(): the worker ignores `shutdown` while reading a page, stop() kills
    it after timeout_s, and the blocked ocr_page raises EngineError("died")."""
    engine = make_engine(tmp_path, "slow,ignore_shutdown")
    info = engine.start()
    engine.load()
    outcome = {}

    def read():
        try:
            outcome["result"] = engine.ocr_page(page, "quality")
        except EngineError as e:
            outcome["error"] = e

    reader = threading.Thread(target=read)
    reader.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    engine.stop(timeout_s=0.3)
    reader.join(timeout=10)
    assert time.monotonic() - t0 < 1.5        # the page alone would take 2 s
    assert not reader.is_alive() and not engine.is_running()
    assert "result" not in outcome
    assert outcome["error"].kind == "died"
    assert not lifetime.process_alive(info.pid)
