"""Model store: remote file list and resumable download against a fake server."""
import dataclasses
import threading

import pytest

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, FakeRemote, manifest_entries

WEIGHTS = "model-00001-of-000001.safetensors"


@pytest.fixture
def remote(monkeypatch):
    fake = FakeRemote()
    monkeypatch.setattr(store, "_open", fake.open)
    return fake


def test_fetch_remote_manifest(remote):
    files = store.fetch_remote_manifest(SPEC)
    assert files == manifest_entries()
    assert "assets/logo.png" not in files and ".gitattributes" not in files
    assert remote.requests[0][0] == (
        "https://huggingface.co/api/models/baidu/Unlimited-OCR/tree/"
        "07dea832e22aefee32ad281d4b80551282e1c168?recursive=true")


def test_fetch_remote_manifest_offline(remote):
    remote.down_hosts.add("huggingface.co")
    with pytest.raises(store.StoreError):
        store.fetch_remote_manifest(SPEC)


def test_download_everything(remote):
    progress = []
    store.download(SPEC, on_progress=lambda done, total: progress.append((done, total)))
    folder = paths.model_dir()
    for rel, data in FILES.items():
        assert (folder / rel).read_bytes() == data
    total = sum(len(d) for d in FILES.values())
    assert progress[-1] == (total, total)
    assert store.is_ready(deep=True)
    assert not list(folder.glob("*.part"))
    url, start = remote.file_requests(WEIGHTS)[0]
    assert url == f"https://huggingface.co/baidu/Unlimited-OCR/resolve/{SPEC.revision}/{WEIGHTS}"


def test_second_download_does_nothing(remote):
    store.download(SPEC)
    remote.requests.clear()
    store.download(SPEC)
    assert remote.requests == []


def test_resume_partial_file(remote):
    folder = paths.model_dir()
    folder.mkdir(parents=True)
    (folder / (WEIGHTS + ".part")).write_bytes(FILES[WEIGHTS][:1000])
    progress = []
    store.download(SPEC, on_progress=lambda done, total: progress.append(done))
    assert remote.file_requests(WEIGHTS) == [(remote.file_requests(WEIGHTS)[0][0], 1000)]
    assert (folder / WEIGHTS).read_bytes() == FILES[WEIGHTS]
    assert progress[-1] == sum(len(d) for d in FILES.values())


def test_server_that_ignores_range(remote):
    remote.ignore_range = True
    folder = paths.model_dir()
    folder.mkdir(parents=True)
    (folder / (WEIGHTS + ".part")).write_bytes(FILES[WEIGHTS][:1000])
    store.download(SPEC)
    assert (folder / WEIGHTS).read_bytes() == FILES[WEIGHTS]


def test_falls_back_to_modelscope(remote):
    remote.corrupt.add(("huggingface.co", WEIGHTS))
    store.download(SPEC)
    urls = [u for u, _ in remote.file_requests(WEIGHTS)]
    assert urls[1] == f"https://www.modelscope.cn/models/PaddlePaddle/Unlimited-OCR/resolve/master/{WEIGHTS}"
    assert store.is_ready(deep=True)


def test_every_source_bad(remote):
    remote.corrupt.add(("huggingface.co", WEIGHTS))
    remote.corrupt.add(("www.modelscope.cn", WEIGHTS))
    with pytest.raises(store.StoreError):
        store.download(SPEC)
    assert not store.manifest_path().exists()
    assert not (paths.model_dir() / WEIGHTS).exists()


def test_cancel(remote):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(store.StoreError, match="cancelled"):
        store.download(SPEC, cancel=cancel)
    assert not store.manifest_path().exists()


def test_dropped_connection_keeps_the_partial_file(remote):
    """urllib returns b"" (no error) when the connection closes early: the .part must survive and
    the next request must continue from where the first one stopped."""
    remote.truncate_once[WEIGHTS] = 1000
    remote.down_hosts.add("www.modelscope.cn")
    with pytest.raises(store.StoreError, match="cannot download"):
        store.download(SPEC)
    assert (paths.model_dir() / (WEIGHTS + ".part")).read_bytes() == FILES[WEIGHTS][:1000]
    remote.down_hosts.clear()
    remote.requests.clear()
    store.download(SPEC)
    assert [s for _, s in remote.file_requests(WEIGHTS)] == [1000]
    assert store.is_ready(deep=True)


def test_dropped_connection_resumes_from_the_next_source(remote):
    remote.truncate_once[WEIGHTS] = 1000
    progress = []
    store.download(SPEC, on_progress=lambda done, total: progress.append(done))
    requests = remote.file_requests(WEIGHTS)
    assert [s for _, s in requests] == [0, 1000]
    assert "modelscope" in requests[1][0]
    assert (paths.model_dir() / WEIGHTS).read_bytes() == FILES[WEIGHTS]
    assert progress[-1] == sum(len(d) for d in FILES.values())
    assert store.is_ready(deep=True)


def test_remote_list_with_an_unsafe_path_is_refused(remote):
    remote.extra_entries.append({"type": "file", "path": "../../evil.py", "size": 1, "oid": "e1"})
    with pytest.raises(store.StoreError, match="unsafe"):
        store.download(dataclasses.replace(SPEC, files=()))     # no pinned set: the remote list is used
    assert not store.manifest_path().exists()


def test_download_uses_the_pinned_files_when_hugging_face_is_down(remote):
    """The file list comes from the registry, so ModelScope alone is enough (design 6.3.5)."""
    remote.down_hosts.add("huggingface.co")
    store.download(SPEC)
    assert not [u for u, _ in remote.requests if "/api/models/" in u]
    assert store.is_ready(deep=True)
    for rel, data in FILES.items():
        assert (paths.model_dir() / rel).read_bytes() == data


def test_remote_list_of_the_wrong_shape_is_a_store_error(remote, monkeypatch):
    monkeypatch.setattr(remote, "tree", lambda: {"error": "not a list"})
    with pytest.raises(store.StoreError):
        store.fetch_remote_manifest(SPEC)
