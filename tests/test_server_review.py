from pathlib import Path

import pytest
from PIL import Image

from owlocr import settings
from owlocr.jobs import engines
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.pipeline.document import load_sidecar
from owlocr.web import server
from owlocr.web.server import create_app
from tests.owl_helpers import fake_engine_factory, make_tiff, wait_until

H = {"X-Owl": "1"}


@pytest.fixture
def done_job(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_WORKER", "")
    monkeypatch.setattr(engines, "engine_installed", lambda: True)
    settings.update({"output_location": "folder", "output_folder": str(tmp_path / "out"),
                     "formats": ["md"], "mode_default": "quality"})
    q = JobQueue(tmp_path / "queue.json")
    r = Runner(q, fake_engine_factory(tmp_path), settings.load)
    client = create_app(r, q).test_client()
    [job] = client.post("/api/jobs", json={"paths": [str(make_tiff(tmp_path / "book.tif", pages=2))]},
                        headers=H).json["jobs"]
    client.post("/api/run/start", headers=H)
    assert wait_until(lambda: q.get(job["id"]).state == "done")
    # 'done' is written a moment before the runner lets go of the job; until then an edit is 409
    assert wait_until(lambda: r.status()["current_job"] is None)
    yield client, q, job["id"], tmp_path, r
    r.shutdown()


def test_document_json(done_job):
    client, q, jid, tmp, _ = done_job
    doc = client.get(f"/api/jobs/{jid}/document").json
    assert [p["index"] for p in doc["pages"]] == [0, 1]
    block = doc["pages"][0]["blocks"][0]
    assert block["box"] == [100, 100, 900, 200] and block["text"].startswith("fake text")


def test_document_missing_before_first_page(tmp_path, monkeypatch):
    monkeypatch.setattr(engines, "engine_installed", lambda: True)
    q = JobQueue(tmp_path / "queue.json")
    r = Runner(q, fake_engine_factory(tmp_path), settings.load)
    client = create_app(r, q).test_client()
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    assert client.get(f"/api/jobs/{job.id}/document").status_code == 404


def test_edit_block_is_saved_and_exported(done_job):
    client, q, jid, tmp, _ = done_job
    edited = client.post(f"/api/jobs/{jid}/document",
                         json={"page": 1, "block": 0, "text": "Opravený text"}, headers=H)
    assert edited.status_code == 200
    assert edited.json["text"] == "Opravený text" and edited.json["flags"] == []
    owl = Path(q.get(jid).outputs["owl"])
    assert load_sidecar(owl).pages[1].blocks[0].text == "Opravený text"
    bad = client.post(f"/api/jobs/{jid}/document", json={"page": 1, "block": 9, "text": "x"},
                      headers=H)
    assert bad.status_code == 404
    assert client.post(f"/api/jobs/{jid}/document", json={"page": "1"},
                       headers=H).status_code == 400
    assert client.post(f"/api/jobs/{jid}/document", json={"page": True, "block": 0, "text": "x"},
                       headers=H).status_code == 400  # a bool is not a page number
    assert client.post(f"/api/jobs/{jid}/document", json={"page": 1, "block": False, "text": "x"},
                       headers=H).status_code == 400
    exported = client.post(f"/api/jobs/{jid}/export", json={"formats": ["md", "txt"]}, headers=H)
    assert exported.status_code == 200
    outputs = exported.json["outputs"]
    assert "Opravený text" in Path(outputs["txt"]).read_text(encoding="utf-8")
    assert Path(outputs["md"]).name == "book_1.md"  # the first export is never overwritten
    assert q.get(jid).outputs["txt"] == outputs["txt"]


def test_export_rejects_unknown_or_unavailable(done_job, monkeypatch):
    client, q, jid, tmp, _ = done_job
    assert client.post(f"/api/jobs/{jid}/export", json={"formats": ["rtf"]},
                       headers=H).status_code == 400
    monkeypatch.setattr("owlocr.web.server.available_formats", lambda: ("md", "txt"))
    unavailable = client.post(f"/api/jobs/{jid}/export", json={"formats": ["docx"]}, headers=H)
    assert unavailable.status_code == 400 and "not available" in unavailable.json["error"]


def test_text_and_page_image(done_job):
    client, q, jid, tmp, _ = done_job
    text = client.get(f"/api/jobs/{jid}/text").json["text"]
    assert "fake text for" in text
    image = client.get(f"/api/jobs/{jid}/page/1.png")
    assert image.status_code == 200 and image.mimetype == "image/png"
    out = tmp / "p.png"
    out.write_bytes(image.data)
    with Image.open(out) as img:
        assert img.width > 0 and img.height > img.width  # the test page is portrait
    assert client.get(f"/api/jobs/{jid}/page/7.png").status_code == 404


def test_running_job_cannot_be_edited_or_exported(done_job, monkeypatch):
    client, q, jid, tmp, r = done_job
    status = r.status()
    monkeypatch.setattr(r, "status", lambda: {**status, "current_job": jid})
    monkeypatch.setattr(r, "unless_current", lambda job_id, action: job_id != jid and action() is None)
    edit = client.post(f"/api/jobs/{jid}/document", json={"page": 0, "block": 0, "text": "x"},
                       headers=H)
    assert edit.status_code == 409
    export = client.post(f"/api/jobs/{jid}/export", json={"formats": ["txt"]}, headers=H)
    assert export.status_code == 409
    assert "txt" not in q.get(jid).outputs


def test_export_merges_into_fresh_outputs(done_job, monkeypatch):
    """Entries written while the export runs (by the runner or another export) survive."""
    client, q, jid, tmp, _ = done_job
    real = server.export_document

    def export_while_someone_writes(doc, source, formats, settings):
        q.update(jid, outputs={**q.get(jid).outputs, "pdf": "other.pdf"})
        return real(doc, source, formats, settings)

    monkeypatch.setattr(server, "export_document", export_while_someone_writes)
    before = q.get(jid).outputs
    exported = client.post(f"/api/jobs/{jid}/export", json={"formats": ["txt"]}, headers=H)
    assert exported.status_code == 200
    after = q.get(jid).outputs
    assert after["owl"] == before["owl"] and after["pdf"] == "other.pdf"
    assert after["txt"] == exported.json["outputs"]["txt"]
