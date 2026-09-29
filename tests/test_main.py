import ctypes
import socket
import threading

import pytest

from werkzeug.serving import make_server

from owlocr import __main__ as owl_main
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web.server import create_app


def test_pick_port_gives_a_free_port():
    port = owl_main.pick_port()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def test_pick_port_avoids_busy_preferred_port():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert owl_main.pick_port(taken) != taken


def test_single_instance_mutex(monkeypatch, tmp_path):
    assert owl_main.acquire_single_instance() is True
    try:
        assert owl_main.acquire_single_instance() is False
    finally:
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(owl_main._mutex_handle))
        owl_main._mutex_handle = None
    first = owl_main.mutex_name()
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "other"))
    assert owl_main.mutex_name() != first


def test_focus_existing_without_instance_file():
    assert owl_main.focus_existing() is False


def test_focus_existing_calls_running_instance(tmp_path):
    queue = JobQueue(tmp_path / "queue.json")
    runner = Runner(queue, lambda: None, dict)
    app = create_app(runner, queue)
    called = threading.Event()
    app.config["OWL_FOCUS"] = called.set
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        owl_main.write_instance(server.server_port)
        assert owl_main.focus_existing() is True
        assert called.wait(3)
    finally:
        server.shutdown()
        runner.shutdown()


def test_server_that_never_comes_up_shuts_down_and_exits_1(monkeypatch):
    shut = []

    class FakeRunner:
        def __init__(self, *args):
            pass

        def shutdown(self):
            shut.append(1)

    class FakeApp:
        config = {}

        def run(self, **kwargs):
            pass            # like a Flask thread that failed to bind the port

    monkeypatch.setattr(owl_main, "acquire_single_instance", lambda: True)
    monkeypatch.setattr(owl_main, "sweep_stale_worker", lambda: None)
    monkeypatch.setattr(owl_main, "Runner", FakeRunner)
    monkeypatch.setattr(owl_main, "create_app", lambda runner, queue: FakeApp())
    monkeypatch.setattr(owl_main, "write_instance", lambda port: None)
    monkeypatch.setattr(owl_main, "wait_until_up", lambda port: False)
    monkeypatch.setattr(owl_main.atexit, "register", lambda fn: None)
    monkeypatch.setattr(owl_main, "_run_window", lambda *a: pytest.fail("no window"))
    monkeypatch.setattr(owl_main.webbrowser, "open", lambda url: pytest.fail("no browser"))
    assert owl_main.main([]) == 1
    assert shut == [1]
