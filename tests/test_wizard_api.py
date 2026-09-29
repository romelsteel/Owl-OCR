import threading
from pathlib import Path

import pytest

from owlocr import hardware, paths
from owlocr.engine import bootstrap
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


def test_probe(env):
    client, _ = make_client()
    data = client.get("/api/wizard/probe").get_json()
    assert data["gpus"][0]["name"] == "NVIDIA GeForce RTX 4080 SUPER"
    assert data["ram_mib"] == 65000
    assert data["tier"]["name"] == "gpu_full" and data["tier"]["default_mode"] == "quality"
    assert Path(data["data_root"]).resolve() == (env / "data").resolve()
    assert data["free_bytes"] > 0 and data["required_bytes"] == 16 * 1024**3
    assert data["installed"] is False and data["interrupted"] is False and data["install"] is None
    assert data["env_override"] is False and data["cpu_tier_enabled"] is True


def test_location_sets_data_root(env):
    client, runner = make_client()
    target = env / "other drive" / "Owl"
    data = client.post("/api/wizard/location", json={"path": str(target)}).get_json()
    assert data["data_root"] == str(target.resolve())
    assert paths.data_root().resolve() == target.resolve()
    assert runner.stops == 0


def test_location_moves_existing_data_after_stopping_the_engine(env):
    (env / "data" / "models" / "unlimited_ocr").mkdir(parents=True)
    client, runner = make_client()
    response = client.post("/api/wizard/location", json={"path": str(env / "new")})
    assert response.status_code == 200
    assert (env / "new" / "models" / "unlimited_ocr").is_dir()
    assert runner.stops == 1


def test_location_errors(env):
    client, _ = make_client()
    assert client.post("/api/wizard/location", json={}).get_json()["error"].startswith("empty")
    response = client.post("/api/wizard/location", json={"path": "relative"})
    assert response.status_code == 400 and response.get_json()["error"].startswith("not_absolute")


def test_location_change_moves_the_queue_along(env):
    old = env / "data"
    queue = JobQueue(old / "queue.json")
    [job] = queue.add([make_tiff(env / "in" / "a.tif")])
    client, _ = make_client(queue=queue)
    response = client.post("/api/wizard/location", json={"path": str(env / "new")})
    assert response.status_code == 200
    assert [j.id for j in JobQueue(env / "new" / "queue.json").all()] == [job.id]
    assert not (old / "queue.json").exists()


def test_adopt_calls_store(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.store, "adopt", lambda folder, spec, move=True: calls.append((folder, spec.engine_id, move)))
    client, _ = make_client()
    assert client.post("/api/wizard/adopt", json={"path": "C:\\Users\\x\\engine"}).get_json() == {"ok": True}
    assert client.post("/api/wizard/adopt", json={"path": "C:\\Users\\x\\engine", "copy": True}).status_code == 200
    assert [c[2] for c in calls] == [True, False]
    assert calls[0][1] == "unlimited_ocr"


def test_adopt_failure(env, monkeypatch):
    def boom(folder, spec, move=True):
        raise wizard_api.store.StoreError("sha256 mismatch in model-00001-of-000001.safetensors")
    monkeypatch.setattr(wizard_api.store, "adopt", boom)
    client, _ = make_client()
    response = client.post("/api/wizard/adopt", json={"path": "C:\\nowhere"})
    assert response.status_code == 400
    assert response.get_json()["error"].startswith("adopt_failed: sha256 mismatch")


