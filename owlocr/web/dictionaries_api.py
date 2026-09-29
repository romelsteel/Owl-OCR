"""HTTP routes for the optional spell-check dictionaries (plan C's `dictionaries` module).

The dictionaries are never bundled: the wizard's optional step and Settings download them on
request. A download runs in a background thread; `GET /api/dictionaries` reports its progress.
A failed download removes every file of that language again, so no half dictionary is left.
"""
from __future__ import annotations

import threading
from typing import Callable

from flask import Blueprint, jsonify

from owlocr.pipeline import dictionaries, spellcheck


class DictionaryRunning(RuntimeError):
    """Raised by `DictionaryJobs.remove` while that language downloads."""


class DictionaryJobs:
    """One background download per language, with progress and the last error."""

    def __init__(self, download_fn: Callable | None = None, remove_fn: Callable | None = None) -> None:
        self._download = download_fn or dictionaries.download
        self._remove = remove_fn or dictionaries.remove
        self._lock = threading.RLock()
        self._active: set[str] = set()      # set under the lock before the thread starts
        self._jobs: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}

    def running(self, language: str) -> bool:
        with self._lock:
            return language in self._active

    def start(self, language: str) -> bool:
        with self._lock:
            if self.running(language):
                return False
            self._jobs[language] = {"done": 0, "total": 0, "error": None}
            self._active.add(language)
            thread = threading.Thread(target=self._work, args=(language,), name=f"owl-dict-{language}", daemon=True)
            self._threads[language] = thread
            try:
                thread.start()
            except BaseException:
                self._active.discard(language)
                raise
            return True

    def _work(self, language: str) -> None:
        was_installed = spellcheck.available(language)

        def progress(done: int, total: int) -> None:
            with self._lock:
                self._jobs[language].update(done=done, total=total)

        try:
            self._download(language, on_progress=progress)
            spellcheck._reset_cache()           # plan C resets too; a second reset is harmless
        except Exception as exc:                # DictionaryError, network, disk: never half-installed
            message = str(exc) if isinstance(exc, dictionaries.DictionaryError) else f"{type(exc).__name__}: {exc}"
            if not was_installed:
                try:
                    self._remove(language)
                except OSError:
                    pass
            with self._lock:
                self._jobs[language]["error"] = f"dictionary_failed: {message}"
        finally:
            with self._lock:
                self._active.discard(language)

    def remove(self, language: str) -> None:
        with self._lock:                        # check and act are one step: start() cannot slip in
            if language in self._active:
                raise DictionaryRunning(language)
            self._remove(language)
            self._jobs.pop(language, None)

    def wait(self, language: str, timeout: float | None = None) -> None:
        thread = self._threads.get(language)
        if thread is not None:
            thread.join(timeout)

    def state(self, language: str) -> dict:
        with self._lock:
            job = dict(self._jobs.get(language) or {"done": 0, "total": 0, "error": None})
        job["running"] = self.running(language)
        return job


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def languages_status(jobs: DictionaryJobs) -> list[dict]:
    languages = dictionaries.manifest()["languages"]
    rows = []
    for language in dictionaries.LANGUAGES:
        entry = languages[language]
        rows.append({"language": language, "name": entry["name"], "installed": spellcheck.available(language),
                     "size": sum(f["size"] for f in entry["files"]), "licence": entry["licence"],
                     "source": entry["source"], **jobs.state(language)})
    return rows


def make_dictionaries_blueprint(jobs: DictionaryJobs | None = None) -> Blueprint:
    bp = Blueprint("owl_dictionaries", __name__)
    work = jobs or DictionaryJobs()

    @bp.get("/api/dictionaries")
    def dictionaries_list():
        return jsonify({"languages": languages_status(work)})

    @bp.post("/api/dictionaries/<language>")
    def dictionaries_install(language):
        if language not in dictionaries.LANGUAGES:
            return _error(f"unknown_language: {language}", 404)
        return jsonify({"started": work.start(language)})

    @bp.delete("/api/dictionaries/<language>")
    def dictionaries_remove(language):
        if language not in dictionaries.LANGUAGES:
            return _error(f"unknown_language: {language}", 404)
        try:
            work.remove(language)
        except DictionaryRunning:
            return _error("dictionary_running: wait until the download finishes", 409)
        except OSError as exc:
            return _error(f"remove_failed: {exc}", 500)
        return jsonify({})

    return bp
