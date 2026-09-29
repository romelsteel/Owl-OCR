import threading

import pytest

from owlocr import hardware, paths
from owlocr.engine.bootstrap import StageEvent
from owlocr.jobs.queue import JobQueue
from owlocr.web import wizard_api
from owlocr.web.wizard_api import InstallController
from tests.owl_helpers import make_tiff
from tests.wizard_fakes import FakeRunner, make_client, scripted_run


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr(hardware, "CPU_TIER_ENABLED", True)
    paths.set_data_root(tmp_path / "data")
    return tmp_path


def test_move_refused_while_queue_runs(env):
    (env / "data" / "engine").mkdir(parents=True)
    runner = FakeRunner()
    runner.state.update(running=True, engine="busy")
    client, _ = make_client(runner)
    response = client.post("/api/engine/move", json={"path": str(env / "new")})
    assert response.status_code == 409 and response.get_json()["error"].startswith("queue_running")
    assert (env / "data" / "engine").is_dir()


def test_verify(env, monkeypatch):
    monkeypatch.setattr(wizard_api.store, "verify", lambda engine_id="unlimited_ocr": {"tokenizer.json": "sha mismatch"})
    client, _ = make_client()
    assert client.post("/api/engine/verify").get_json() == {"problems": {"tokenizer.json": "sha mismatch"}}


def test_remove_and_reinstall(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.bootstrap, "remove_engine", lambda: calls.append("remove"))
    monkeypatch.setattr(wizard_api.bootstrap, "reset_install", lambda: calls.append("reset"))
    monkeypatch.setattr(wizard_api.engines, "forget_installed", lambda: calls.append("forget"))
    client, runner = make_client()
    assert client.post("/api/engine/remove").get_json() == {}
    assert client.post("/api/engine/reinstall").get_json() == {}
    assert calls == ["remove", "forget", "reset", "forget"] and runner.stops == 2


def test_engine_move(env):
    (env / "data" / "engine").mkdir(parents=True)
    client, runner = make_client()
    data = client.post("/api/engine/move", json={"path": str(env / "moved")}).get_json()
    assert data["data_root"] == str((env / "moved").resolve())
    assert (env / "moved" / "engine").is_dir() and runner.stops == 1


def test_engine_move_takes_the_queue_along(env):
    old = env / "data"
    (old / "engine").mkdir(parents=True)
    queue = JobQueue(old / "queue.json")
    [job] = queue.add([make_tiff(env / "in" / "a.tif")])
    client, _ = make_client(queue=queue)
    response = client.post("/api/engine/move", json={"path": str(env / "moved")})
    assert response.status_code == 200
    assert [j.id for j in JobQueue(env / "moved" / "queue.json").all()] == [job.id]
    assert not (old / "queue.json").exists()
    queue.update(job.id, state="paused")          # the queue now writes to the new file
    assert not (old / "queue.json").exists()
    assert JobQueue(env / "moved" / "queue.json").get(job.id).state == "paused"


def test_engine_actions_are_refused_while_installing(env):
    gate = threading.Event()
    controller = InstallController(run_fn=scripted_run([StageEvent("torch", "start", 0, 0, "")], gate=gate))
    client, runner = make_client(controller=controller)
    client.post("/api/wizard/install")
    for path in ("/api/engine/remove", "/api/engine/reinstall", "/api/engine/verify"):
        response = client.post(path)
        assert response.status_code == 409 and response.get_json()["error"].startswith("install_running"), path
    assert client.post("/api/engine/move", json={"path": str(env / "x")}).status_code == 409
    assert runner.stops == 1     # only the install route stopped the engine
    client.post("/api/wizard/cancel")
    controller.wait(5)


def test_remove_and_reinstall_refused_while_queue_runs(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.bootstrap, "remove_engine", lambda: calls.append("remove"))
    monkeypatch.setattr(wizard_api.bootstrap, "reset_install", lambda: calls.append("reset"))
    runner = FakeRunner()
    runner.state.update(running=True, engine="busy")
    client, _ = make_client(runner)
    for path in ("/api/engine/remove", "/api/engine/reinstall"):
        response = client.post(path)
        assert response.status_code == 409 and response.get_json()["error"].startswith("queue_running"), path
    assert calls == [] and runner.stops == 0


def test_verify_failure_is_a_json_error(env, monkeypatch):
    def broken(engine_id="unlimited_ocr"):
        raise OSError("device not ready")
    monkeypatch.setattr(wizard_api.store, "verify", broken)
    client, _ = make_client()
    response = client.post("/api/engine/verify")
    assert response.status_code == 500
    assert response.get_json()["error"].startswith("verify_failed: device not ready")


def test_engine_move_into_a_foreign_folder_uses_an_owlocr_subfolder(env):
    (env / "data" / "engine").mkdir(parents=True)
    target = env / "Documents"
    target.mkdir()
    (target / "letter.txt").write_text("not ours", encoding="utf-8")
    client, _ = make_client()
    data = client.post("/api/engine/move", json={"path": str(target)}).get_json()
    assert data["data_root"].endswith("OwlOCR") and data["leftovers"] == []
    assert (target / "OwlOCR" / "engine").is_dir() and (target / "letter.txt").is_file()


def test_engine_move_reports_leftovers(env, monkeypatch):
    (env / "data" / "engine").mkdir(parents=True)
    real_move = wizard_api.relocate.move_data_root

    def move_with_leftover(dest):
        folder = real_move(dest)
        wizard_api.relocate.last_leftovers.append(r"C:\old\engine: in use")
        return folder
    monkeypatch.setattr(wizard_api.relocate, "move_data_root", move_with_leftover)
    monkeypatch.setattr(wizard_api.relocate, "last_leftovers", [])
    client, _ = make_client()
    data = client.post("/api/engine/move", json={"path": str(env / "moved")}).get_json()
    assert data["leftovers"] == [r"C:\old\engine: in use"]


def test_file_operations_run_one_at_a_time(env, monkeypatch):
    started, release = threading.Event(), threading.Event()
    removes = []

    def slow_remove():
        removes.append("remove")
        started.set()
        assert release.wait(10)
    monkeypatch.setattr(wizard_api.bootstrap, "remove_engine", slow_remove)
    monkeypatch.setattr(wizard_api.store, "verify", lambda engine_id="unlimited_ocr": {})
    controller = InstallController(run_fn=scripted_run([]))
    client, _ = make_client(controller=controller)
    first = {}
    worker = threading.Thread(target=lambda: first.update(r=client.post("/api/engine/remove")))
    worker.start()
    try:
        assert started.wait(10)
        assert client.blueprint.file_ops_busy() is True
        for path, body in (("/api/engine/remove", None), ("/api/engine/reinstall", None),
                           ("/api/engine/verify", None), ("/api/engine/move", {"path": str(env / "m")}),
                           ("/api/wizard/location", {"path": str(env / "m")}),
                           ("/api/wizard/adopt", {"path": str(env / "m")}), ("/api/wizard/install", None)):
            response = client.post(path, json=body) if body else client.post(path)
            assert response.status_code == 409, path
            assert response.get_json() == {"error": "busy: another engine action is running"}, path
    finally:
        release.set()
        worker.join(10)
    assert first["r"].status_code == 200 and removes == ["remove"]
    assert client.blueprint.file_ops_busy() is False
    assert client.post("/api/engine/verify").get_json() == {"problems": {}}
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    controller.wait(5)
    assert client.post("/api/engine/remove").status_code == 200 and removes == ["remove", "remove"]
