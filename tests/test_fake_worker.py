"""The fake worker itself, driven over raw pipes (no client code involved)."""
import json
import os
import subprocess
import sys

from owlocr.engine import lifetime
from tests.conftest import FAKE_WORKER


def _start(flags: str = ""):
    env = dict(os.environ, FAKE_WORKER=flags, PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(os.getpid())],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)


def _send(p, message):
    p.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    p.stdin.flush()


def _read(p):
    return json.loads(p.stdout.readline().decode("utf-8"))


def test_ready_ping_load_ocr_shutdown(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"not really a png")
    p = _start()
    try:
        ready = _read(p)
        assert ready["event"] == "ready"
        assert lifetime.process_alive(ready["pid"])       # the worker's own pid
        _send(p, {"cmd": "ping", "id": "1"})
        assert _read(p) == {"event": "pong", "id": "1"}
        _send(p, {"cmd": "ocr", "id": "2", "image": str(image), "mode": "quality",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        assert _read(p)["kind"] == "not_loaded"
        _send(p, {"cmd": "load", "id": "3", "model_dir": "x", "device": "cpu", "dtype": "float32"})
        assert _read(p)["event"] == "loaded"
        _send(p, {"cmd": "ocr", "id": "4", "image": str(image), "mode": "quality",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        result = _read(p)
        assert result["event"] == "result"
        assert result["text"] == "<|det|>text [100, 100, 900, 200]<|/det|>fake text for page.png"
        (tmp_path / "page.png.raw.txt").write_text("<|det|>title [1, 2, 3, 4]<|/det|>Nadpis", encoding="utf-8")
        _send(p, {"cmd": "ocr", "id": "5", "image": str(image), "mode": "fast",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        assert _read(p)["text"] == "<|det|>title [1, 2, 3, 4]<|/det|>Nadpis"
        _send(p, {"cmd": "shutdown", "id": "6"})
        assert _read(p) == {"event": "bye", "id": "6"}
        assert p.wait(timeout=5) == 0
    finally:
        p.kill()


def test_stdin_eof_ends_the_fake_worker():
    p = _start()
    try:
        assert _read(p)["event"] == "ready"
        p.stdin.close()
        assert p.wait(timeout=5) == 0
    finally:
        p.kill()