def test_install_progress_and_collapsed_events(env):
    events = [StageEvent("tools", "start", 0, 0, "checking")] + \
             [StageEvent("tools", "progress", i, 10, "") for i in range(1, 11)] + \
             [StageEvent("tools", "done", 10, 10, "")]
    controller = InstallController(run_fn=scripted_run(events))
    client, _ = make_client(controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    controller.wait(5)
    data = client.get("/api/wizard/progress").get_json()
    assert data["running"] is False and data["error"] is None
    assert [(e["state"], e["done"]) for e in data["events"]] == [("start", 0), ("progress", 10), ("done", 10)]


def test_install_error_is_reported(env):
    controller = InstallController(run_fn=scripted_run([], error="not_enough_space: 1 bytes needed, 0 free"))
    client, _ = make_client(controller=controller)
    client.post("/api/wizard/install")
    controller.wait(5)
    assert client.get("/api/wizard/progress").get_json()["error"].startswith("not_enough_space")


def test_cancel_and_second_start(env):
    gate = threading.Event()
    controller = InstallController(run_fn=scripted_run([StageEvent("torch", "start", 0, 0, "")], gate=gate))
    client, _ = make_client(controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    assert client.post("/api/wizard/install").get_json() == {"started": False}
    assert client.post("/api/wizard/cancel").get_json() == {}
    controller.wait(5)
    data = client.get("/api/wizard/progress").get_json()
    assert data["running"] is False and data["error"] == "cancelled"


def test_install_refused_on_unsupported_hardware(env):
    client, _ = make_client(gpus=(), ram=8000)
    response = client.post("/api/wizard/install")
    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported: ram_too_small"


def test_finished_install_refreshes_the_installed_cache(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.engines, "forget_installed", lambda: calls.append("forget"))
    controller = InstallController(run_fn=scripted_run([StageEvent("mark", "done", 0, 0, "")]))
    client, _ = make_client(controller=controller)
    client.post("/api/wizard/install")
    controller.wait(5)
    assert calls == ["forget"]


def test_demo_install_is_used_when_requested(env, monkeypatch):
    monkeypatch.setenv("OWLOCR_DEMO_INSTALL", "1")
    assert InstallController()._run_fn is wizard_api.demo_install
    monkeypatch.delenv("OWLOCR_DEMO_INSTALL")
    assert InstallController()._run_fn is bootstrap.run


def test_location_and_adopt_refused_while_installing(env, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_api.store, "adopt", lambda folder, spec, move=True: calls.append(folder))
    gate = threading.Event()
    controller = InstallController(run_fn=scripted_run([StageEvent("torch", "start", 0, 0, "")], gate=gate))
    client, runner = make_client(controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    response = client.post("/api/wizard/location", json={"path": str(env / "elsewhere")})
    assert response.status_code == 409 and response.get_json()["error"].startswith("install_running")
    (env / "data" / "engine").mkdir(parents=True)          # with engine data: the same answer
    response = client.post("/api/wizard/location", json={"path": str(env / "elsewhere")})
    assert response.status_code == 409 and response.get_json()["error"].startswith("install_running")
    response = client.post("/api/wizard/adopt", json={"path": r"C:\Users\x\engine"})
    assert response.status_code == 409 and response.get_json()["error"].startswith("install_running")
    assert calls == [] and runner.stops == 1     # only the install route stopped the engine
    assert paths.data_root().resolve() == (env / "data").resolve()
    client.post("/api/wizard/cancel")
    controller.wait(5)


def test_location_uses_an_owlocr_subfolder_of_a_foreign_folder(env):
    target = env / "Documents"
    target.mkdir()
    (target / "letter.txt").write_text("not ours", encoding="utf-8")
    client, _ = make_client()
    data = client.post("/api/wizard/location", json={"path": str(target)}).get_json()
    assert data["data_root"].endswith("OwlOCR")
    assert paths.data_root().resolve() == (target / "OwlOCR").resolve()


def test_queue_that_cannot_follow_does_not_fail_the_change(env):
    class BrokenQueue:
        def relocate(self, path):
            raise OSError("disk gone")
    client, _ = make_client(queue=BrokenQueue())
    response = client.post("/api/wizard/location", json={"path": str(env / "new")})
    assert response.status_code == 200
    assert paths.data_root().resolve() == (env / "new").resolve()


def test_probe_survives_an_unreadable_install_record(env, monkeypatch):
    def broken():
        raise ValueError("bad json")
    monkeypatch.setattr(wizard_api.bootstrap, "read_install", broken)
    client, _ = make_client()
    response = client.get("/api/wizard/probe")
    assert response.status_code == 200
    data = response.get_json()
    assert data["install"] is None and data["probe_error"].startswith("install_unreadable: ValueError")


def test_probe_has_no_error_normally(env):
    client, _ = make_client()
    assert client.get("/api/wizard/probe").get_json()["probe_error"] is None


def test_install_refused_while_the_queue_runs(env):
    ran = []
    controller = InstallController(run_fn=lambda tier, on_event, cancel: ran.append(tier))
    client, runner = make_client(controller=controller)
    runner.state.update(running=True, paused=False)
    response = client.post("/api/wizard/install")
    assert response.status_code == 409
    assert response.get_json()["error"] == wizard_api.QUEUE_RUNNING
    assert not controller.running and ran == [] and runner.stops == 0


def test_install_stops_the_engine_before_it_starts(env):
    calls = []
    controller = InstallController(run_fn=lambda tier, on_event, cancel: calls.append("install"))
    runner = FakeRunner()
    runner.stop_engine = lambda: calls.append("stop")
    client, _ = make_client(runner=runner, controller=controller)
    assert client.post("/api/wizard/install").get_json() == {"started": True}
    controller.wait(5)
    assert calls == ["stop", "install"]


def test_probe_survives_a_missing_data_drive(env, monkeypatch):
    """M-4: an unplugged data drive must not make the probe answer 500; the wizard is how to fix it."""
    def gone(_root):
        raise FileNotFoundError("drive not ready")
    monkeypatch.setattr(wizard_api.relocate, "free_bytes", gone)
    client, _ = make_client()
    response = client.get("/api/wizard/probe")
    assert response.status_code == 200
    data = response.get_json()
    assert data["free_bytes"] == 0 and data["probe_error"].startswith("disk_unreadable: FileNotFoundError")


def test_probe_survives_a_failing_hardware_probe(env):
    def broken():
        raise OSError("nvidia-smi crashed")
    client, _ = make_client(probe_fn=broken)
    response = client.get("/api/wizard/probe")
    assert response.status_code == 200
    data = response.get_json()
    assert data["gpus"] == [] and data["tier"]["name"] == "unsupported"
    assert data["probe_error"].startswith("hardware_probe_failed: OSError")


def test_probe_error_codes_have_messages():
    from tests.test_wizard_strings import STRINGS
    for code in ("disk_unreadable", "hardware_probe_failed"):
        assert f"wz_error_{code}" in STRINGS["en"] and f"wz_error_{code}" in STRINGS["cs"]
