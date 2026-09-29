import shutil

import pytest

from owlocr import paths
from owlocr.engine import relocate
from owlocr.engine.relocate import LocationError


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME", raising=False)
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    return tmp_path


def fill(root):
    (root / "engine" / "venv").mkdir(parents=True)
    (root / "engine" / "venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (root / "models" / "unlimited_ocr").mkdir(parents=True)
    (root / "models" / "unlimited_ocr" / "config.json").write_text("{}", encoding="utf-8")
    (root / "queue.json").write_text('{"jobs": []}', encoding="utf-8")
    (root / "private.txt").write_text("not ours", encoding="utf-8")


def test_validate_rejects_relative_and_files(config):
    with pytest.raises(LocationError, match="not_absolute"):
        relocate.validate_location(relocate.Path("relative\\folder"))
    f = config / "a_file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(LocationError, match="not_a_folder"):
        relocate.validate_location(f)
    with pytest.raises(LocationError, match="empty"):
        relocate.validate_location(relocate.Path(" "))


def test_validate_creates_folder(config):
    target = config / "new" / "OwlOCR data"
    assert relocate.validate_location(target) == target.resolve()
    assert target.is_dir()


def test_choose_location_without_data_just_points_there(config):
    target = config / "D_drive" / "OwlOCR"
    relocate.choose_location(target)
    assert paths.data_root().resolve() == target.resolve()


def test_move_data_root_moves_only_our_items(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    new = config / "new"
    relocate.move_data_root(new)
    assert paths.data_root().resolve() == new.resolve()
    assert (new / "engine" / "venv" / "pyvenv.cfg").exists()
    assert (new / "models" / "unlimited_ocr" / "config.json").exists()
    assert (new / "queue.json").exists()
    assert (old / "private.txt").exists() and not (new / "private.txt").exists()
    assert not (old / "engine").exists()


def test_choose_location_moves_existing_data(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    relocate.choose_location(config / "new")
    assert (config / "new" / "models").is_dir()


def test_move_refuses_nested_and_existing(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    with pytest.raises(LocationError, match="nested"):
        relocate.move_data_root(old / "inner")
    clash = config / "clash"
    (clash / "models").mkdir(parents=True)
    (clash / relocate.ROOT_MARKER).write_text("x", encoding="utf-8")
    with pytest.raises(LocationError, match="exists"):
        relocate.move_data_root(clash)
    assert (old / "models").is_dir()


def test_move_refused_when_env_override(config, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(config / "home"))
    with pytest.raises(LocationError, match="env_override"):
        relocate.move_data_root(config / "elsewhere")


def _force_copy(monkeypatch):
    def no_rename(a, b):
        raise OSError("different drive")
    monkeypatch.setattr(relocate.os, "rename", no_rename)


def test_failed_copy_leaves_sources_and_no_partial_copies(config, monkeypatch):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    _force_copy(monkeypatch)
    real_copy2 = shutil.copy2

    def flaky(src, dst, **kw):
        if str(src).endswith("queue.json"):
            relocate.Path(dst).write_text("partial", encoding="utf-8")
            raise OSError("disk full")
        return real_copy2(src, dst, **kw)

    monkeypatch.setattr(relocate.shutil, "copy2", flaky)
    new = config / "new"
    with pytest.raises(LocationError, match="move_failed"):
        relocate.move_data_root(new)
    assert (old / "engine" / "venv" / "pyvenv.cfg").exists()
    assert (old / "models" / "unlimited_ocr" / "config.json").exists()
    assert (old / "queue.json").exists()
    assert not (new / "engine").exists() and not (new / "models").exists()
    assert not (new / "queue.json").exists()
    assert paths.data_root().resolve() == old.resolve()


def test_source_delete_failure_keeps_the_complete_copy(config, monkeypatch):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    _force_copy(monkeypatch)

    def broken(path):
        next(relocate.Path(path).rglob("*.*")).unlink()   # deletes one file, then fails
        raise OSError("file in use")

    monkeypatch.setattr(relocate.kit, "rmtree", broken)
    new = config / "new"
    assert relocate.move_data_root(new) == new.resolve()
    assert paths.data_root().resolve() == new.resolve()
    assert (new / "engine" / "venv" / "pyvenv.cfg").read_text(encoding="utf-8") == "home = x\n"
    assert (new / "models" / "unlimited_ocr" / "config.json").exists()
    assert (new / "queue.json").exists()
    assert len(relocate.last_leftovers) == 2


def test_drive_root_uses_subfolder(config, monkeypatch):
    fake_root = config / "fakedrive"
    fake_root.mkdir()
    monkeypatch.setattr(relocate, "is_drive_root", lambda p: p == fake_root.resolve())
    assert relocate.choose_location(fake_root) == (fake_root / "OwlOCR").resolve()
    assert paths.data_root().resolve() == (fake_root / "OwlOCR").resolve()


def test_foreign_folder_uses_subfolder(config):
    other = config / "other"
    other.mkdir()
    (other / "thesis.docx").write_text("x", encoding="utf-8")
    assert relocate.choose_location(other) == (other / "OwlOCR").resolve()


def test_existing_root_and_empty_folder_are_used_as_is(config):
    ours = config / "ours"
    fill(ours)
    (ours / relocate.ROOT_MARKER).write_text("x", encoding="utf-8")
    assert relocate.effective_root(ours) == ours.resolve()
    empty = config / "empty"
    empty.mkdir()
    assert relocate.effective_root(empty) == empty.resolve()


def test_move_into_foreign_folder_uses_subfolder(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    foreign = config / "foreign"
    foreign.mkdir()
    (foreign / "thesis.docx").write_text("x", encoding="utf-8")
    assert relocate.move_data_root(foreign) == (foreign / "OwlOCR").resolve()
    assert (foreign / "OwlOCR" / "models").is_dir() and not (foreign / "models").exists()


def test_free_bytes_of_missing_folder_uses_parent(config):
    assert relocate.free_bytes(config / "does" / "not" / "exist") > 0


def test_foreign_folder_with_generic_names_gets_subfolder(config):
    projects = config / "Projects"
    (projects / "work").mkdir(parents=True)
    (projects / "work" / "report.docx").write_text("mine", encoding="utf-8")
    (projects / "notes.txt").write_text("mine", encoding="utf-8")
    assert relocate.choose_location(projects) == (projects / "OwlOCR").resolve()
    assert (projects / "OwlOCR" / relocate.ROOT_MARKER).is_file()
    assert not (projects / relocate.ROOT_MARKER).exists()


def test_move_writes_marker_and_foreign_generic_folder_is_not_used(config):
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    foreign = config / "foreign"
    (foreign / "logs").mkdir(parents=True)
    (foreign / "logs" / "mine.txt").write_text("mine", encoding="utf-8")
    dest = relocate.move_data_root(foreign)
    assert dest == (foreign / "OwlOCR").resolve()
    assert (dest / relocate.ROOT_MARKER).is_file()
    assert (foreign / "logs" / "mine.txt").exists()


def test_default_root_counts_without_marker(config):
    default = relocate.default_root()
    default.mkdir(parents=True)
    (default / "queue.json").write_text("{}", encoding="utf-8")
    assert relocate.effective_root(default) == default.resolve()


def test_drive_root_is_not_probed(config, monkeypatch):
    fake_root = config / "fakedrive"
    fake_root.mkdir()
    monkeypatch.setattr(relocate, "is_drive_root", lambda p: p == fake_root.resolve())
    import tempfile
    real = tempfile.mkstemp
    probed = []

    def spy(*a, **kw):
        probed.append(kw.get("dir"))
        return real(*a, **kw)

    monkeypatch.setattr(relocate.tempfile, "mkstemp", spy)
    relocate.effective_root(fake_root)
    assert fake_root not in probed and fake_root.resolve() not in probed


def test_refused_choose_leaves_no_new_folders(config, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(config / "home"))
    with pytest.raises(LocationError):
        relocate.choose_location(config / "brand" / "new")
    assert not (config / "brand").exists()
    monkeypatch.delenv("OWLOCR_HOME")
    old = config / "old"
    relocate.paths.set_data_root(old)
    fill(old)
    with pytest.raises(LocationError, match="nested"):
        relocate.move_data_root(old / "deeper" / "still")
    assert not (old / "deeper").exists()
