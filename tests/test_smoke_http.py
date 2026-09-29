"""Browser-free smoke test: the real entry point with the fake worker, driven over HTTP."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from owlocr.__main__ import pick_port
from owlocr.engine.lifetime import process_alive
from tests.owl_helpers import FAKE_WORKER, REPO, make_tiff, wait_until


def _call(port, method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Owl": "1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _up(port):
    try:
        return _call(port, "GET", "/api/health")["ok"]
    except (urllib.error.URLError, OSError):
        return False


def test_add_start_done_export_over_http(tmp_path):
    env = dict(os.environ)
    env.update({"OWLOCR_HOME": str(tmp_path / "home"), "OWLOCR_CONFIG": str(tmp_path / "config"),
                "OWLOCR_ENGINE_WORKER": str(FAKE_WORKER), "FAKE_WORKER": "",
                "PYTHONIOENCODING": "utf-8"})
    port = pick_port()
    log = open(tmp_path / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "owlocr", "--server-only", "--port", str(port)],
                            cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT)
    worker_pid = None
    try:
        assert wait_until(lambda: _up(port), timeout=30), "server did not start"
        status = _call(port, "GET", "/api/status")
        assert status["installed"] is True and status["engine"] == "stopped"

        _call(port, "POST", "/api/settings", {"output_location": "folder",
                                              "output_folder": str(tmp_path / "out"),
                                              "formats": ["md", "txt"]})
        scan = make_tiff(tmp_path / "in" / "scan.tif", pages=2)
        [job] = _call(port, "POST", "/api/jobs", {"paths": [str(scan)]})["jobs"]
        assert job["state"] == "pending" and job["pages_total"] == 2

        _call(port, "POST", "/api/run/start")

        def job_state():
            return _call(port, "GET", "/api/jobs")["jobs"][0]["state"]
        assert wait_until(lambda: job_state() == "done", timeout=30)

        done = _call(port, "GET", "/api/jobs")["jobs"][0]
        assert done["pages_done"] == 2
        assert Path(done["outputs"]["md"]).is_file() and Path(done["outputs"]["owl"]).is_file()

        exported = _call(port, "POST", f"/api/jobs/{job['id']}/export", {"formats": ["txt"]})
        assert Path(exported["outputs"]["txt"]).is_file()
        assert "fake text for" in _call(port, "GET", f"/api/jobs/{job['id']}/text")["text"]

        worker_pid = _call(port, "GET", "/api/status")["engine_pid"]
        assert worker_pid and process_alive(worker_pid)

        second = subprocess.run([sys.executable, "-m", "owlocr", "--server-only"], cwd=str(REPO),
                                env=env, timeout=30, capture_output=True, text=True)
        assert second.returncode == 0  # a second launch only focuses the first one
        assert _up(port)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()
    if worker_pid:
        assert wait_until(lambda: not process_alive(worker_pid), timeout=5)
