"""Model store: adopting a model folder downloaded earlier ("I already have the engine")."""
import dataclasses
import json

import pytest

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, FakeRemote, git_blob_sha1, manifest_entries


def make_download(folder, with_manifest: bool = True):
    folder.mkdir(parents=True, exist_ok=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    if with_manifest:
        (folder / "manifest.json").write_text(json.dumps(
            {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")
    return folder


def test_adopt_moves_the_model_folder(tmp_path):
    source = make_download(tmp_path / "old" / "unlimited_ocr")
    store.adopt(source, SPEC)
    assert store.is_ready(deep=True)
    assert not (source / "config.json").exists()


def test_adopt_parent_folder_with_models_subfolder(tmp_path):
    make_download(tmp_path / "old_engine" / "models" / "unlimited_ocr")
    store.adopt(tmp_path / "old_engine", SPEC, move=False)
    assert store.is_ready(deep=True)
    assert (tmp_path / "old_engine" / "models" / "unlimited_ocr" / "config.json").exists()


def test_adopt_without_pinned_files_uses_the_remote_list(tmp_path, monkeypatch):
    remote = FakeRemote()
    monkeypatch.setattr(store, "_open", remote.open)
    source = make_download(tmp_path / "unlimited_ocr", with_manifest=False)
    store.adopt(source, dataclasses.replace(SPEC, files=()))
    assert store.is_ready(deep=True)
    assert "/api/models/" in remote.requests[0][0]


def test_adopt_with_pinned_files_needs_no_network(tmp_path, monkeypatch):
    remote = FakeRemote()
    monkeypatch.setattr(store, "_open", remote.open)
    source = make_download(tmp_path / "unlimited_ocr", with_manifest=False)
    store.adopt(source, SPEC)
    assert store.is_ready(deep=True)
    assert remote.requests == []


@pytest.mark.parametrize("key", ["../evil.py", "..\\..\\evil.py", "sub/../../evil.py",
                                 "C:\\evil.py", "C:evil.py", "/evil.py", "\\\\server\\share\\evil.py"])
def test_adopt_rejects_a_traversal_key(tmp_path, monkeypatch, key):
    remote = FakeRemote()
    remote.extra_entries.append({"type": "file", "path": key, "size": 1, "oid": "e1"})
    monkeypatch.setattr(store, "_open", remote.open)
    source = make_download(tmp_path / "unlimited_ocr")
    with pytest.raises(store.StoreError, match="unsafe"):
        store.adopt(source, dataclasses.replace(SPEC, files=()))
    pinned = dataclasses.replace(SPEC, files=SPEC.files + ((key, 1, None, "e1"),))
    with pytest.raises(store.StoreError, match="unsafe"):
        store.adopt(source, pinned)
    assert not store.manifest_path().exists()


def test_adopt_ignores_the_folders_own_manifest(tmp_path):
    """Code files run with trust_remote_code: a folder whose manifest agrees with a changed
    modeling_*.py must still be rejected, because only the pinned set counts."""
    source = make_download(tmp_path / "unlimited_ocr")
    evil = b"import os  # changed\n" * 7
    (source / "modeling_unlimitedocr.py").write_bytes(evil)
    entries = manifest_entries()
    entries["modeling_unlimitedocr.py"] = {"size": len(evil), "sha256": None, "git_sha1": git_blob_sha1(evil)}
    (source / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": entries}), encoding="utf-8")
    with pytest.raises(store.StoreError, match="modeling_unlimitedocr.py"):
        store.adopt(source, SPEC)
    assert not store.is_ready()


def test_adopt_rejects_a_folder_missing_a_pinned_file(tmp_path):
    source = make_download(tmp_path / "unlimited_ocr")
    (source / "modeling_unlimitedocr.py").unlink()
    entries = manifest_entries()
    del entries["modeling_unlimitedocr.py"]
    (source / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": entries}), encoding="utf-8")
    with pytest.raises(store.StoreError, match="modeling_unlimitedocr.py"):
        store.adopt(source, SPEC)
    assert not store.is_ready()


def test_adopt_rejects_other_weights(tmp_path):
    source = make_download(tmp_path / "unlimited_ocr")
    other = dataclasses.replace(SPEC, weights_sha256="0" * 64)
    with pytest.raises(store.StoreError, match="weights"):
        store.adopt(source, other)
    assert not store.is_ready()


def test_adopt_rejects_corrupt_files(tmp_path):
    source = make_download(tmp_path / "unlimited_ocr")
    (source / "config.json").write_bytes(b"{" + b" " * (len(FILES["config.json"]) - 1))
    with pytest.raises(store.StoreError, match="config.json"):
        store.adopt(source, SPEC)
    assert (source / "config.json").exists()


def test_adopt_folder_without_model(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(store.StoreError):
        store.adopt(tmp_path / "empty", SPEC)


def test_adopt_in_place(tmp_path):
    make_download(paths.model_dir(), with_manifest=False)
    (paths.model_dir() / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")
    store.adopt(paths.model_dir(), SPEC)
    assert store.is_ready(deep=True)


def test_adopt_refuses_to_mix_with_existing_files(tmp_path):
    paths.model_dir().mkdir(parents=True)
    (paths.model_dir() / "stray.txt").write_text("x")
    source = make_download(tmp_path / "unlimited_ocr")
    with pytest.raises(store.StoreError, match="already contains"):
        store.adopt(source, SPEC)
