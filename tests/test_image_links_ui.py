"""Task 22b: the Markdown image-link setting and the images-folder button (plan C note 19)."""
import pytest

from owlocr import settings
from owlocr.jobs import engines
from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web import server
from owlocr.web.server import create_app
from tests.owl_helpers import fake_engine_factory, make_tiff, static_text

H = {"X-Owl": "1"}
INDEX = static_text("index.html")
APP = static_text("app.js")


def test_image_links_select_is_in_the_settings_form():
    start = INDEX.index('id="settingsForm"')
    select = INDEX.index('id="setImageLinks"')
    assert start < select < INDEX.index("</form>", start)
    block = INDEX[select:INDEX.index("</select>", select)]
    assert '<option value="markdown" data-i18n="il_markdown"></option>' in block
    assert '<option value="obsidian" data-i18n="il_obsidian"></option>' in block
    assert '<label for="setImageLinks" data-i18n="set_image_links"></label>' in INDEX


def test_settings_form_reads_and_writes_image_links():
    assert "$('setImageLinks').value = s.image_links;" in APP
    assert "image_links: $('setImageLinks').value," in APP


def test_done_job_offers_the_images_folder_only_when_it_exists():
    assert ("if (job.images_dir) actions.append(button('btn_open_images', "
            "function () { openPath(job.images_dir); }));") in APP


def test_job_json_reports_the_images_folder(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    job = q.add([make_tiff(tmp_path / "doc.tif")])[0]
    assert server.job_json(q.get(job.id))["images_dir"] is None  # no md output
    md = tmp_path / "doc.md"
    q.update(job.id, outputs={"md": str(md)})
    assert server.job_json(q.get(job.id))["images_dir"] is None  # folder not there
    (tmp_path / "doc_images").mkdir()
    assert server.job_json(q.get(job.id))["images_dir"] == str(tmp_path / "doc_images")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_WORKER", "")
    monkeypatch.setattr(engines, "engine_installed", lambda: True)
    q = JobQueue(tmp_path / "queue.json")
    r = Runner(q, fake_engine_factory(tmp_path), settings.load)
    yield create_app(r, q).test_client()
    r.shutdown()


def test_image_links_setting_is_saved_and_validated(client):
    ok = client.post("/api/settings", json={"image_links": "obsidian"}, headers=H)
    assert ok.status_code == 200 and settings.get("image_links") == "obsidian"
    bad = client.post("/api/settings", json={"image_links": "wiki"}, headers=H)
    assert bad.status_code == 400 and settings.get("image_links") == "obsidian"
