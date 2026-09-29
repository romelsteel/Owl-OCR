"""A fake Hugging Face / ModelScope server for the model store tests (no network)."""
import dataclasses
import hashlib
import io
import json
import urllib.error
import urllib.parse

from owlocr.engine import registry

FILES = {
    "config.json": b'{"model_type": "unlimited-ocr"}',
    "modeling_unlimitedocr.py": "# model code, žluťoučký\n".encode("utf-8") * 50,
    "model-00001-of-000001.safetensors": bytes(range(256)) * 400,
}
LFS = {"model-00001-of-000001.safetensors"}


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest_entries() -> dict:
    return {
        path: {"size": len(data),
               "sha256": hashlib.sha256(data).hexdigest() if path in LFS else None,
               "git_sha1": None if path in LFS else git_blob_sha1(data)}
        for path, data in FILES.items()
    }


# The real spec with the fake files pinned (weights sha256 and the full file set).
SPEC = dataclasses.replace(
    registry.UNLIMITED_OCR,
    weights_sha256=hashlib.sha256(FILES["model-00001-of-000001.safetensors"]).hexdigest(),
    files=tuple((path, e["size"], e["sha256"], e["git_sha1"]) for path, e in manifest_entries().items()))


class _Response(io.BytesIO):
    def __init__(self, status: int, body: bytes, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class FakeRemote:
    def __init__(self):
        self.requests: list[tuple[str, int]] = []
        self.down_hosts: set[str] = set()
        self.ignore_range = False
        self.corrupt: set[tuple[str, str]] = set()      # (host, path) serving wrong bytes
        self.truncate_once: dict[str, int] = {}         # path -> next response stops at this byte
        self.extra_entries: list[dict] = []             # appended to the file list as they are

    def tree(self) -> list[dict]:
        entries = [{"type": "directory", "oid": "d0", "size": 0, "path": "assets"},
                   {"type": "file", "oid": "a1", "size": 3, "path": "assets/logo.png"},
                   {"type": "file", "oid": "a2", "size": 5, "path": ".gitattributes"}]
        for path, data in FILES.items():
            entry = {"type": "file", "path": path, "size": len(data), "oid": git_blob_sha1(data)}
            if path in LFS:
                entry["oid"] = "pointer-blob"
                entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest(), "size": len(data), "pointerSize": 131}
            entries.append(entry)
        return entries + self.extra_entries

    def open(self, url: str, start: int = 0):
        self.requests.append((url, start))
        host = urllib.parse.urlsplit(url).hostname
        if host in self.down_hosts:
            raise urllib.error.URLError(f"{host} is down")
        if "/api/models/" in url:
            return _Response(200, json.dumps(self.tree()).encode("utf-8"))
        path = urllib.parse.unquote(url.split("/resolve/", 1)[1].split("/", 1)[1])
        data = FILES[path]
        if (host, path) in self.corrupt:
            data = b"X" * len(data)
        end = self.truncate_once.pop(path, len(data))   # connection closes early, no error
        if start and not self.ignore_range:
            return _Response(206, data[start:end])
        return _Response(200, data[:end])

    def file_requests(self, name: str) -> list[tuple[str, int]]:
        return [(u, s) for u, s in self.requests if u.endswith("/" + name)]
