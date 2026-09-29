"""Persistent job queue (design 10.2). One JSON file, rewritten atomically after every change."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path

from owlocr import paths
from owlocr.engine.protocol import MODES
from owlocr.pipeline import pages

STATES = ("pending", "running", "paused", "done", "failed", "cancelled")
_FINISHED = ("done", "failed", "cancelled")


@dataclass
class Job:
    id: str
    source: str
    state: str
    mode: str | None  # None = use the default
    pages_total: int
    pages_done: int
    warnings: int
    error: str | None
    outputs: dict[str, str]
    seconds: float
    added: str
    finished: str | None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


_FIELD_NAMES = frozenset(f.name for f in fields(Job))


def _copy(job: Job) -> Job:
    return replace(job, outputs=dict(job.outputs))


def seconds_left(job: Job) -> float | None:
    """Estimated seconds until the job is done, from the measured seconds per page so far."""
    if job.pages_done <= 0 or job.seconds <= 0 or job.pages_total <= job.pages_done:
        return None
    return job.seconds / job.pages_done * (job.pages_total - job.pages_done)


class JobQueue:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._jobs: list[Job] = []
        self._load()

    # ---- persistence -------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            jobs = [Job(**{k: v for k, v in item.items() if k in _FIELD_NAMES})
                    for item in data["jobs"]]
        except (ValueError, TypeError, KeyError, AttributeError):
            backup = paths.unique_path(self._path.with_name(self._path.name + ".corrupt"))
            self._path.replace(backup)
            return
        changed = False
        for job in jobs:
            if job.state == "running" or job.state not in STATES:
                job.state = "pending"
                changed = True
        self._jobs = jobs
        if changed:
            self._save()

    def _save(self) -> None:
        payload = {"version": 1, "jobs": [asdict(j) for j in self._jobs]}
        paths.atomic_write_text(self._path, json.dumps(payload, ensure_ascii=False, indent=1))

    def relocate(self, path: Path) -> None:
        """Point the queue at a new queue.json (after the data root moved) and save it there."""
        with self._lock:
            self._path = Path(path)
            self._save()

    def _find(self, job_id: str) -> Job:
        for job in self._jobs:
            if job.id == job_id:
                return job
        raise KeyError(job_id)

    # ---- public API --------------------------------------------------
    def add(self, sources: list[Path]) -> list[Job]:
        new: list[Job] = []
        for src in sources:
            src = Path(src)
            try:
                total, state, error = pages.count_pages(src), "pending", None
            except Exception as exc:  # unreadable file: show it as a failed job
                total, state, error = 0, "failed", f"{type(exc).__name__}: {exc}"
            new.append(Job(id=uuid.uuid4().hex[:12], source=str(src), state=state, mode=None,
                           pages_total=total, pages_done=0, warnings=0, error=error, outputs={},
                           seconds=0.0, added=_now(), finished=None if state == "pending" else _now()))
        with self._lock:
            self._jobs.extend(new)
            self._save()
        return [_copy(j) for j in new]

    def get(self, job_id: str) -> Job:
        with self._lock:
            return _copy(self._find(job_id))

    def all(self) -> list[Job]:
        with self._lock:
            return [_copy(j) for j in self._jobs]

    def next_pending(self) -> Job | None:
        with self._lock:
            for job in self._jobs:
                if job.state == "pending":
                    return _copy(job)
        return None

    def update(self, job_id: str, **changes) -> Job:
        for key, value in changes.items():
            if key not in _FIELD_NAMES or key == "id":
                raise ValueError(f"cannot change {key!r}")
            if key == "state" and value not in STATES:
                raise ValueError(f"unknown state {value!r}")
            if key == "mode" and value is not None and value not in MODES:
                raise ValueError(f"unknown mode {value!r}")
        with self._lock:
            job = self._find(job_id)
            for key, value in changes.items():
                setattr(job, key, dict(value) if key == "outputs" else value)
            self._save()
            return _copy(job)

    def merge_outputs(self, job_id: str, outputs: dict) -> Job:
        """Adds format -> path entries to the job's current outputs in one locked step, so entries
        written since the caller last read the job (by the runner or another export) survive."""
        with self._lock:
            job = self._find(job_id)
            job.outputs = {**job.outputs, **outputs}
            self._save()
            return _copy(job)

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.remove(self._find(job_id))
            self._save()

    def reorder(self, ids: list[str]) -> None:
        with self._lock:
            by_id = {j.id: j for j in self._jobs}
            head = [by_id.pop(i) for i in ids if i in by_id]
            self._jobs = head + [j for j in self._jobs if j.id in by_id]
            self._save()

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = [j for j in self._jobs if j.state not in _FINISHED]
            self._save()
