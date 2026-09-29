r"""Removes the owner's local paths and Windows user name from tracked text files before the
repository becomes public (design 12, "Going public").

    py -3.11 packaging\scrub_local_paths.py           rewrite the files, list what changed
    py -3.11 packaging\scrub_local_paths.py --check   only list; exit code 1 when something is found

The user name is read from the environment (USERNAME), so it never has to be written into this
public file. C:\Users\<name>\ becomes %USERPROFILE%\ and a path mangled as C--Users-<name>-
(Claude's project folders) becomes C--Users-<user>-.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip", ".exe", ".dll", ".safetensors", ".bin",
                   ".tif", ".tiff", ".webp", ".bmp", ".gif", ".docx"}


def patterns(user: str) -> list[tuple[re.Pattern, str]]:
    name = re.escape(user)
    return [
        (re.compile(rf"[A-Za-z]:\\\\Users\\\\{name}\\\\", re.I), r"%USERPROFILE%\\\\"),   # escaped in JSON/Python
        (re.compile(rf"[A-Za-z]:\\Users\\{name}(?=[\\/]|$|[^\w.-])", re.I), r"%USERPROFILE%"),
        (re.compile(rf"[A-Za-z]:/Users/{name}(?=[\\/]|$|[^\w.-])", re.I), "%USERPROFILE%"),
        (re.compile(rf"[A-Za-z]--Users-{name}-", re.I), "C--Users-<user>-"),
    ]


def scrub_text(text: str, user: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in patterns(user):
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [REPO / name for name in out.decode("utf-8").split("\0") if name]


def main(argv: list[str]) -> int:
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        print("USERNAME is not set")
        return 2
    check_only = "--check" in argv
    found = 0
    for path in tracked_files():
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new, count = scrub_text(text, user)
        if count:
            found += count
            print(f"{path.relative_to(REPO)}: {count}")
            if not check_only:
                path.write_bytes(new.encode("utf-8"))
    print(f"{found} occurrence(s) {'found' if check_only else 'replaced'}")
    return 1 if (check_only and found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
