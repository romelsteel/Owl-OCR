"""Model files on disk: download once, verify, remember (design 6.3).

manifest.json in the model folder is written LAST, after every file has been verified. It holds
the pinned revision and the size and hash of every file. On later starts is_ready() only checks
that the files exist with the recorded sizes: no hashing, no network.
The manifest format is the one the spike wrote ({"repo", "commit", "files"}), so the model the
owner already downloaded with spike/download_model.py is recognised as ready.
"""
import fnmatch
import hashlib
import json
import shutil
import threading
import urllib.parse
import urllib.request
from pathlib import Path, PureWindowsPath
from typing import Callable

from owlocr import __version__, paths
from owlocr.engine import registry
from owlocr.engine.registry import EngineSpec

_HF_TREE = "https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
_HF_FILE = "https://huggingface.co/{repo}/resolve/{revision}/{path}"
_MODELSCOPE_FILE = "https://www.modelscope.cn/models/{repo}/resolve/master/{path}"
_CHUNK = 8 << 20
_TIMEOUT_S = 60


class StoreError(RuntimeError):
    pass


def manifest_path(engine_id: str = "unlimited_ocr") -> Path:
    return paths.model_dir(engine_id) / "manifest.json"


def _safe_rel(rel: object) -> str:
    """A manifest key as a path inside the model folder; StoreError for anything that could escape it
    (absolute, drive, UNC, '..')."""
    if not isinstance(rel, str) or not rel:
        raise StoreError(f"bad file name in manifest: {rel!r}")
    p = PureWindowsPath(rel)                    # splits on both slash and backslash
    if p.drive or p.root or ".." in p.parts:
        raise StoreError(f"unsafe file name in manifest: {rel!r}")
    return rel


def _pinned_files(spec: EngineSpec) -> dict[str, dict]:
    """spec.files in manifest form: path -> {size, sha256, git_sha1}."""
    return {rel: {"size": size, "sha256": sha256, "git_sha1": git_sha1}
            for rel, size, sha256, git_sha1 in spec.files}


