import sys
from pathlib import Path

from owlocr import paths


def test_env_overrides(owl_env):
    assert paths.config_dir() == owl_env["config"]
    assert paths.data_root() == owl_env["home"]


def test_config_dir_is_created(tmp_path, monkeypatch):
    target = tmp_path / "new" / "config"
    monkeypatch.setenv("OWLOCR_CONFIG", str(target))
    assert paths.config_dir() == target
    assert target.is_dir()


def test_location_txt_used_when_no_owlocr_home(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME")
    chosen = tmp_path / "D_drive" / "OwlData"
    paths.set_data_root(chosen)
    assert (paths.config_dir() / "location.txt").read_text(encoding="utf-8").strip() == str(chosen.resolve())
    assert paths.data_root() == chosen.resolve()


def test_default_data_root_is_localappdata(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.data_root() == tmp_path / "local" / "OwlOCR"


def test_default_config_dir_is_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_CONFIG")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.config_dir() == tmp_path / "roaming" / "OwlOCR"


def test_owlocr_home_wins_over_location_txt(owl_env, tmp_path):
    paths.set_data_root(tmp_path / "elsewhere")
    assert paths.data_root() == owl_env["home"]


def test_derived_folders(owl_env):
    home = owl_env["home"]
    assert paths.engine_dir() == home / "engine"
    assert paths.engine_python() == home / "engine" / "venv" / "Scripts" / "python.exe"
    assert paths.worker_dir() == home / "engine" / "worker"
    assert paths.models_dir() == home / "models"
    assert paths.model_dir() == home / "models" / "unlimited_ocr"
    assert paths.model_dir("other") == home / "models" / "other"
    assert paths.hf_home() == home / "hf_home"
    assert paths.queue_file() == home / "queue.json"
    assert paths.settings_file() == owl_env["config"] / "settings.json"


def test_work_and_logs_dirs_are_created(owl_env):
    work = paths.work_dir("job42")
    assert work == owl_env["home"] / "work" / "job42" and work.is_dir()
    logs = paths.logs_dir()
    assert logs == owl_env["home"] / "logs" and logs.is_dir()


def test_resource_path_dev_and_frozen(tmp_path, monkeypatch):
    repo = Path(paths.__file__).resolve().parent.parent
    assert paths.resource_path("worker/owl_worker.py") == repo / "worker" / "owl_worker.py"
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("worker/owl_worker.py") == tmp_path / "worker" / "owl_worker.py"


def test_atomic_write_text(tmp_path):
    target = tmp_path / "sub" / "file.json"
    paths.atomic_write_text(target, "Příliš žluťoučký kůň\n")
    assert target.read_bytes() == "Příliš žluťoučký kůň\n".encode("utf-8")
    paths.atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert [p.name for p in target.parent.iterdir()] == ["file.json"]


def test_unique_path(tmp_path):
    first = tmp_path / "book.md"
    assert paths.unique_path(first) == first
    first.write_text("x")
    assert paths.unique_path(first) == tmp_path / "book_1.md"
    (tmp_path / "book_1.md").write_text("x")
    assert paths.unique_path(first) == tmp_path / "book_2.md"


def test_unique_path_compound_suffixes(tmp_path):
    (tmp_path / "book.ocr.pdf").write_text("x")
    (tmp_path / "book.owl.json").write_text("x")
    assert paths.unique_path(tmp_path / "book.ocr.pdf") == tmp_path / "book_1.ocr.pdf"
    assert paths.unique_path(tmp_path / "book.owl.json") == tmp_path / "book_1.owl.json"
