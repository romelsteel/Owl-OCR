import pytest

from owlocr import paths, settings
from owlocr.jobs import engines
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web.server import create_app
from tests.owl_helpers import fake_engine_factory, make_tiff, wait_until

H = {"X-Owl": "1"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_WORKER", "")
    monkeypatch.setattr(engines, "engine_installed", lambda: True)
    settings.update({"output_location": "folder", "output_folder": str(tmp_path / "out"),
                     "formats": ["md", "txt"], "mode_default": "quality"})
    q = JobQueue(tmp_path / "queue.json")
    r = Runner(q, fake_engine_factory(tmp_path), settings.load)
    app = create_app(r, q)
    client = app.test_client()
    yield client, q, r, tmp_path
    r.shutdown()


def test_health_and_status(env):
    client, *_ = env
    assert client.get("/api/health").json == {"ok": True, "version": "0.1.0"}
    status = client.get("/api/status").json
    assert status["installed"] is True and status["engine"] == "stopped"
    assert status["running"] is False and status["current_job"] is None


def test_writes_need_header_and_local_host(env):
    client, *_ = env
    assert client.post("/api/run/start").status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/run/pause", headers=H).status_code == 200


def test_settings_roundtrip_and_validation(env):
    client, *_ = env
    got = client.get("/api/settings").json
    assert set(settings.DEFAULTS) <= set(got)
    changed = client.post("/api/settings", json={"mode_default": "fast"}, headers=H)
    assert changed.status_code == 200 and changed.json["mode_default"] == "fast"
    bad = client.post("/api/settings", json={"mode_default": "turbo"}, headers=H)
    assert bad.status_code == 400 and "error" in bad.json


def test_add_list_mode_reorder_remove(env):
    client, q, r, tmp = env
    folder = tmp / "scans"
    make_tiff(folder / "a.tif", pages=2)
    make_tiff(folder / "sub" / "b.tif")
    (folder / "notes.docx").write_text("ignored", encoding="utf-8")
    added = client.post("/api/jobs", json={"paths": [str(folder)]}, headers=H)
    assert added.status_code == 200
    jobs = added.json["jobs"]
    assert [j["name"] for j in jobs] == ["a.tif", "b.tif"]
    assert jobs[0]["pages_total"] == 2 and jobs[0]["eta_s"] is None
    a, b = jobs[0]["id"], jobs[1]["id"]
    assert client.post("/api/jobs", json={"paths": [str(tmp / "nothing")]}, headers=H).status_code == 400
    assert client.post("/api/jobs", json={"paths": "x"}, headers=H).status_code == 400
    assert client.post(f"/api/jobs/{a}", json={"mode": "fast"}, headers=H).json["mode"] == "fast"
    assert client.post(f"/api/jobs/{a}", json={"mode": "turbo"}, headers=H).status_code == 400
    assert client.post(f"/api/jobs/{a}", json={"mode": None}, headers=H).json["mode"] is None
    client.post(f"/api/jobs/{a}", json={"mode": "fast"}, headers=H)
    assert client.post(f"/api/jobs/{a}", json={}, headers=H).status_code == 400   # no key: no change
    assert q.get(a).mode == "fast"
    assert client.post("/api/jobs/reorder", json={"ids": [b, a]}, headers=H).json == {}
    assert [j["id"] for j in client.get("/api/jobs").json["jobs"]] == [b, a]
    assert client.delete(f"/api/jobs/{b}", headers=H).json == {}
    assert client.delete(f"/api/jobs/{b}", headers=H).status_code == 404
    assert [j["id"] for j in client.get("/api/jobs").json["jobs"]] == [a]


def test_cancel_retry_clear(env):
    client, q, r, tmp = env
    [job] = client.post("/api/jobs", json={"paths": [str(make_tiff(tmp / "a.tif"))]},
                        headers=H).json["jobs"]
    jid = job["id"]
    assert client.post(f"/api/jobs/{jid}/retry", headers=H).status_code == 409
    assert client.post(f"/api/jobs/{jid}/cancel", headers=H).json["state"] == "cancelled"
    assert client.post(f"/api/jobs/{jid}/retry", headers=H).json["state"] == "pending"
    q.update(jid, state="done")
    assert client.post("/api/jobs/clear", headers=H).json == {}
    assert client.get("/api/jobs").json["jobs"] == []
    assert client.post("/api/jobs/nope/cancel", headers=H).status_code == 404


def test_run_start_pause_and_engine_stop(env):
    client, q, r, tmp = env
    client.post("/api/jobs", json={"paths": [str(make_tiff(tmp / "a.tif"))]}, headers=H)
    started = client.post("/api/run/start", headers=H).json
    assert "installed" in started and "engine" in started
    assert wait_until(lambda: q.all()[0].state == "done")
    assert wait_until(lambda: client.get("/api/status").json["engine"] == "ready")
    stopped = client.post("/api/engine/stop", headers=H).json
    assert stopped["engine"] == "stopped"
    paused = client.post("/api/run/pause", headers=H).json
    assert paused["paused"] is True and paused["running"] is False


def test_about_and_focus(env):
    client, q, r, tmp = env
    about = client.get("/api/about").json
    assert about["version"] == "0.1.0" and "md" in about["formats_available"]
    assert about["data_root"] == str(paths.data_root())
    calls = []
    client.application.config["OWL_FOCUS"] = lambda: calls.append(1)
    assert client.post("/api/focus", headers=H).json == {"ok": True}
    assert calls == [1]


def test_unknown_route_is_json_404(env):
    client, *_ = env
    missing = client.get("/api/nothing")
    assert missing.status_code == 404 and "error" in missing.json


def test_delete_cannot_remove_a_job_the_runner_just_picked_up(env, monkeypatch):
    """DELETE checks and removes under the runner's lock. If the runner could pick the job up
    between the check and the remove, its next queue.update would raise KeyError and kill the
    runner thread, so the queue would never run again."""
    import threading

    client, q, r, tmp = env
    monkeypatch.setenv("FAKE_WORKER", "slow")
    [job] = q.add([make_tiff(tmp / "a.tif")])
    test_thread = threading.current_thread()

    class HookLock:  # releases like the real RLock, then lets the runner pick up the job once
        def __init__(self, inner):
            self.inner, self.armed, self.depth = inner, False, 0

        def acquire(self, *args, **kwargs):
            return self.inner.acquire(*args, **kwargs)

        def release(self):
            self.inner.release()

        def __enter__(self):
            self.inner.acquire()
            if threading.current_thread() is test_thread:
                self.depth += 1
            return self

        def __exit__(self, *exc):
            self.inner.release()
            if threading.current_thread() is not test_thread:
                return False
            self.depth -= 1
            if self.armed and self.depth == 0:
                self.armed = False
                r.start()
                wait_until(lambda: q.all() and q.all()[0].state == "running"
                           or not r.status()["running"], timeout=5)
            return False

    r._lock = HookLock(r._lock)
    r._lock.armed = True
    # the runner is started right after the route's first lock block: with check and remove in
    # one block the job is already gone, so the runner finds nothing to pick up
    assert client.delete(f"/api/jobs/{job.id}", headers=H).json == {}
    assert q.all() == []
    monkeypatch.setenv("FAKE_WORKER", "")
    [second] = q.add([make_tiff(tmp / "b.tif")])
    client.post("/api/run/start", headers=H)
    assert wait_until(lambda: q.get(second.id).state == "done", timeout=20)


def test_concurrent_settings_writes_neither_fail_nor_lose_updates(env):
    import threading
    client, *_ = env
    app = client.application
    keys = {"idle_stop_minutes": [5, 6], "pdf_dpi": [150, 300], "time_limit_s": [60, 61]}
    problems = []

    def writer(key, values):
        own = app.test_client()
        for i in range(60):
            value = values[i % 2]
            reply = own.post("/api/settings", json={key: value}, headers=H)
            if reply.status_code != 200:
                problems.append((key, reply.status_code))
            elif own.get("/api/settings").json[key] != value:   # only this thread writes key
                problems.append((key, "lost"))
    threads = [threading.Thread(target=writer, args=item) for item in keys.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert problems == []
