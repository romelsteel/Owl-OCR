"""Helpers for the wizard and engine route tests: a fake Runner and a client with the X-Owl header."""
import time

from flask import Flask

from owlocr.engine.bootstrap import BootstrapError
from owlocr.hardware import Gpu
from owlocr.web.wizard_api import make_blueprint

RTX = Gpu("NVIDIA GeForce RTX 4080 SUPER", "617.14", 16376, 13858, 8.9)


class FakeRunner:
    def __init__(self):
        self.state = {"engine": "stopped", "running": False, "paused": False, "current_job": None,
                      "current_page_tokens": 0, "vram_used_mib": None}
        self.stops = 0

    def status(self):
        return dict(self.state)

    def stop_engine(self):
        self.stops += 1


def scripted_run(events_to_send, error=None, gate=None):
    def run(tier, on_event, cancel):
        for ev in events_to_send:
            on_event(ev)
        if gate is not None:
            while not cancel.is_set():
                time.sleep(0.01)
            raise BootstrapError("cancelled")
        if error:
            raise BootstrapError(error)
    return run


H = {"X-Owl": "1"}


class Client:
    """Flask test client that sends the X-Owl header plan B's guard requires."""

    def __init__(self, client):
        self._client = client

    def get(self, path, **kw):
        return self._client.get(path, **kw)

    def post(self, path, **kw):
        return self._client.post(path, headers=H, **kw)


def make_client(runner=None, controller=None, gpus=(RTX,), ram=65000, queue=None, probe_fn=None):
    app = Flask(__name__)
    runner = runner or FakeRunner()
    bp = make_blueprint(runner, controller, probe_fn=probe_fn or (lambda: (list(gpus), ram)), queue=queue)
    app.register_blueprint(bp)
    client = Client(app.test_client())
    client.blueprint = bp
    return client, runner
