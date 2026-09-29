"""THROWAWAY spike: download Unlimited-OCR exactly once, verify, mark ready.

Usage:  spike\\.venv\\Scripts\\python.exe spike\\download_model.py [--check] [--deep]

  (no flag)  download if not ready, verify every file, write manifest.json LAST
  --check    only report whether the model is ready (fast: sizes only, no network)
  --deep     with --check: also re-hash every file

Does not touch the GPU and never loads the model.
"""
import os
import sys
import json
import time
import shutil
import hashlib
import pathlib
import fnmatch

sys.stdout.reconfigure(encoding="utf-8")

# NOT %LOCALAPPDATA%: tools started from the Claude desktop app (a packaged Windows app)
# get AppData writes redirected into Claude's private folder, where a normally started
# program never looks. The project's engine/ folder is a real path and is ignored by git.
APP = pathlib.Path(os.environ.get("OWLOCR_HOME") or pathlib.Path(__file__).resolve().parent.parent / "engine")
MODEL_DIR = APP / "models" / "unlimited_ocr"
MANIFEST = MODEL_DIR / "manifest.json"

# HF reads these at import time -> set BEFORE importing huggingface_hub.
os.environ["HF_HOME"] = str(APP / "hf_home")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # plain HTTPS; Xet has a history of stalls on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

REPO = "baidu/Unlimited-OCR"
COMMIT = "07dea832e22aefee32ad281d4b80551282e1c168"
IGNORE = ["assets/*", "wheel/*", "*.pdf", "*.gif", ".gitattributes"]
MIN_FREE_BYTES = 10 * 1024**3


def _ignored(path: str) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in IGNORE)


def sha256_of(p: pathlib.Path, bufsize: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1_of(p: pathlib.Path) -> str:
    """Hash the way git does, so small (non-LFS) files can be checked against blob_id."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % p.stat().st_size)
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(rel: str, info: dict) -> str | None:
    """Returns None if the file is good, else a short reason."""
    p = MODEL_DIR / rel
    if not p.is_file():
        return "missing"
    if p.stat().st_size != info["size"]:
        return f"size {p.stat().st_size} != {info['size']}"
    if info.get("sha256"):
        if sha256_of(p) != info["sha256"]:
            return "sha256 mismatch"
    elif info.get("git_sha1"):
        if git_blob_sha1_of(p) != info["git_sha1"]:
            return "git sha1 mismatch"
    return None


def is_ready(deep: bool = False) -> bool:
    if not MANIFEST.exists():
        return False
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if m.get("commit") != COMMIT:
        return False
    for rel, info in m["files"].items():
        p = MODEL_DIR / rel
        if not p.is_file() or p.stat().st_size != info["size"]:
            return False
        if deep and verify_file(rel, info) is not None:
            return False
    return True


def fetch_remote_manifest() -> dict:
    from huggingface_hub import HfApi

    files = {}
    for f in HfApi().list_repo_tree(REPO, revision=COMMIT, recursive=True):
        size = getattr(f, "size", None)
        if size is None or _ignored(f.path):  # folders have no size
            continue
        lfs = getattr(f, "lfs", None)
        files[f.path] = {
            "size": lfs.size if lfs else size,
            "sha256": lfs.sha256 if lfs else None,
            "git_sha1": None if lfs else f.blob_id,
        }
    return files


def main() -> int:
    if "--check" in sys.argv:
        ok = is_ready(deep="--deep" in sys.argv)
        print("READY" if ok else "NOT READY", "-", MODEL_DIR)
        return 0 if ok else 1

    if is_ready():
        print("Model already downloaded and verified, nothing to do:", MODEL_DIR)
        return 0

    APP.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(APP).free
    if free < MIN_FREE_BYTES:
        print(f"Not enough free space: {free / 1024**3:.1f} GB, need 10 GB")
        return 2

    from huggingface_hub import snapshot_download
    import huggingface_hub

    print("huggingface_hub", huggingface_hub.__version__, "| xet disabled:", os.environ["HF_HUB_DISABLE_XET"])
    files = fetch_remote_manifest()
    total = sum(i["size"] for i in files.values())
    print(f"{len(files)} files, {total / 1e9:.2f} GB -> {MODEL_DIR}")

    t0 = time.time()
    snapshot_download(REPO, revision=COMMIT, local_dir=str(MODEL_DIR), ignore_patterns=IGNORE, max_workers=4)
    dl_s = time.time() - t0
    print(f"download finished in {dl_s:.0f} s (~{total / 1e6 / max(dl_s, 1):.0f} MB/s average)")

    t0 = time.time()
    bad = {rel: r for rel, i in files.items() if (r := verify_file(rel, i))}
    if bad:
        print("verification FAILED for:", bad, "-> re-downloading those files once")
        for rel in bad:
            (MODEL_DIR / rel).unlink(missing_ok=True)
        snapshot_download(REPO, revision=COMMIT, local_dir=str(MODEL_DIR), allow_patterns=list(bad), force_download=True)
        still_bad = {rel: r for rel in bad if (r := verify_file(rel, files[rel]))}
        if still_bad:
            print("STILL corrupt, giving up:", still_bad)
            return 3
    print(f"all {len(files)} files verified in {time.time() - t0:.0f} s")

    # The ready marker is written last, so an interrupted run is never mistaken for a finished one.
    MANIFEST.write_text(
        json.dumps({"repo": REPO, "commit": COMMIT, "download_seconds": round(dl_s), "files": files}, indent=1),
        encoding="utf-8",
    )
    print("READY -", MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
