"""Checks before a public release (plan D, task 31). Run with OWLOCR_RELEASE_CHECK=1."""
import os
import re
import subprocess
import sys

import pytest

from owlocr import __version__
from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import build  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("OWLOCR_RELEASE_CHECK") != "1",
                                reason="release check: set OWLOCR_RELEASE_CHECK=1")
DIST = REPO / "dist"
ARTEFACTS = (f"OwlOCR-{__version__}-setup.exe", f"OwlOCR-{__version__}-portable-win64.zip")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def test_readme_has_no_missing_images():
    """Owner decision 2026-09-29: the README ships without screenshots."""
    for name in ("README.md", "README.cs.md"):
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", (REPO / name).read_text(encoding="utf-8")):
            assert (REPO / target).is_file(), (name, target)


def test_no_local_paths_or_user_name_in_tracked_files():
    done = subprocess.run([sys.executable, str(REPO / "packaging" / "scrub_local_paths.py"), "--check"],
                          cwd=REPO, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_nothing_from_samples_is_tracked():
    assert [f for f in tracked() if f.startswith("samples/")] == []


def test_cpu_decision_is_recorded():
    record = (REPO / "docs" / "research" / "2026-09-28-cpu-acceptance.md").read_text(encoding="utf-8")
    assert "Result: **" in record


def test_release_notes_and_version():
    notes = (REPO / "docs" / f"release-notes-{__version__}.md").read_text(encoding="utf-8")
    assert f"Owl OCR {__version__}" in notes


def test_artefacts_exist_are_small_enough_and_match_the_sums():
    sums = (DIST / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    for name in ARTEFACTS:
        path = DIST / name
        assert path.is_file(), name
        assert path.stat().st_size < 2 * 1024**3, name             # GitHub's per-file limit
        assert any(line.endswith("  " + name) for line in sums), name


def test_no_user_name_in_artefacts():
    assert build.user_name_hits(DIST / "OwlOCR", os.environ["USERNAME"]) == []
