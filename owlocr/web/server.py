"""Flask routes of the app: the plan-B part of the HTTP API table in the interface contract.

Only 127.0.0.1 / localhost may call it, and every POST or DELETE must carry the header
`X-Owl: 1`. A web page on another origin cannot add that header without a CORS preflight, which
this server never grants, so other sites cannot drive the app.
"""
from __future__ import annotations

import platform
import threading
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from PIL import Image
from werkzeug.exceptions import HTTPException

from owlocr import __version__, paths
from owlocr import settings as settings_mod
from owlocr.engine import registry
from owlocr.engine.protocol import MODES
from owlocr.export import FORMATS
from owlocr.export.text import document_text
from owlocr.jobs import engines
from owlocr.jobs.formats import available_formats
from owlocr.jobs.queue import Job, JobQueue, seconds_left
from owlocr.jobs.runner import Runner, discard_work, export_document, resume_file
from owlocr.pipeline import pages
from owlocr.pipeline.document import load_sidecar, save_sidecar, to_json
from owlocr.web.dictionaries_api import make_dictionaries_blueprint
from owlocr.web.wizard_api import BUSY, INSTALL_RUNNING, make_blueprint

STATIC_DIR = Path(__file__).resolve().parent / "static"
_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
REVIEW_DPI = 150
# Serialises every settings write in this process (settings.update is an unlocked
# read-modify-write and paths.atomic_write_text uses one temp name per process).
# Plan D: every settings writer must hold this lock too.
SETTINGS_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def images_dir(job: Job) -> str | None:
    """The picture folder of the job's Markdown export, when it exists (plan C note 19)."""
    md = job.outputs.get("md")
    if not md:
        return None
    folder = Path(md).with_name(Path(md).stem + "_images")
    return str(folder) if folder.is_dir() else None


def job_json(job: Job) -> dict:
    data = asdict(job)
    data["name"] = Path(job.source).name
    data["eta_s"] = seconds_left(job) if job.state in ("pending", "running", "paused") else None
    data["images_dir"] = images_dir(job)
    return data


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)  # JSON true is not a number


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("a JSON object is expected")
    return data


