"""Plan C: dictionary manifest, on-demand download and verification (design 9.3)."""
import hashlib
import io
import json
import os
import re
import threading
from pathlib import Path

import pytest

from owlocr.pipeline import dictionaries, spellcheck

MANIFEST = Path(__file__).parent.parent / "owlocr" / "pipeline" / "dictionaries.json"


def test_manifest_pins_both_languages():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "{commit}" in data["url_template"] and "{path}" in data["url_template"]
    for language in ("cs", "en"):
        entry = data["languages"][language]
        assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"])
        assert entry["licence"] and entry["decision"]
        names = [f["name"] for f in entry["files"]]
        assert names[0].endswith(".LICENSE.txt")                 # licence arrives first
        assert names[1:] == [f"{entry['name']}.aff", f"{entry['name']}.dic"]
        for f in entry["files"]:
            assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) and f["size"] > 0


def test_module_reads_the_manifest():
    assert dictionaries.manifest() == json.loads(MANIFEST.read_text(encoding="utf-8"))




def _fake_entry(files: dict[str, bytes]) -> dict:
    return {"name": "cs_CZ", "commit": "0" * 40, "licence": "test",
            "files": [{"name": name, "path": f"cs_CZ/{name}", "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]}


FILES = {
    "cs_CZ.LICENSE.txt": b"licence text",
    "cs_CZ.aff": "SET UTF-8\n".encode("utf-8"),
    "cs_CZ.dic": "2\nbuď\nstrom\n".encode("utf-8"),
}


def _serve(monkeypatch, files, calls=None):
    def fake_open(url):
        if calls is not None:
            calls.append(url)
        return io.BytesIO(files[url.rsplit("/", 1)[1]])
    monkeypatch.setattr(dictionaries, "_open", fake_open)


def test_download_verifies_and_makes_dictionary_available(no_dicts, monkeypatch):
    calls, progress = [], []
    _serve(monkeypatch, FILES, calls)
    assert not spellcheck.available("cs")
    folder = dictionaries.download("cs", on_progress=lambda d, t: progress.append((d, t)),
                                   entry=_fake_entry(FILES))
    assert folder == spellcheck.dictionaries_dir()
    assert spellcheck.available("cs")
    assert spellcheck.known("buď", "cs") and not spellcheck.known("bud", "cs")
    assert calls[0].endswith("/" + "0" * 40 + "/cs_CZ/cs_CZ.LICENSE.txt")
    assert progress[-1] == (sum(len(v) for v in FILES.values()),) * 2
    assert dictionaries.verify("cs", _fake_entry(FILES)) == {}


def test_second_download_fetches_nothing(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    calls = []
    _serve(monkeypatch, FILES, calls)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    assert calls == []


def test_wrong_checksum_is_rejected_and_nothing_is_installed(no_dicts, monkeypatch):
    served = dict(FILES, **{"cs_CZ.dic": "2\nbuď\nstrom\nX\n".encode("utf-8")})
    _serve(monkeypatch, served)
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.download("cs", entry=_fake_entry(FILES))
    assert not spellcheck.available("cs")
    assert not list(spellcheck.dictionaries_dir().glob("*.part"))


def test_cancel_stops_the_download(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(dictionaries.DictionaryError, match="cancelled"):
        dictionaries.download("cs", cancel=cancel, entry=_fake_entry(FILES))
    assert not spellcheck.available("cs")


def test_verify_reports_problems(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    (spellcheck.dictionaries_dir() / "cs_CZ.aff").write_bytes(b"SET UTF-8\r\n")
    (spellcheck.dictionaries_dir() / "cs_CZ.dic").unlink()
    assert dictionaries.verify("cs", _fake_entry(FILES)) == {"cs_CZ.aff": "wrong size",
                                                             "cs_CZ.dic": "missing"}


def test_remove_deletes_the_files(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    dictionaries.remove("cs")
    assert not spellcheck.available("cs")


def test_unknown_language_is_an_error():
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.download("de")


@pytest.mark.skipif(os.environ.get("OWLOCR_NETWORK_TESTS") != "1",
                    reason="set OWLOCR_NETWORK_TESTS=1 to download the real dictionaries")
@pytest.mark.parametrize("language", ["cs", "en"])
def test_real_download_matches_the_pins(no_dicts, language):
    dictionaries.download(language)
    assert dictionaries.verify(language) == {}
    word = {"cs": "pojišťovnou", "en": "house"}[language]
    assert spellcheck.known(word, language)


# ---- final review M9: a server that sends more than the pinned size ---------------------------

class _EndlessResponse:
    def __init__(self):
        self.reads = 0

    def read(self, size):
        self.reads += 1
        assert self.reads < 50, "download kept reading past the pinned size"
        return b"x" * size

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_stops_once_a_file_is_larger_than_pinned(no_dicts, monkeypatch):
    response = _EndlessResponse()
    monkeypatch.setattr(dictionaries, "_open", lambda url: response)
    with pytest.raises(dictionaries.DictionaryError, match="larger than"):
        dictionaries.download("cs", entry=_fake_entry(FILES))
    assert response.reads <= 2                     # the pinned size is far below one chunk
    folder = spellcheck.dictionaries_dir()
    assert not list(folder.glob("*.part")) and not list(folder.glob("cs_CZ*"))
