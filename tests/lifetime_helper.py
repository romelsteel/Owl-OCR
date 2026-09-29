"""Stand-in for the app in the lifetime tests: starts the fake worker through SubprocessEngine,
prints the worker's pid, then waits to be killed.

    python tests/lifetime_helper.py <log file> <parent pid>

The worker is given <parent pid> (a process that outlives this one) instead of this process's
pid, so its parent-alive watchdog cannot end it when this helper is killed: only the Job Object can.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from owlocr.engine.client import SubprocessEngine  # noqa: E402


def main() -> None:
    log_file = Path(sys.argv[1])
    parent_pid = int(sys.argv[2])
    engine = SubprocessEngine(python=Path(sys.executable), worker_script=REPO / "tests" / "fake_worker.py",
                              model_dir=log_file.parent / "model", device="cpu", dtype="float32",
                              log_file=log_file)
    real_getpid = os.getpid
    os.getpid = lambda: parent_pid       # start() puts os.getpid() into --parent-pid
    try:
        info = engine.start()
    finally:
        os.getpid = real_getpid
    print(info.pid, flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
