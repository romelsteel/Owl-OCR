import os
from pathlib import Path

import owlocr
from tests.conftest import REPO


def test_version():
    assert owlocr.__version__ == "0.1.0"


def test_every_test_gets_private_folders(owl_env, tmp_path):
    assert Path(os.environ["OWLOCR_HOME"]) == owl_env["home"]
    assert Path(os.environ["OWLOCR_CONFIG"]) == owl_env["config"]
    assert tmp_path in Path(os.environ["OWLOCR_HOME"]).parents


def test_license_is_mit():
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Tomáš Burcal" in text
