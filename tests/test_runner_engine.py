import time

import pytest

from owlocr.engine.lifetime import process_alive
from owlocr.jobs import runner as runner_mod
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from tests.owl_helpers import engine_error, fake_engine_factory, make_tiff, settings_for, wait_until


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    runners = []

    def build(behaviour="", factory=None, **settings_overrides):
        monkeypatch.setenv("FAKE_WORKER", behaviour)
        q = JobQueue(tmp_path / "queue.json")
        values = settings_for(tmp_path, **settings_overrides)
        r = Runner(q, factory or fake_engine_factory(tmp_path, behaviour), lambda: values)
        runners.append(r)
        return q, r

    yield build
    for r in runners:
        r.shutdown()


def _run_one_job(tmp_path, q, r, pages=1):
    [job] = q.add([make_tiff(tmp_path / f"{time.monotonic_ns()}.tif", pages=pages)])
    r.start()
    assert wait_until(lambda: q.get(job.id).state == "done")
    # the queue counts as running until the loop finds no next job; stop_engine() would pause it
    assert wait_until(lambda: not r.status()["running"])
    return job


def test_idle_stop_after_timer(tmp_path, make_runner):
    q, r = make_runner(idle_stop_minutes=1)
    r._idle_unit_s = 0.2  # one "minute" lasts 0.2 s in this test
    _run_one_job(tmp_path, q, r)
    pid = r.status()["engine_pid"]
    assert pid and process_alive(pid)
    assert wait_until(lambda: r.status()["engine"] == "stopped", timeout=5)
    assert wait_until(lambda: not process_alive(pid), timeout=5)
    assert r.status()["vram_used_mib"] is None


def test_idle_zero_keeps_engine(tmp_path, make_runner):
    q, r = make_runner(idle_stop_minutes=0)
    r._idle_unit_s = 0.01
    _run_one_job(tmp_path, q, r)
    time.sleep(1.2)
    assert r.status()["engine"] == "ready"


def test_stop_engine_while_idle(tmp_path, make_runner):
    q, r = make_runner()
    _run_one_job(tmp_path, q, r)
    pid = r.status()["engine_pid"]
    assert process_alive(pid)
    r.stop_engine()
    status = r.status()
    assert status["engine"] == "stopped" and status["engine_pid"] is None
    assert not status["paused"]
    assert wait_until(lambda: not process_alive(pid), timeout=5)


def test_stop_engine_during_page_pauses_and_resumes(tmp_path, make_runner):
    q, r = make_runner("slow")
    [job] = q.add([make_tiff(tmp_path / "a.tif", pages=3)])
    r.start()
    assert wait_until(lambda: r.status()["engine"] == "busy")
    pid = r.status()["engine_pid"]
    done_before = q.get(job.id).pages_done
    started = time.monotonic()
    r.stop_engine()
    assert wait_until(lambda: not process_alive(pid), timeout=5)
    assert time.monotonic() - started < 5
    status = r.status()
    assert status["engine"] == "stopped" and status["paused"] and not status["running"]
    assert q.get(job.id).state == "paused"
    assert q.get(job.id).pages_done == done_before
    r.start()
    assert wait_until(lambda: q.get(job.id).state == "done", timeout=20)
    assert q.get(job.id).pages_done == 3


def test_shutdown_leaves_no_worker(tmp_path, make_runner):
    q, r = make_runner("slow")
    [job] = q.add([make_tiff(tmp_path / "a.tif", pages=3)])
    r.start()
    assert wait_until(lambda: r.status()["engine"] == "busy")
    pid = r.status()["engine_pid"]
    r.shutdown()
    assert wait_until(lambda: not process_alive(pid), timeout=5)
    assert q.get(job.id).state == "pending"
    r.start()  # ignored after shutdown
    assert not r.status()["running"]


def test_free_vram_check_blocks_job(tmp_path, make_runner, monkeypatch):
    class GpuEngine:
        device = "cuda"
        loaded = False
        started = False

        def is_running(self):
            return False

        def start(self):
            GpuEngine.started = True
            raise AssertionError("must not start")

        def stop(self, timeout_s=5.0):
            pass

    monkeypatch.setattr(runner_mod.hardware, "free_vram_mib", lambda: 4000)
    q, r = make_runner(factory=GpuEngine)
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert wait_until(lambda: r.status()["error"] is not None)
    error = r.status()["error"]
    assert error == {"code": "vram_short", "mode": "quality", "need_mib": 9500,
                     "free_mib": 4000, "missing_mib": 5500}
    assert q.get(job.id).state == "pending"
    assert not r.status()["running"] and not GpuEngine.started


