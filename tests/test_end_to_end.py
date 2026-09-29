"""The command line from start to finish, as a user runs it, with the fake worker as engine."""
import json
import os
import subprocess
import sys

from owlocr import paths
from tests.conftest import FAKE_WORKER, REPO


def test_cli_end_to_end(owl_env, tmp_path):
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps({
        "engine_id": "unlimited_ocr", "python": sys.executable, "worker_script": str(FAKE_WORKER),
        "device": "cpu"}))
    out = tmp_path / "out"
    run = subprocess.run(
        [sys.executable, "-m", "owlocr.cli", "tests/fixtures/pages/01_letter_clean.png",
         "--formats", "md,txt", "--out", str(out)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120, env=dict(os.environ))
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines() == [str(out / "01_letter_clean.md"), str(out / "01_letter_clean.txt"),
                                       str(out / "01_letter_clean.owl.json")]
    assert (out / "01_letter_clean.md").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert (out / "01_letter_clean.txt").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert "01_letter_clean.png: page 1 (1/1) ocr" in run.stderr
    assert not (owl_env["home"] / "engine" / "worker.pid").exists()     # the worker was stopped
    log = (owl_env["home"] / "logs" / "engine.log").read_text(encoding="utf-8")
    assert "engine start" in log
