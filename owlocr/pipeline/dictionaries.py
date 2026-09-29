"""Download and verify the Hunspell dictionaries (design 9.3).

The dictionaries are not bundled in v1: the app downloads them on demand from the pinned
LibreOffice commits in dictionaries.json into spellcheck.dictionaries_dir(), unmodified and
together with their licence text. A file is moved into place only after its size and sha256
match, so a present .aff/.dic pair is always a verified one.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from owlocr.pipeline import spellcheck

LANGUAGES = ("cs", "en")
_CHUNK = 1 << 16
_TIMEOUT_S = 60


class DictionaryError(RuntimeError):
    pass


def manifest() -> dict:
    return json.loads(Path(__file__).with_name("dictionaries.json").read_text(encoding="utf-8"))


def _entry(language: str) -> dict:
    languages = manifest()["languages"]
    if language not in languages:
        raise DictionaryError(f"no dictionary is known for language {language!r}")
    return languages[language]


def _open(url: str):
    """Seam for tests: returns a readable binary response."""
    return urllib.request.urlopen(url, timeout=_TIMEOUT_S)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(language: str, entry: dict | None = None) -> dict[str, str]:
    """name -> problem for every file of the language; an empty dict means all files are good."""
    entry = entry or _entry(language)
    folder = spellcheck.dictionaries_dir()
    problems = {}
    for f in entry["files"]:
        path = folder / f["name"]
        if not path.is_file():
            problems[f["name"]] = "missing"
        elif path.stat().st_size != f["size"]:
            problems[f["name"]] = "wrong size"
        elif _sha256(path) != f["sha256"]:
            problems[f["name"]] = "wrong sha256"
    return problems


def download(language: str, on_progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None, entry: dict | None = None) -> Path:
    """Download the language's files (licence first), verify each, return the folder."""
    entry = entry or _entry(language)
    template = manifest()["url_template"]
    folder = spellcheck.dictionaries_dir()
    folder.mkdir(parents=True, exist_ok=True)
    total = sum(f["size"] for f in entry["files"])
    done = 0
    for f in entry["files"]:
        dest = folder / f["name"]
        if dest.is_file() and dest.stat().st_size == f["size"] and _sha256(dest) == f["sha256"]:
            done += f["size"]
            if on_progress:
                on_progress(done, total)
            continue
        part = dest.with_name(dest.name + ".part")
        digest = hashlib.sha256()
        written = 0
        try:
            with _open(template.format(commit=entry["commit"], path=f["path"])) as response, \
                    open(part, "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DictionaryError("cancelled")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > f["size"]:        # final review M9: never write until EOF
                        raise DictionaryError(f"{f['name']}: larger than the pinned size")
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
        except DictionaryError:
            part.unlink(missing_ok=True)
            raise
        except OSError as error:
            part.unlink(missing_ok=True)
            raise DictionaryError(f"{f['name']}: download failed: {error}") from error
        if part.stat().st_size != f["size"] or digest.hexdigest() != f["sha256"]:
            part.unlink(missing_ok=True)
            raise DictionaryError(f"{f['name']}: size or sha256 does not match the pinned value")
        os.replace(part, dest)
    spellcheck._reset_cache()
    return folder


def remove(language: str) -> None:
    entry = _entry(language)
    folder = spellcheck.dictionaries_dir()
    for f in entry["files"]:
        (folder / f["name"]).unlink(missing_ok=True)
    spellcheck._reset_cache()
