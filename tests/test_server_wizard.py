"""Plan D routes inside plan B's real app: registration, the X-Owl guard, and the installed state."""
import pytest

from owlocr.engine import bootstrap
from owlocr.jobs import engines
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web import wizard_api
from owlocr.web.server import create_app

H = {"X-Owl": "1"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)
    queue = JobQueue(tmp_path / "queue.json")
    runner = Runner(queue, lambda: None, dict)
    client = create_app(runner, queue).test_client()
    engines.forget_installed()
    yield client, runner
    runner.shutdown()
    engines.forget_installed()


def test_wizard_routes_are_registered(app):
    client, _ = app
    probe = client.get("/api/wizard/probe")
    assert probe.status_code == 200
    assert probe.get_json()["tier"]["name"] in ("gpu_full", "gpu_reduced", "cpu", "unsupported")
    assert client.get("/api/wizard/progress").get_json() == {"events": [], "running": False, "error": None}
    languages = client.get("/api/dictionaries").get_json()["languages"]
    assert [d["language"] for d in languages] == ["cs", "en"]


def test_wizard_and_engine_posts_need_the_owl_header(app):
    client, _ = app
    for path in ("/api/wizard/cancel", "/api/wizard/install", "/api/engine/remove", "/api/engine/verify",
                 "/api/dictionaries/cs"):
        assert client.post(path).status_code == 403, path
    assert client.delete("/api/dictionaries/cs").status_code == 403
    assert client.post("/api/wizard/cancel", headers=H).status_code == 200


def test_owl_guard_covers_registered_dictionary_routes(app):
    # with the header the dictionary route itself answers (unknown language), so the 403
    # above really comes from plan B's guard in front of a registered route
    client, _ = app
    assert client.post("/api/dictionaries/xx").status_code == 403
    answer = client.post("/api/dictionaries/xx", headers=H)
    assert answer.status_code == 404
    assert answer.get_json()["error"].startswith("unknown_language")


def test_status_follows_bootstrap_is_installed(app, monkeypatch):
    client, _ = app
    monkeypatch.setattr(bootstrap, "is_installed", lambda: True)
    engines.forget_installed()
    assert client.get("/api/status").get_json()["installed"] is True
    monkeypatch.setattr(bootstrap, "is_installed", lambda: False)
    engines.forget_installed()
    assert client.get("/api/status").get_json()["installed"] is False


def test_remove_stops_the_engine_first_and_refreshes_status(app, monkeypatch):
    client, runner = app
    calls = []
    monkeypatch.setattr(runner, "stop_engine", lambda: calls.append("stop"))
    monkeypatch.setattr(bootstrap, "remove_engine", lambda: calls.append("remove"))
    monkeypatch.setattr(bootstrap, "is_installed", lambda: True)
    engines.engine_installed()                         # cache "installed"
    monkeypatch.setattr(bootstrap, "is_installed", lambda: False)
    assert client.post("/api/engine/remove", headers=H).status_code == 200
    assert calls == ["stop", "remove"]
    assert client.get("/api/status").get_json()["installed"] is False


def test_verify_answers_through_the_app(app, monkeypatch):
    client, _ = app
    monkeypatch.setattr("owlocr.engine.store.verify", lambda engine_id="unlimited_ocr": {})
    assert client.post("/api/engine/verify", headers=H).get_json() == {"problems": {}}


def test_run_start_refused_while_engine_files_are_being_moved(app, monkeypatch):
    client, runner = app
    started = []
    monkeypatch.setattr(runner, "start", lambda: started.append(1))
    wizard = client.application.blueprints["owl_wizard"]
    with wizard.try_file_ops() as got:                 # the blueprint's real file-operations lock
        assert got and wizard.file_ops_busy()
        answer = client.post("/api/run/start", headers=H)
        assert answer.status_code == 409
        assert answer.get_json() == {"error": "busy: another engine action is running"}
        assert started == []
    assert not wizard.file_ops_busy()
    assert client.post("/api/run/start", headers=H).status_code == 200
    assert started == [1]


def test_run_start_refused_while_the_installer_runs(app, monkeypatch):
    client, runner = app
    started = []
    monkeypatch.setattr(runner, "start", lambda: started.append(1))
    wizard = client.application.blueprints["owl_wizard"]
    monkeypatch.setattr(wizard, "install_running", lambda: True)
    answer = client.post("/api/run/start", headers=H)
    assert answer.status_code == 409
    assert answer.get_json() == {"error": wizard_api.INSTALL_RUNNING}
    assert started == [] and not wizard.file_ops_busy()
