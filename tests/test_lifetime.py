"""Design 5.6: the engine worker never outlives the app."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from owlocr.engine import lifetime
from tests.conftest import FAKE_WORKER, REPO

HELPER = REPO / "tests" / "lifetime_helper.py"


def _gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not lifetime.process_alive(pid):
            return True
        time.sleep(0.05)
    return False


def _start_helper(tmp_path: Path, flags: str) -> tuple[subprocess.Popen, int]:
    env = dict(os.environ, FAKE_WORKER=flags)
    # The worker's watchdog watches this pytest process, which stays alive during the test.
    helper = subprocess.Popen([sys.executable, str(HELPER), str(tmp_path / "engine.log"), str(os.getpid())],
                              stdout=subprocess.PIPE, env=env)
    worker_pid = int(helper.stdout.readline())
    assert lifetime.process_alive(worker_pid)
    return helper, worker_pid


def test_worker_dies_when_the_app_is_killed(tmp_path):
    helper, worker_pid = _start_helper(tmp_path, "ignore_stdin_eof,ignore_shutdown")
    try:
        helper.kill()                        # TerminateProcess: no clean-up code runs in the app
        # The watchdog watches the still-running pytest process and stdin EOF is ignored,
        # so only the Job Object can end the worker here.
        assert _gone_within(worker_pid, 5)
    finally:
        helper.kill()
        lifetime._terminate(worker_pid)


def test_worker_exits_on_stdin_eof(tmp_path):
    env = dict(os.environ, FAKE_WORKER="")
    worker = subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(os.getpid())],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        assert b'"ready"' in worker.stdout.readline()
        worker.stdin.close()
        assert worker.wait(timeout=5) == 0
    finally:
        worker.kill()


def test_parent_watchdog_ends_the_worker(tmp_path):
    # The "parent" is a separate short-lived process that is not in any job with the worker,
    # and the worker ignores stdin EOF, so only the watchdog can end it.
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    env = dict(os.environ, FAKE_WORKER="ignore_stdin_eof")
    worker = subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(parent.pid)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        worker_pid = int(json.loads(worker.stdout.readline())["pid"])
        parent.kill()
        parent.wait(timeout=5)
        assert _gone_within(worker_pid, 5)
    finally:
        worker.kill()
        parent.kill()
