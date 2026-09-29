import pytest

from owlocr import paths, uninstall
from owlocr.engine import relocate


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    data = tmp_path / "data"
    paths.set_data_root(data)
    data.mkdir(parents=True)
    (data / relocate.ROOT_MARKER).write_text("x", encoding="utf-8")
    monkeypatch.setattr("owlocr.engine.client.sweep_stale_worker", lambda: None, raising=False)
    return tmp_path, data


def test_removes_our_items_and_empty_folders(dirs):
    tmp, data = dirs
    for d in ("engine/venv", "models/unlimited_ocr", "hf_home", "work/abc", "logs", "dictionaries"):
        (data / d).mkdir(parents=True, exist_ok=True)
    (data / "models" / "unlimited_ocr" / "x.bin").write_bytes(b"1")
    (data / "queue.json").write_text("{}", encoding="utf-8")
    (tmp / "config" / "settings.json").write_text("{}", encoding="utf-8")
    (tmp / "config" / "instance.json").write_text("{}", encoding="utf-8")
    assert uninstall.remove_all_data() == []
    assert not data.exists()
    assert not (tmp / "config").exists()


def test_keeps_foreign_files(dirs):
    tmp, data = dirs
    (data / "engine").mkdir(parents=True, exist_ok=True)
    (data / "my thesis.docx").write_text("precious", encoding="utf-8")
    assert uninstall.remove_all_data() == []
    assert (data / "my thesis.docx").read_text(encoding="utf-8") == "precious"
    assert not (data / "engine").exists()


def test_main_exit_code(dirs):
    assert uninstall.main() == 0


def test_refuses_items_directly_in_a_drive_root(dirs, monkeypatch):
    tmp, data = dirs
    (data / "models").mkdir(parents=True)
    monkeypatch.setattr("owlocr.engine.relocate.is_drive_root", lambda p: p == data)
    problems = uninstall.remove_all_data()
    assert len(problems) == 1 and "not deleted" in problems[0]
    assert (data / "models").is_dir()


def test_unmarked_foreign_root_is_not_deleted(dirs):
    tmp, data = dirs
    (data / relocate.ROOT_MARKER).unlink()
    (data / "work").mkdir()
    (data / "work" / "report.docx").write_text("mine", encoding="utf-8")
    problems = uninstall.remove_all_data()
    assert len(problems) == 1
    assert (data / "work" / "report.docx").read_text(encoding="utf-8") == "mine"
    assert not (tmp / "config" / "settings.json").exists()


def test_default_root_without_marker_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr("owlocr.engine.client.sweep_stale_worker", lambda: None, raising=False)
    default = tmp_path / "localappdata" / "OwlOCR"
    (default / "logs").mkdir(parents=True)
    assert paths.data_root() == default
    assert uninstall.remove_all_data() == []
    assert not default.exists()


def test_failed_item_keeps_marker_and_location(dirs, monkeypatch):
    """I-2: when an item cannot be deleted, the pointer to the leftover data must survive."""
    tmp, data = dirs
    for d in ("engine", "models", "logs"):
        (data / d).mkdir()
    (tmp / "config" / "settings.json").write_text("{}", encoding="utf-8")
    real_rmtree = uninstall.kit.rmtree

    def locked(target, *a, **k):
        if target.name == "models":
            raise PermissionError("file in use")
        return real_rmtree(target, *a, **k)

    monkeypatch.setattr(uninstall.kit, "rmtree", locked)
    problems = uninstall.remove_all_data()
    assert len(problems) == 1 and "models" in problems[0]
    assert (data / "models").is_dir()
    assert not (data / "engine").exists() and not (data / "logs").exists()
    assert (data / relocate.ROOT_MARKER).is_file()
    assert (tmp / "config" / "location.txt").is_file()
    assert paths.data_root() == data.resolve()
    assert not (tmp / "config" / "settings.json").exists()
    assert uninstall.main() == 1


def test_failed_sweep_alone_still_removes_the_pointer(dirs, monkeypatch):
    tmp, data = dirs

    def boom():
        raise RuntimeError("no")

    monkeypatch.setattr("owlocr.engine.client.sweep_stale_worker", boom)
    problems = uninstall.remove_all_data()
    assert len(problems) == 1 and problems[0].startswith("sweep")
    assert not data.exists()
    assert not (tmp / "config" / "location.txt").exists()
