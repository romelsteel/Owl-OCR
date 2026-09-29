import os
import subprocess
import sys
import time

from owlocr.engine import lifetime

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def _wait_dead(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not lifetime.process_alive(pid):
            return True
        time.sleep(0.05)
    return not lifetime.process_alive(pid)


def test_process_alive():
    assert lifetime.process_alive(os.getpid())
    assert not lifetime.process_alive(0)
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not lifetime.process_alive(p.pid)


def test_closing_the_job_kills_its_processes():
    job = lifetime.JobObject()
    p = subprocess.Popen(SLEEPER)
    try:
        job.assign(p.pid)
        assert lifetime.process_alive(p.pid)
        job.close()
        assert _wait_dead(p.pid, 5)
    finally:
        p.kill()


def test_close_twice_is_harmless():
    job = lifetime.JobObject()
    job.close()
    assert job._handle is None
    job.close()
    assert job._handle is None


def test_create_time_identifies_a_process():
    p = subprocess.Popen(SLEEPER)
    try:
        first = lifetime._process_create_time(p.pid)
        assert isinstance(first, int) and first > 0
        assert lifetime._process_create_time(p.pid) == first
        assert lifetime._terminate(p.pid)
        assert _wait_dead(p.pid, 5)
        assert lifetime._process_create_time(p.pid) is None
    finally:
        p.kill()
