import importlib.util
import json
import sys
from pathlib import Path

from owlocr import paths
from owlocr.engine.client import default_engine
from tests.conftest import REPO
from tests.store_fakes import FILES, SPEC, manifest_entries


def load_script():
    spec = importlib.util.spec_from_file_location("dev_engine", REPO / "scripts" / "dev_engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_model(root: Path) -> None:
    folder = root / "models" / "unlimited_ocr"
    folder.mkdir(parents=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    (folder / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")


def test_writes_install_json_that_default_engine_accepts(tmp_path, monkeypatch):
    root = tmp_path / "devroot"
    fake_model(root)
    assert load_script().main(["--python", sys.executable, "--data-root", str(root)]) == 0
    data = json.loads((root / "engine" / "install.json").read_text(encoding="utf-8"))
    assert data["python"] == sys.executable
    assert data["revision"] == SPEC.revision and data["device"] == "cuda" and data["dtype"] == "bfloat16"
    monkeypatch.setenv("OWLOCR_HOME", str(root))
    engine = default_engine()
    assert engine.python == Path(sys.executable)
    assert engine.worker_script == REPO / "worker" / "owl_worker.py"
    assert engine.model_dir == root / "models" / "unlimited_ocr"
    assert engine.log_file == paths.logs_dir() / "engine.log"


def test_refuses_without_model_or_python(tmp_path):
    script = load_script()
    assert script.main(["--python", sys.executable, "--data-root", str(tmp_path / "empty")]) == 1
    fake_model(tmp_path / "root")
    assert script.main(["--python", str(tmp_path / "none.exe"), "--data-root", str(tmp_path / "root")]) == 1
    assert not (tmp_path / "root" / "engine" / "install.json").exists()
