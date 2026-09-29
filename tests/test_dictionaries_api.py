"""Routes for the optional dictionaries, on top of plan C's `dictionaries` module (network faked)."""
import hashlib
import io
import threading

import pytest
from flask import Flask

from owlocr.pipeline import dictionaries, spellcheck
from owlocr.web.dictionaries_api import DictionaryJobs, make_dictionaries_blueprint

H = {"X-Owl": "1"}
FILES = {
    "cs_CZ.LICENSE.txt": b"GNU GPL licence text",
    "cs_CZ.aff": "SET UTF-8\n".encode("utf-8"),
    "cs_CZ.dic": "2\nbuď\nstrom\n".encode("utf-8"),
}


REAL_MANIFEST = dictionaries.manifest()


def fake_manifest(files=FILES):
    real = REAL_MANIFEST
    cs = {"name": "cs_CZ", "source": "https://example.invalid/cs_CZ", "commit": "0" * 40,
          "licence": "GNU GPL", "decision": "test",
          "files": [{"name": n, "path": f"cs_CZ/{n}", "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                    for n, d in files.items()]}
    return {"url_template": real["url_template"], "languages": {"cs": cs, "en": real["languages"]["en"]}}


@pytest.fixture
def served(no_dicts, monkeypatch):
    """Serves FILES instead of GitHub; the test may change what is served."""
    content = dict(FILES)
    monkeypatch.setattr(dictionaries, "manifest", lambda: fake_manifest())
    monkeypatch.setattr(dictionaries, "_open", lambda url: io.BytesIO(content[url.rsplit("/", 1)[1]]))
    return content


def client(jobs=None):
    app = Flask(__name__)
    jobs = jobs or DictionaryJobs()
    app.register_blueprint(make_dictionaries_blueprint(jobs))
    return app.test_client(), jobs


def by_language(response):
    return {row["language"]: row for row in response.get_json()["languages"]}


def test_list_shows_state_size_and_licence(served):
    c, _ = client()
    rows = by_language(c.get("/api/dictionaries"))
    assert set(rows) == {"cs", "en"}
    assert rows["cs"]["installed"] is False and rows["cs"]["running"] is False
    assert rows["cs"]["size"] == sum(len(d) for d in FILES.values())
    assert rows["cs"]["licence"] == "GNU GPL" and rows["cs"]["source"].startswith("https://")
    assert rows["en"]["licence"].startswith("SCOWL") and rows["en"]["size"] > 500_000


def test_install_makes_the_dictionary_work_without_a_restart(served):
    c, jobs = client()
    assert spellcheck.known("bud", "cs") is True            # no dictionary: everything is "known"
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": True}
    jobs.wait("cs", 10)
    row = by_language(c.get("/api/dictionaries"))["cs"]
    assert row["installed"] is True and row["error"] is None
    assert row["done"] == row["total"] == sum(len(d) for d in FILES.values())
    assert spellcheck.known("buď", "cs") and not spellcheck.known("bud", "cs")


def test_failed_download_leaves_nothing_behind(served):
    served["cs_CZ.dic"] = b"2\nbroken\n"                     # wrong sha256 for the last file
    c, jobs = client()
    c.post("/api/dictionaries/cs", headers=H)
    jobs.wait("cs", 10)
    row = by_language(c.get("/api/dictionaries"))["cs"]
    assert row["installed"] is False and row["error"].startswith("dictionary_failed:")
    assert list(spellcheck.dictionaries_dir().iterdir()) == []   # licence and .aff removed again


def test_remove(served):
    c, jobs = client()
    c.post("/api/dictionaries/cs", headers=H)
    jobs.wait("cs", 10)
    assert c.delete("/api/dictionaries/cs", headers=H).get_json() == {}
    assert by_language(c.get("/api/dictionaries"))["cs"]["installed"] is False
    assert spellcheck.known("bud", "cs") is True


def test_one_download_per_language_and_no_remove_meanwhile(served):
    release = threading.Event()

    def slow_download(language, on_progress=None):
        release.wait(10)

    c, jobs = client(DictionaryJobs(download_fn=slow_download))
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": True}
    assert c.post("/api/dictionaries/cs", headers=H).get_json() == {"started": False}
    assert by_language(c.get("/api/dictionaries"))["cs"]["running"] is True
    response = c.delete("/api/dictionaries/cs", headers=H)
    assert response.status_code == 409 and response.get_json()["error"].startswith("dictionary_running")
    release.set()
    jobs.wait("cs", 10)


def test_unknown_language(served):
    c, _ = client()
    assert c.post("/api/dictionaries/de", headers=H).status_code == 404
    assert c.delete("/api/dictionaries/de", headers=H).status_code == 404


def test_remove_is_refused_from_the_moment_start_returns():
    """The language counts as running before the worker thread body executes."""
    from owlocr.web.dictionaries_api import DictionaryRunning
    gate = threading.Event()
    removed = []
    jobs = DictionaryJobs(download_fn=lambda language, on_progress=None: gate.wait(10),
                          remove_fn=removed.append)
    assert jobs.start("cs") is True
    with pytest.raises(DictionaryRunning):
        jobs.remove("cs")
    assert removed == []
    gate.set()
    jobs.wait("cs", 10)
    assert jobs.running("cs") is False
    jobs.remove("cs")
    assert removed == ["cs"]


def test_a_remove_in_progress_blocks_a_start_until_it_is_done():
    events = []
    in_remove, release = threading.Event(), threading.Event()

    def slow_remove(language):
        events.append("remove-begin")
        in_remove.set()
        release.wait(10)
        events.append("remove-end")

    jobs = DictionaryJobs(download_fn=lambda language, on_progress=None: events.append("download"),
                          remove_fn=slow_remove)
    remover = threading.Thread(target=jobs.remove, args=("cs",))
    remover.start()
    assert in_remove.wait(10)
    starter = threading.Thread(target=jobs.start, args=("cs",))
    starter.start()
    starter.join(0.3)
    assert starter.is_alive()                     # start() waits for the lock, no download yet
    assert "download" not in events
    release.set()
    remover.join(10)
    starter.join(10)
    jobs.wait("cs", 10)
    assert events == ["remove-begin", "remove-end", "download"]
