import hashlib
import http.server
import os
import sys
import threading
import time

import pytest

from owlocr.engine import uvtool

PAYLOAD = bytes(range(256)) * 4096          # 1 MiB


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            if start >= len(PAYLOAD):
                self.send_response(416)
                self.end_headers()
                return
            self.send_response(206)
        else:
            self.send_response(200)
        body = PAYLOAD[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/file.zip"
    httpd.shutdown()


def test_download_whole_file(server, tmp_path):
    seen = []
    dest = tmp_path / "f.zip"
    uvtool.download_file(server, dest, on_progress=lambda d, t: seen.append((d, t)))
    assert dest.read_bytes() == PAYLOAD
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert not (tmp_path / "f.zip.part").exists()


def test_download_resumes_partial_file(server, tmp_path):
    dest = tmp_path / "f.zip"
    (tmp_path / "f.zip.part").write_bytes(PAYLOAD[:1000])
    uvtool.download_file(server, dest)
    assert dest.read_bytes() == PAYLOAD


def test_download_with_complete_partial_file(server, tmp_path):
    dest = tmp_path / "f.zip"
    (tmp_path / "f.zip.part").write_bytes(PAYLOAD)
    uvtool.download_file(server, dest)
    assert dest.read_bytes() == PAYLOAD


def test_download_cancel(server, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(uvtool.Cancelled):
        uvtool.download_file(server, tmp_path / "f.zip", cancel=cancel)
    assert not (tmp_path / "f.zip").exists()


def test_sha256_file(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(PAYLOAD)
    assert uvtool.sha256_file(p) == hashlib.sha256(PAYLOAD).hexdigest()


def test_run_command_streams_lines_and_returns_code():
    lines = []
    code = uvtool.run_command([sys.executable, "-c", "print('eins'); print('zwei ž'); raise SystemExit(3)"],
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, on_line=lines.append)
    assert code == 3
    assert lines == ["eins", "zwei ž"]


def test_run_command_cancel_kills_the_process():
    cancel = threading.Event()
    lines = []

    def on_line(line):
        lines.append(line)
        cancel.set()

    started = time.monotonic()
    code = uvtool.run_command(
        [sys.executable, "-u", "-c", "import time; print('started'); time.sleep(60)"],
        env=dict(os.environ), on_line=on_line, cancel=cancel)
    assert code == uvtool.CANCELLED
    assert lines == ["started"]
    assert time.monotonic() - started < 20


def test_run_command_keeps_draining_when_on_line_raises():
    """M-1: a failing log write must not stop the pump, or the tool blocks on a full pipe."""
    calls = []

    def on_line(line):
        calls.append(line)
        raise OSError("disk full")

    result = {}

    def go():
        result["code"] = uvtool.run_command(
            [sys.executable, "-c", "for i in range(20000): print('x' * 100)"],
            env=dict(os.environ), on_line=on_line)

    worker = threading.Thread(target=go, daemon=True)
    worker.start()
    worker.join(timeout=60)
    assert not worker.is_alive(), "run_command hung after on_line raised"
    assert result["code"] == 0
    assert len(calls) == 1          # reported once, then only drained
