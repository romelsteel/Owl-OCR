from pathlib import Path

import pytest

from owlocr import paths
from owlocr.jobs.formats import available_formats
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import OOM_WARNING, Runner, resume_file
from owlocr.pipeline.document import load_sidecar
from tests.owl_helpers import engine_error, fake_engine_factory, make_tiff, settings_for, wait_until


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    runners = []

    def build(behaviour="", queue=None, **settings_overrides):
        monkeypatch.setenv("FAKE_WORKER", behaviour)
        q = queue or JobQueue(tmp_path / "queue.json")
        values = settings_for(tmp_path, **settings_overrides)
        r = Runner(q, fake_engine_factory(tmp_path, behaviour), lambda: values)
        runners.append(r)
        return q, r

    yield build
    for r in runners:
        r.shutdown()


def _state(q, job_id):
    return q.get(job_id).state


def test_processes_job_and_exports(tmp_path, make_runner):
    q, r = make_runner()
    [job] = q.add([make_tiff(tmp_path / "in" / "book.tif", pages=2)])
    assert r.status()["engine"] == "stopped"  # lazy: nothing started yet
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "done")
    done = q.get(job.id)
    assert done.pages_done == 2 and done.error is None and done.finished
    assert set(done.outputs) == {"md", "txt", "owl"}
    assert "fake text for" in Path(done.outputs["txt"]).read_text(encoding="utf-8")
    doc = load_sidecar(Path(done.outputs["owl"]))
    assert [p.index for p in doc.pages] == [0, 1]
    assert not resume_file(job.id).exists()
    assert wait_until(lambda: not r.status()["running"])
    assert r.status()["engine"] == "ready"


def test_unsupported_formats_are_skipped(tmp_path, make_runner):
    q, r = make_runner(formats=["md", "docx", "pdf"])
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "done")
    later = {"docx", "pdf"} & set(available_formats())  # empty until plan C lands
    assert set(q.get(job.id).outputs) == {"md", "owl"} | later


def test_pause_after_current_page_then_resume(tmp_path, make_runner):
    q, r = make_runner("slow")
    [job] = q.add([make_tiff(tmp_path / "a.tif", pages=3)])
    r.start()
    assert wait_until(lambda: r.status()["engine"] == "busy")
    r.pause()
    assert wait_until(lambda: _state(q, job.id) == "paused", timeout=6)
    assert q.get(job.id).pages_done == 1
    status = r.status()
    assert status["paused"] and not status["running"]
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "done", timeout=15)
    assert q.get(job.id).pages_done == 3


def test_cancel_running_job_stops_at_once(tmp_path, make_runner):
    q, r = make_runner("slow")
    a, b = q.add([make_tiff(tmp_path / "a.tif", pages=3), make_tiff(tmp_path / "b.tif")])
    r.start()
    assert wait_until(lambda: r.status()["current_page_tokens"] > 0)
    r.cancel(a.id)
    assert wait_until(lambda: _state(q, a.id) == "cancelled", timeout=1.5)
    assert q.get(a.id).pages_done == 0
    assert wait_until(lambda: _state(q, b.id) == "done", timeout=10)


def test_cancel_pending_job(tmp_path, make_runner):
    q, r = make_runner()
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.cancel(job.id)
    assert _state(q, job.id) == "cancelled"


def test_resume_after_restart_reads_only_missing_pages(tmp_path, make_runner):
    q1, r1 = make_runner("slow")
    [job] = q1.add([make_tiff(tmp_path / "a.tif", pages=3)])
    r1.start()
    assert wait_until(lambda: q1.get(job.id).pages_done >= 1, timeout=6)
    r1.shutdown()  # the app closes in the middle of page 2
    assert _state(q1, job.id) == "pending"
    kept = len(load_sidecar(resume_file(job.id)).pages)
    assert kept >= 1

    q2 = JobQueue(tmp_path / "queue.json")  # the app starts again
    calls = []
    q2, r2 = make_runner("", queue=q2)
    real_factory = r2._engine_factory

    def counting_factory():
        engine = real_factory()
        original = engine.ocr_page

        def ocr_page(*args, **kwargs):
            calls.append(args[0])
            return original(*args, **kwargs)
        engine.ocr_page = ocr_page
        return engine
    r2._engine_factory = counting_factory
    r2.start()
    assert wait_until(lambda: _state(q2, job.id) == "done", timeout=10)
    assert len(calls) == 3 - kept
    assert q2.get(job.id).pages_done == 3


def test_out_of_memory_in_quality_retries_page_in_fast(tmp_path, make_runner):
    q, r = make_runner("oom_on_quality")
    [job] = q.add([make_tiff(tmp_path / "a.tif", pages=2)])
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "done")
    done = q.get(job.id)
    assert done.warnings == 2
    doc = load_sidecar(Path(done.outputs["owl"]))
    assert all(p.warnings[0] == OOM_WARNING and p.mode == "fast" for p in doc.pages)


def test_per_job_mode_override(tmp_path, make_runner):
    q, r = make_runner("oom_on_quality")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    q.update(job.id, mode="fast")
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "done")
    assert q.get(job.id).warnings == 0


def test_worker_death_restarts_once_then_fails_job_not_queue(tmp_path, make_runner):
    q, r = make_runner("crash_on_ocr")
    built = []
    real_factory = r._engine_factory
    r._engine_factory = lambda: built.append(1) or real_factory()
    a, b = q.add([make_tiff(tmp_path / "a.tif"), make_tiff(tmp_path / "b.tif")])
    r.start()
    assert wait_until(lambda: _state(q, b.id) == "failed", timeout=20)
    assert _state(q, a.id) == "failed"
    assert q.get(a.id).error.startswith("died") and not q.get(a.id).error.startswith("died: died")
    assert len(built) == 4  # two engines per job: the first try and one restart