def create_app(runner: Runner, queue: JobQueue) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["OWL_FOCUS"] = None  # __main__ puts a callable here that raises the window

    def get_job(job_id: str) -> Job:
        try:
            return queue.get(job_id)
        except KeyError:
            raise ApiError("job not found", 404) from None

    def document_path(job: Job) -> Path:
        owl = job.outputs.get("owl")
        if owl and Path(owl).is_file():
            return Path(owl)
        partial = resume_file(job.id)
        if partial.is_file():
            return partial
        raise ApiError("this job has no document yet", 404)

    def is_current(job_id: str) -> bool:
        return runner.status()["current_job"] == job_id

    def status_json():
        return jsonify({**runner.status(), "installed": engines.engine_installed()})

    # ---- guards and errors -------------------------------------------
    @app.before_request
    def _guard():
        host = (request.host or "").rsplit(":", 1)[0]
        if host not in _ALLOWED_HOSTS:
            return jsonify(error="forbidden host"), 403
        if request.method in ("POST", "PUT", "DELETE") and request.headers.get("X-Owl") != "1":
            return jsonify(error="missing X-Owl header"), 403
        return None

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return jsonify(error=exc.message), exc.status

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        return jsonify(error=exc.description or exc.name), exc.code

    @app.errorhandler(Exception)
    def _crash(exc: Exception):
        return jsonify(error=f"{type(exc).__name__}: {exc}"), 500

    # ---- page and basics ---------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, version=__version__)

    @app.get("/api/status")
    def status():
        return status_json()

    @app.get("/api/about")
    def about():
        spec = registry.UNLIMITED_OCR
        return jsonify(version=__version__, python=platform.python_version(),
                       engine_id=spec.engine_id, engine_revision=spec.revision,
                       data_root=str(paths.data_root()), config_dir=str(paths.config_dir()),
                       logs_dir=str(paths.logs_dir()),
                       formats_available=list(available_formats()))

    @app.post("/api/focus")
    def focus():
        callback = app.config.get("OWL_FOCUS")
        if callback is not None:
            callback()
        return jsonify(ok=True)

    # ---- settings ----------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        return jsonify(settings_mod.load())

    @app.post("/api/settings")
    def post_settings():
        body = _body()
        try:
            with SETTINGS_LOCK:
                saved = settings_mod.update(body)
            return jsonify(saved)
        except settings_mod.SettingsError as exc:
            raise ApiError(str(exc)) from None

    # ---- jobs --------------------------------------------------------
    @app.get("/api/jobs")
    def list_jobs():
        return jsonify(jobs=[job_json(j) for j in queue.all()])

    @app.post("/api/jobs")
    def add_jobs():
        raw = _body().get("paths")
        if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
            raise ApiError("'paths' must be a list of strings")
        files = pages.find_inputs([Path(p) for p in raw if p.strip()])
        if not files:
            raise ApiError("no supported files found")
        return jsonify(jobs=[job_json(j) for j in queue.add(files)])

    @app.post("/api/jobs/reorder")
    def reorder_jobs():
        ids = _body().get("ids")
        if not isinstance(ids, list):
            raise ApiError("'ids' must be a list")
        queue.reorder([str(i) for i in ids])
        return jsonify({})

    @app.post("/api/jobs/clear")
    def clear_jobs():
        for job in queue.all():
            if job.state in ("done", "failed", "cancelled"):
                discard_work(job.id)
        queue.clear_finished()
        return jsonify({})

    @app.post("/api/jobs/<job_id>")
    def change_job(job_id):
        get_job(job_id)
        body = _body()
        if "mode" not in body:   # a missing key must not silently clear the job's mode
            raise ApiError("'mode' is required (null clears the job's own mode)")
        mode = body["mode"]
        if mode is not None and mode not in MODES:
            raise ApiError(f"unknown mode {mode!r}")
        return jsonify(job_json(queue.update(job_id, mode=mode)))

    @app.delete("/api/jobs/<job_id>")
    def delete_job(job_id):
        try:
            removed = runner.remove(job_id)   # checks and removes under the runner's lock
        except KeyError:
            raise ApiError("job not found", 404) from None
        if not removed:
            raise ApiError("the job is running; cancel it first", 409)
        return jsonify({})

    @app.post("/api/jobs/<job_id>/cancel")
    def cancel_job(job_id):
        get_job(job_id)
        runner.cancel(job_id)
        return jsonify(job_json(queue.get(job_id)))

    @app.post("/api/jobs/<job_id>/retry")
    def retry_job(job_id):
        job = get_job(job_id)
        if job.state not in ("failed", "cancelled"):
            raise ApiError("only failed or cancelled jobs can be retried", 409)
        return jsonify(job_json(queue.update(job_id, state="pending", error=None, finished=None)))

    # ---- runner ------------------------------------------------------
    @app.post("/api/run/start")
    def run_start():
        # the install route starts the installer under the same lock, so neither check can race
        with wizard.try_file_ops() as got:  # never restart the runner on half-moved engine files
            if not got:
                raise ApiError(BUSY, 409)
            if wizard.install_running():  # the installer may be replacing the engine right now
                raise ApiError(INSTALL_RUNNING, 409)
            runner.start()
        return status_json()

    @app.post("/api/run/pause")
    def run_pause():
        runner.pause()
        return status_json()

    @app.post("/api/engine/stop")
    def engine_stop():
        runner.stop_engine()
        return status_json()

    # ---- results and review -------------------------------------------
    @app.get("/api/jobs/<job_id>/document")
    def get_document(job_id):
        path = document_path(get_job(job_id))
        return Response(to_json(load_sidecar(path)), mimetype="application/json")

    @app.post("/api/jobs/<job_id>/document")
    def edit_block(job_id):
        get_job(job_id)
        body = _body()
        page_no, block_no, text = body.get("page"), body.get("block"), body.get("text")
        if not _is_int(page_no) or not _is_int(block_no) or not isinstance(text, str):
            raise ApiError("'page' and 'block' must be integers and 'text' a string")
        edited = {}

        def apply_edit():
            # Runs under the runner's lock: a paused job cannot start (and overwrite its
            # unfinished document) between the check and the save.
            path = document_path(get_job(job_id))  # fresh: the job may have finished meanwhile
            doc = load_sidecar(path)
            page = next((p for p in doc.pages if p.index == page_no), None)
            if page is None or not 0 <= block_no < len(page.blocks):
                raise ApiError("no such page or block", 404)
            block = page.blocks[block_no]
            block.text = text
            block.flags = []  # the offsets no longer fit the edited text
            save_sidecar(doc, path)
            edited["block"] = block

        if not runner.unless_current(job_id, apply_edit):
            raise ApiError("the job is running; edit it when it has finished", 409)
        return jsonify(asdict(edited["block"]))

    @app.get("/api/jobs/<job_id>/page/<int:n>.png")
    def page_image(job_id, n):
        job = get_job(job_id)
        source = Path(job.source)
        if not source.is_file():
            raise ApiError("the source file is gone", 404)
        if n < 0 or n >= pages.count_pages(source):
            raise ApiError("no such page", 404)
        cache = paths.work_dir(job_id) / "pages" / f"{n}.png"
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            pages.render_page(source, n, REVIEW_DPI, cache)
            rotation = 0
            try:
                doc = load_sidecar(document_path(job))
                rotation = next((p.rotation_applied for p in doc.pages if p.index == n), 0)
            except ApiError:
                pass
            if rotation:
                with Image.open(cache) as img:
                    turned = img.rotate(-rotation, expand=True)
                turned.save(cache)
        return send_file(cache, mimetype="image/png", max_age=0)

    @app.post("/api/jobs/<job_id>/export")
    def export_job(job_id):
        job = get_job(job_id)
        if is_current(job_id):
            raise ApiError("the job is running; export it when it has finished", 409)
        formats = _body().get("formats")
        if not isinstance(formats, list) or not formats:
            raise ApiError("'formats' must be a non-empty list")
        for fmt in formats:
            if fmt not in FORMATS:
                raise ApiError(f"unknown format {fmt!r}")
            if fmt not in available_formats():
                raise ApiError(f"format not available yet: {fmt}")
        doc = load_sidecar(document_path(job))
        outputs = export_document(doc, Path(job.source), formats, settings_mod.load())
        queue.merge_outputs(job_id, outputs)  # fresh read under the queue's lock, never the snapshot
        return jsonify(outputs=outputs)

    @app.get("/api/jobs/<job_id>/text")
    def job_text(job_id):
        doc = load_sidecar(document_path(get_job(job_id)))
        keep = bool(settings_mod.load().get("keep_page_furniture"))
        return jsonify(text=document_text(doc, keep_furniture=keep))

    wizard = make_blueprint(runner, queue=queue)
    app.register_blueprint(wizard)
    app.register_blueprint(make_dictionaries_blueprint())
    return app
