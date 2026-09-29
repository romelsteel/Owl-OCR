"""Pins the uv release that the engine installer downloads: writes owlocr/engine/pins.json.

    py -3.11 packaging\\pin_uv.py                 latest uv release
    py -3.11 packaging\\pin_uv.py 0.12.19         a given release
    py -3.11 packaging\\pin_uv.py --verify        check the pinned archive and the uv flags we use

Without --verify only small text files are fetched (release metadata and the .sha256 file).
--verify downloads the pinned uv archive (about 18 MB) into a temporary folder, checks its sha256,
and runs `uv --help` commands to confirm the command-line flags bootstrap uses still exist.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PINS = REPO / "owlocr" / "engine" / "pins.json"
ASSET = "uv-x86_64-pc-windows-msvc.zip"
API_LATEST = "https://api.github.com/repos/astral-sh/uv/releases/latest"
API_TAG = "https://api.github.com/repos/astral-sh/uv/releases/tags/{tag}"
CREATE_NO_WINDOW = 0x08000000
# Flags used by owlocr/engine/stages.py; --verify fails if a pinned uv lacks any of them.
REQUIRED_FLAGS = {
    ("python", "install", "--help"): ("--no-bin", "--no-registry"),
    ("venv", "--help"): ("--python", "--no-project"),
    ("pip", "install", "--help"): ("--python", "--index-url", "--requirement"),
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "owl-ocr-pin-uv",
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def asset_url(version: str) -> str:
    return f"https://github.com/astral-sh/uv/releases/download/{version}/{ASSET}"


def parse_sha256_file(text: str) -> str:
    token = text.strip().split()[0].lower() if text.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError(f"not a sha256 file: {text[:80]!r}")
    return token


def digest_from_release(release: dict) -> str | None:
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET and str(asset.get("digest", "")).startswith("sha256:"):
            return asset["digest"].split(":", 1)[1].lower()
    return None


def build_pins(version: str, sha256: str) -> dict:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"unexpected uv version {version!r}")
    return {"uv": {"version": version, "url": asset_url(version), "sha256": sha256}}


def pin(version: str | None, out: Path = PINS) -> dict:
    release = json.loads(_get(API_TAG.format(tag=version) if version else API_LATEST))
    version = release["tag_name"]
    sha = parse_sha256_file(_get(asset_url(version) + ".sha256").decode("utf-8"))
    api_digest = digest_from_release(release)
    if api_digest is not None and api_digest != sha:
        raise ValueError(f"sha256 of {ASSET} differs between the .sha256 file and the release API")
    pins = build_pins(version, sha)
    out.write_text(json.dumps(pins, indent=1) + "\n", encoding="utf-8")
    return pins


def verify(pins_file: Path = PINS) -> list[str]:
    """Returns problems; empty when the pinned uv matches and supports every flag we use."""
    pins = json.loads(pins_file.read_text(encoding="utf-8"))["uv"]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="owl-uv-") as tmp:
        archive = Path(tmp) / ASSET
        archive.write_bytes(_get(pins["url"]))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != pins["sha256"]:
            return [f"sha256 mismatch: {digest} != {pins['sha256']}"]
        with zipfile.ZipFile(archive) as zf:
            member = next(n for n in zf.namelist() if n.replace("\\", "/").rsplit("/", 1)[-1] == "uv.exe")
            exe = Path(tmp) / "uv.exe"
            exe.write_bytes(zf.read(member))
        for args, flags in REQUIRED_FLAGS.items():
            done = subprocess.run([str(exe), *args], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", creationflags=CREATE_NO_WINDOW, timeout=60)
            for flag in flags:
                if flag not in done.stdout:
                    problems.append(f"`uv {' '.join(args[:-1])}` has no {flag}")
    return problems


def main(argv: list[str]) -> int:
    if "--verify" in argv:
        problems = verify()
        for line in problems:
            print("PROBLEM:", line)
        print("uv pin OK" if not problems else "uv pin NOT OK")
        return 0 if not problems else 1
    version = argv[0] if argv else None
    pins = pin(version)
    print(json.dumps(pins, indent=1))
    print(f"written to {PINS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
