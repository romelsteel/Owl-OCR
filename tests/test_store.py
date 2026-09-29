"""Model store: readiness check and verification of files already on disk."""
import json

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, manifest_entries


def install_model(commit: str = SPEC.revision) -> None:
    folder = paths.model_dir("unlimited_ocr")
    folder.mkdir(parents=True, exist_ok=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    (folder / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": commit, "files": manifest_entries()}), encoding="utf-8")


def test_manifest_path(owl_env):
    assert store.manifest_path() == owl_env["home"] / "models" / "unlimited_ocr" / "manifest.json"


def test_not_ready_without_manifest():
    assert store.is_ready() is False
    assert store.verify() == {"manifest.json": "missing"}


def test_ready_and_verified():
    install_model()
    assert store.is_ready() is True
    assert store.is_ready(deep=True) is True
    assert store.verify() == {}


def test_wrong_revision_is_not_ready():
    install_model(commit="0" * 40)
    assert store.is_ready() is False
    assert "manifest.json" in store.verify()


def test_missing_or_truncated_file_is_not_ready():
    install_model()
    folder = paths.model_dir()
    (folder / "config.json").unlink()
    assert store.is_ready() is False
    assert store.verify() == {"config.json": "missing"}
    install_model()
    (folder / "model-00001-of-000001.safetensors").write_bytes(b"short")
    assert store.is_ready() is False
    assert store.verify()["model-00001-of-000001.safetensors"].startswith("size ")


def test_same_size_corruption_needs_deep_check():
    install_model()
    folder = paths.model_dir()
    weights = folder / "model-00001-of-000001.safetensors"
    weights.write_bytes(b"\0" * weights.stat().st_size)
    code = folder / "modeling_unlimitedocr.py"
    code.write_bytes(b"#" * code.stat().st_size)
    assert store.is_ready() is True                 # fast check: sizes only
    assert store.is_ready(deep=True) is False
    assert store.verify() == {"model-00001-of-000001.safetensors": "sha256 mismatch",
                              "modeling_unlimitedocr.py": "git sha1 mismatch"}


def test_spike_manifest_format_is_accepted():
    """The owner's existing download (spike/download_model.py) has no engine_id key."""
    install_model()
    data = json.loads(store.manifest_path().read_text(encoding="utf-8"))
    assert "engine_id" not in data
    assert store.is_ready()


def test_manifest_with_an_unsafe_key_is_not_trusted():
    install_model()
    data = json.loads(store.manifest_path().read_text(encoding="utf-8"))
    data["files"]["../../outside.py"] = {"size": 1, "sha256": None, "git_sha1": "0" * 40}
    store.manifest_path().write_text(json.dumps(data), encoding="utf-8")
    assert store.is_ready() is False
    assert store.verify() == {"manifest.json": "missing"}