def test_missing_source_fails_job(tmp_path, make_runner):
    q, r = make_runner()
    src = make_tiff(tmp_path / "a.tif")
    [job] = q.add([src])
    src.unlink()
    r.start()
    assert wait_until(lambda: _state(q, job.id) == "failed")
    assert "not found" in q.get(job.id).error


def test_status_keys(make_runner):
    _, r = make_runner()
    assert {"engine", "running", "paused", "current_job", "current_page_tokens",
            "vram_used_mib"} <= set(r.status())


def test_cancel_cannot_hit_a_job_the_runner_just_picked_up(tmp_path, make_runner):
    """cancel() checks and marks the job under one lock: if the runner could pick the job up
    between the check and the update, the job would be marked cancelled while it runs and then
    finish as done."""
    import threading

    q, r = make_runner("slow")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    test_thread = threading.current_thread()

    class HookLock:  # releases like the real RLock, then lets the runner pick up the job once
        def __init__(self, inner):
            self.inner, self.armed, self.depth = inner, False, 0

        def acquire(self, *args, **kwargs):
            return self.inner.acquire(*args, **kwargs)

        def release(self):
            self.inner.release()

        def __enter__(self):
            self.inner.acquire()
            if threading.current_thread() is test_thread:
                self.depth += 1
            return self

        def __exit__(self, *exc):
            self.inner.release()
            if threading.current_thread() is not test_thread:
                return False
            self.depth -= 1
            if self.armed and self.depth == 0:
                self.armed = False
                r.start()
                wait_until(lambda: _state(q, job.id) != "pending", timeout=5)
            return False

    r._lock = HookLock(r._lock)
    r._lock.armed = True
    r.cancel(job.id)
    assert wait_until(lambda: r.status()["current_job"] is None and not r.status()["running"],
                      timeout=10)
    assert _state(q, job.id) == "cancelled"
    assert q.get(job.id).pages_done == 0


class _OomInQualityEngine:
    """Stub engine: Quality runs out of memory, Fast reads an empty page (which process_page
    retries internally in Quality)."""
    device = "cpu"

    def __init__(self):
        self.loaded = False
        self.calls = []

    def is_running(self):
        return True

    def load(self):
        self.loaded = True

    def stop(self, timeout_s=5.0):
        self.loaded = False

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        from owlocr.engine.protocol import PageResult

        self.calls.append(mode)
        if mode == "quality":
            raise engine_error("out_of_memory")
        return PageResult(text="", seconds=0.01, prefix_tokens=0, output_tokens=0,
                          hit_token_cap=False, cancelled=False, timed_out=False, peak_vram_mib=0)


@pytest.mark.parametrize("mode", ["fast", "quality"])
def test_out_of_memory_in_internal_retry_falls_back_to_fast(tmp_path, mode):
    engine = _OomInQualityEngine()
    q = JobQueue(tmp_path / "queue.json")
    values = settings_for(tmp_path, mode_default=mode)
    r = Runner(q, lambda: engine, lambda: values)
    try:
        [job] = q.add([make_tiff(tmp_path / "a.tif")])
        r.start()
        assert wait_until(lambda: _state(q, job.id) in ("done", "failed"))
        done = q.get(job.id)
        assert done.state == "done", done.error
        [page] = load_sidecar(Path(done.outputs["owl"])).pages
        assert page.warnings[0] == OOM_WARNING and page.mode == "fast"
        assert engine.calls.count("quality") == 1    # after the out-of-memory only Fast is read
    finally:
        r.shutdown()


def test_remove_refuses_the_running_job_and_removes_others(tmp_path, make_runner):
    q, r = make_runner("slow")
    running, waiting = q.add([make_tiff(tmp_path / "a.tif"), make_tiff(tmp_path / "b.tif")])
    r.start()
    assert wait_until(lambda: r.status()["current_job"] == running.id)
    assert r.remove(running.id) is False
    assert r.remove(waiting.id) is True
    assert [j.id for j in q.all()] == [running.id]
    with pytest.raises(KeyError):
        r.remove(waiting.id)
    r.cancel(running.id)
    assert wait_until(lambda: r.status()["current_job"] is None, timeout=10)


def test_unless_current_refuses_the_running_job_and_runs_for_others(tmp_path, make_runner):
    q, r = make_runner("slow")
    running, waiting = q.add([make_tiff(tmp_path / "a.tif"), make_tiff(tmp_path / "b.tif")])
    r.start()
    assert wait_until(lambda: r.status()["current_job"] == running.id)
    calls = []
    assert r.unless_current(running.id, lambda: calls.append("running")) is False
    assert r.unless_current(waiting.id, lambda: calls.append("waiting")) is True
    assert calls == ["waiting"]
    r.cancel(running.id)
    assert wait_until(lambda: r.status()["current_job"] is None, timeout=10)


def test_queue_write_error_stops_queue_with_notice_and_start_recovers(tmp_path, make_runner):
    q, r = make_runner()
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    real_update = q.update
    failures = []

    def failing_update(job_id, **fields):
        if fields.get("state") == "running" and not failures:   # outside _run_job's try
            failures.append(1)
            raise PermissionError("queue.json is locked")
        return real_update(job_id, **fields)
    q.update = failing_update
    r.start()
    assert wait_until(lambda: r.status()["error"] is not None)
    status = r.status()
    assert status["error"] == {"code": "internal"} and not status["running"]
    assert status["current_job"] is None
    assert _state(q, job.id) == "pending"
    assert "queue.json is locked" in (paths.logs_dir() / "runner.log").read_text(encoding="utf-8")
    r.start()                                   # a dead runner thread is started again
    assert wait_until(lambda: _state(q, job.id) == "done")
    assert r.status()["error"] is None