def _read_manifest(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    try:
        for rel in data["files"]:
            _safe_rel(rel)
    except StoreError:
        return None
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    """Hash the way git does, so small (non-LFS) files can be checked against the blob id."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % path.stat().st_size)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_file(path: Path, info: dict, deep: bool) -> str | None:
    """None when the file is good, else a short reason."""
    if not path.is_file():
        return "missing"
    size = path.stat().st_size
    if size != info["size"]:
        return f"size {size} != {info['size']}"
    if deep:
        if info.get("sha256"):
            if _sha256(path) != info["sha256"]:
                return "sha256 mismatch"
        elif info.get("git_sha1"):
            if _git_blob_sha1(path) != info["git_sha1"]:
                return "git sha1 mismatch"
    return None


def is_ready(engine_id: str = "unlimited_ocr", deep: bool = False) -> bool:
    spec = registry.get(engine_id)
    folder = paths.model_dir(engine_id)
    manifest = _read_manifest(folder)
    if manifest is None or manifest.get("commit") != spec.revision:
        return False
    return all(_check_file(folder / rel, info, deep) is None for rel, info in manifest["files"].items())


def verify(engine_id: str = "unlimited_ocr") -> dict[str, str]:
    spec = registry.get(engine_id)
    folder = paths.model_dir(engine_id)
    manifest = _read_manifest(folder)
    if manifest is None:
        return {"manifest.json": "missing"}
    if manifest.get("commit") != spec.revision:
        return {"manifest.json": f"revision {manifest.get('commit')} != {spec.revision}"}
    problems = {}
    for rel, info in manifest["files"].items():
        reason = _check_file(folder / rel, info, deep=True)
        if reason:
            problems[rel] = reason
    return problems


# ---- network ----------------------------------------------------------------------------------

def _open(url: str, start: int = 0):
    """GET `url`, from byte `start` on. Returns a response with .status, .headers, .read(n)."""
    headers = {"User-Agent": f"OwlOCR/{__version__}", "Accept-Encoding": "identity"}
    if start:
        headers["Range"] = f"bytes={start}-"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=_TIMEOUT_S)


def _ignored(path: str, spec: EngineSpec) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in spec.ignore)


def _next_link(link_header: str | None) -> str | None:
    for part in (link_header or "").split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1: part.find(">")]
    return None


def fetch_remote_manifest(spec: EngineSpec) -> dict[str, dict]:
    """path -> {size, sha256, git_sha1} for every file of the pinned revision, minus spec.ignore."""
    files: dict[str, dict] = {}
    url = _HF_TREE.format(repo=spec.repo, revision=spec.revision)
    try:
        while url:
            with _open(url) as response:
                entries = json.loads(response.read().decode("utf-8"))
                url = _next_link(response.headers.get("Link"))
            for entry in entries:
                if entry.get("type") != "file" or _ignored(entry["path"], spec):
                    continue
                _safe_rel(entry["path"])
                lfs = entry.get("lfs")
                files[entry["path"]] = {
                    "size": int(lfs["size"] if lfs else entry["size"]),
                    "sha256": lfs["oid"] if lfs else None,
                    "git_sha1": None if lfs else entry["oid"],
                }
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:   # also a list of the wrong shape
        raise StoreError(f"cannot read the file list of {spec.repo}: {e}") from e
    if not files:
        raise StoreError(f"{spec.repo} at {spec.revision} lists no files")
    return files


def _download_file(urls: list[str], dest: Path, info: dict, on_bytes: Callable[[int], None],
                   cancel: threading.Event | None) -> None:
    """Fetch one file into dest via dest.part, resuming, trying each url in turn."""
    part = dest.with_name(dest.name + ".part")
    if part.exists():
        on_bytes(part.stat().st_size)          # bytes fetched by an earlier, interrupted run
    last_error: Exception | None = None
    for url in urls:
        try:
            have = part.stat().st_size if part.exists() else 0
            if have > info["size"]:
                on_bytes(-have)
                part.unlink()
                have = 0
            if have < info["size"]:
                with _open(url, have) as response:
                    if have and response.status != 206:     # server ignored Range: start again
                        on_bytes(-have)
                        have = 0
                    with open(part, "ab" if have else "wb") as fh:
                        while True:
                            if cancel is not None and cancel.is_set():
                                raise StoreError("cancelled")
                            chunk = response.read(_CHUNK)
                            if not chunk:
                                break
                            fh.write(chunk)
                            on_bytes(len(chunk))
            size = part.stat().st_size
            if size < info["size"]:
                # The connection closed early (urllib returns b"" rather than raising): keep the
                # .part so the next source continues from here with a Range request.
                last_error = StoreError(f"{dest.name}: connection closed at {size} of {info['size']} "
                                        f"bytes (from {url})")
                continue
            reason = _check_file(part, info, deep=True)
            if reason is None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                part.replace(dest)
                return
            on_bytes(-size)
            part.unlink()
            last_error = StoreError(f"{dest.name}: {reason} (from {url})")
        except StoreError as e:
            if str(e) == "cancelled":
                raise
            last_error = e
        except OSError as e:                     # includes urllib.error.URLError and HTTPError
            last_error = e
    raise StoreError(f"cannot download {dest.name}: {last_error}")


def download(spec: EngineSpec, on_progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None) -> None:
    """Download and verify every file of the pinned revision into model_dir(spec.engine_id).
    Resumable: finished files are kept, partial files continue. manifest.json is written last.
    The file list is the set pinned in the registry (spec.files), or the Hugging Face list when
    the spec pins none, so the ModelScope fallback works while Hugging Face is unreachable.
    Raises StoreError("cancelled") when `cancel` is set."""
    if is_ready(spec.engine_id):
        return
    folder = paths.model_dir(spec.engine_id)
    folder.mkdir(parents=True, exist_ok=True)
    files = _pinned_files(spec) or fetch_remote_manifest(spec)   # pinned set: works while HF is down
    for rel in files:
        _safe_rel(rel)
    total = sum(info["size"] for info in files.values())
    done = 0

    def on_bytes(n: int) -> None:
        nonlocal done
        done += n
        if on_progress is not None:
            on_progress(done, total)

    for rel, info in files.items():
        dest = folder / rel
        if _check_file(dest, info, deep=True) is None:
            on_bytes(info["size"])
            continue
        dest.unlink(missing_ok=True)
        quoted = urllib.parse.quote(rel)
        urls = [_HF_FILE.format(repo=spec.repo, revision=spec.revision, path=quoted),
                _MODELSCOPE_FILE.format(repo=spec.modelscope_repo, path=quoted)]
        _download_file(urls, dest, info, on_bytes, cancel)
    _write_manifest(folder, spec, files)


def _write_manifest(folder: Path, spec: EngineSpec, files: dict[str, dict]) -> None:
    paths.atomic_write_text(folder / "manifest.json", json.dumps(
        {"repo": spec.repo, "commit": spec.revision, "engine_id": spec.engine_id, "files": files}, indent=1))


# ---- adopt an existing download ----------------------------------------------------------

def _find_model_folder(folder: Path, spec: EngineSpec) -> Path:
    for candidate in (folder, folder / spec.engine_id, folder / "models" / spec.engine_id):
        if (candidate / "config.json").is_file():
            return candidate
    raise StoreError(f"no {spec.engine_id} model found in {folder}")


def adopt(folder: Path, spec: EngineSpec, move: bool = True) -> None:
    """Take over a model folder downloaded earlier (design 6.3 point 7). `folder` may be the model
    folder itself, contain it, or contain models/<engine_id>. Every file is verified by hash; the
    weights must match the pinned sha256. The files are then moved (or copied) into the data root.
    The folder's own manifest is never trusted: files are checked against the file set pinned in
    the registry (spec.files), or against the remote list when the spec pins none."""
    source = _find_model_folder(Path(folder), spec)
    files = _pinned_files(spec) or fetch_remote_manifest(spec)
    for rel in files:
        _safe_rel(rel)
    weights = [rel for rel, info in files.items() if rel.endswith(".safetensors")]
    if not weights or any(files[rel].get("sha256") != spec.weights_sha256 for rel in weights):
        raise StoreError("the weights listed for this folder are not the pinned ones")
    problems = {rel: reason for rel, info in files.items()
                if (reason := _check_file(source / rel, info, deep=True))}
    if problems:
        raise StoreError("files do not verify: " + ", ".join(f"{k} ({v})" for k, v in sorted(problems.items())))
    target = paths.model_dir(spec.engine_id)
    if source.resolve() != target.resolve():
        if target.exists() and any(target.iterdir()):
            raise StoreError(f"{target} already contains files; remove the engine first")
        target.mkdir(parents=True, exist_ok=True)
        for rel in files:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(source / rel), str(dest))
            else:
                shutil.copy2(source / rel, dest)
    _write_manifest(target, spec, files)