def test_not_installed_keeps_job_pending(tmp_path, make_runner):
    def factory():
        raise engine_error("not_installed")
    q, r = make_runner(factory=factory)
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert wait_until(lambda: r.status()["error"] is not None)
    assert r.status()["error"] == {"code": "not_installed"}
    assert r.status()["engine"] == "not_installed"
    assert q.get(job.id).state == "pending"


def test_stuck_first_pass_restarts_engine_and_clears_status(tmp_path, make_runner):
    built = []
    q, r = make_runner("stuck_first_pass")
    real_factory = r._engine_factory
    r._engine_factory = lambda: built.append(1) or real_factory()
    [job] = q.add([make_tiff(tmp_path / "a.tif", pages=2)])
    r.start()
    assert wait_until(lambda: q.get(job.id).state == "done", timeout=20)
    assert q.get(job.id).warnings == 2          # 'time_limit' on both pages
    assert len(built) == 2                      # plan A note 24: a fresh engine for the next page
    assert r.status()["engine"] == "stopped" and r.status()["engine_pid"] is None


def test_stop_engine_and_shutdown_do_not_wait_for_a_load(tmp_path, make_runner):
    base = fake_engine_factory(tmp_path)

    def factory():
        engine = base()
        real_load = engine.load

        def slow_load():  # like a real load: blocks until the worker answers or dies
            end = time.monotonic() + 8
            while time.monotonic() < end:
                if not engine.is_running():
                    raise engine_error("died")
                time.sleep(0.05)
            return real_load()
        engine.load = slow_load
        return engine
    q, r = make_runner(factory=factory)
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert wait_until(lambda: r.status()["engine"] == "loading")
    started = time.monotonic()
    r.stop_engine()
    assert time.monotonic() - started < 3
    assert q.get(job.id).state == "paused" and r.status()["engine"] == "stopped"
    r.start()
    assert wait_until(lambda: r.status()["engine"] == "loading")
    started = time.monotonic()
    r.shutdown()
    assert time.monotonic() - started < 3
    assert q.get(job.id).state == "pending"


class _GpuFake:
    """A GPU engine whose calls are recorded; nothing real is started."""
    device = "cuda"
    loaded = False

    def __init__(self):
        self.calls = []
        self.running = False

    def is_running(self):
        return self.running

    def start(self):
        self.calls.append("start")
        self.running = True

        class Info:
            pid = None
        return Info()

    def load(self):
        self.calls.append("load")
        raise AssertionError("must not load")

    def stop(self, timeout_s=5.0):
        self.calls.append("stop")
        self.running = False


def test_stop_engine_during_vram_probe_starts_no_worker(tmp_path, make_runner, monkeypatch):
    import threading
    in_probe = threading.Event()

    def slow_probe():
        in_probe.set()
        time.sleep(1.0)
        return 20000
    monkeypatch.setattr(runner_mod.hardware, "free_vram_mib", slow_probe)
    engines = []
    q, r = make_runner(factory=lambda: engines.append(_GpuFake()) or engines[-1])
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert in_probe.wait(5)
    started = time.monotonic()
    with r._engine_lock:                           # the probe does not hold the engine lock
        assert time.monotonic() - started < 0.5
    r.stop_engine()                                # returns once the probe ends (job settles)
    assert time.monotonic() - started < 2.5
    assert wait_until(lambda: q.get(job.id).state == "paused")
    time.sleep(0.3)
    assert all("start" not in e.calls and "load" not in e.calls for e in engines)
    assert r.status()["engine"] == "stopped" and r.status()["engine_pid"] is None


def test_stop_engine_while_worker_starts_ends_it_before_load(tmp_path, make_runner, monkeypatch):
    import threading
    monkeypatch.setattr(runner_mod.hardware, "free_vram_mib", lambda: 20000)
    holder = {}

    class StartRace(_GpuFake):
        def start(self):
            info = super().start()
            stopper = threading.Thread(target=holder["runner"].stop_engine)
            stopper.start()
            assert wait_until(lambda: holder["runner"]._engine is None, timeout=3)
            return info
    engines = []
    q, r = make_runner(factory=lambda: engines.append(StartRace()) or engines[-1])
    holder["runner"] = r
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    r.start()
    assert wait_until(lambda: q.get(job.id).state == "paused")
    assert engines[0].calls[0] == "start" and "load" not in engines[0].calls
    assert engines[0].calls[-1] == "stop" and not engines[0].running
    assert r.status()["engine"] == "stopped"
