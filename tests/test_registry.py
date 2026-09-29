import dataclasses

import pytest

from owlocr.engine import registry


def test_unlimited_ocr_pins():
    spec = registry.get("unlimited_ocr")
    assert spec is registry.UNLIMITED_OCR
    assert spec.engine_id == "unlimited_ocr"
    assert spec.repo == "baidu/Unlimited-OCR"
    assert spec.revision == "07dea832e22aefee32ad281d4b80551282e1c168"
    assert len(spec.revision) == 40
    assert spec.ignore == ("assets/*", "wheel/*", "*.pdf", "*.gif", ".gitattributes")
    assert spec.weights_sha256 == "2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6"
    assert spec.modelscope_repo == "PaddlePaddle/Unlimited-OCR"
    assert (spec.torch, spec.torchvision, spec.transformers) == ("2.10.0", "0.25.0", "4.57.1")


def test_spec_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        registry.UNLIMITED_OCR.revision = "x"


def test_unknown_engine():
    with pytest.raises(KeyError):
        registry.get("tesseract")


def test_pinned_files_match_the_verified_download():
    """The pinned file set equals the owner's verified download (reads only its manifest.json)."""
    import fnmatch
    import json
    from pathlib import Path

    manifest = Path(__file__).resolve().parent.parent / "engine" / "models" / "unlimited_ocr" / "manifest.json"
    if not manifest.is_file():
        pytest.skip("no local model download")
    spec = registry.UNLIMITED_OCR
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["commit"] == spec.revision
    expected = {rel: (info["size"], info["sha256"], info["git_sha1"])
                for rel, info in data["files"].items()
                if not any(fnmatch.fnmatch(rel, pattern) for pattern in spec.ignore)}
    assert {rel: (size, sha256, git_sha1) for rel, size, sha256, git_sha1 in spec.files} == expected
    assert len(spec.files) == len(expected)
    weights = [f for f in spec.files if f[0].endswith(".safetensors")]
    assert weights == [("model-00001-of-000001.safetensors", 6672547120, spec.weights_sha256, None)]
