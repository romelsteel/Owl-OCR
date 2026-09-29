import os
import stat
import sys
import threading

import pytest

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import uvtool
from owlocr.engine.install_kit import BootstrapError, Deps, StageContext
from owlocr.hardware import tier_by_name


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "config"))
    return tmp_path / "data"


def make_ctx(run_cmd=None, cancel=None):
    emitted, logged = [], []
    deps = Deps(pins={}, run_cmd=run_cmd or (lambda args, env, on_line, cancel: 0))
    ctx = StageContext(tier_by_name("cpu"), deps, cancel, lambda d, t, m: emitted.append((d, t, m)), logged.append)
    return ctx, emitted, logged


def test_layout_of_the_engine_folder(home):
    engine = home / "engine"
    assert kit.uv_exe() == engine / "tools" / "uv.exe"
    assert kit.python_dir() == engine / "python"
    assert kit.venv_dir() == engine / "venv"
    assert kit.uv_cache_dir() == engine / "uv-cache"
    assert kit.install_file() == engine / "install.json"
    assert paths.engine_python() == kit.venv_dir() / "Scripts" / "python.exe"


def test_report_throttles_but_never_drops_text_or_completion(home):
    ctx, emitted, _ = make_ctx()
    ctx.report(done=1, total=100, message="a")
    for i in range(2, 50):
        ctx.report(done=i)                      # within 0.25 s: swallowed
    ctx.report(message="b")                    # new text: always emitted
    ctx.report(done=100)                       # finished: always emitted
    assert emitted[0] == (1, 100, "a")
    assert emitted[1] == (49, 100, "b")
    assert emitted[-1] == (100, 100, "b")
    assert len(emitted) == 3


def test_stamps_round_trip(home):
    assert kit.read_stamp("tools") is None
    kit.write_stamp("tools", {"version": "1"})
    assert kit.read_stamp("tools") == {"version": "1"}
    (kit.stamps_dir() / "bad.json").write_text("[1, 2", encoding="utf-8")
    assert kit.read_stamp("bad") is None


def test_managed_python_and_venv_home(home):
    assert kit.managed_python() is None
    base = kit.python_dir() / "cpython-3.11.13-windows-x86_64-none"
    base.mkdir(parents=True)
    (base / "python.exe").write_bytes(b"")
    assert kit.managed_python() == base / "python.exe"
    kit.venv_dir().mkdir(parents=True)
    (kit.venv_dir() / "pyvenv.cfg").write_text(f"home = {base}\n", encoding="utf-8")
    assert kit.venv_home_ok()
    (kit.venv_dir() / "pyvenv.cfg").write_text("home = C:\\Elsewhere\\python\n", encoding="utf-8")
    assert not kit.venv_home_ok()


def _is_link(path) -> bool:
    return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def test_managed_python_ignores_a_junction_and_picks_the_newest_patch(home):
    from tests.install_fakes import make_junction

    real = kit.python_dir() / "cpython-3.11.9-windows-x86_64-none"
    newer = kit.python_dir() / "cpython-3.11.16-windows-x86_64-none"
    for folder in (real, newer):
        folder.mkdir(parents=True)
        (folder / "python.exe").write_bytes(b"")
    assert kit.managed_python() == newer / "python.exe"      # 16 > 9, not text order
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "python.exe").write_bytes(b"")
    make_junction(kit.python_dir() / "cpython-3.11.99-windows-x86_64-none", elsewhere)
    assert kit.managed_python() == newer / "python.exe"


def test_remove_python_links_removes_only_links_and_never_follows_them(home):
    from tests.install_fakes import make_junction

    real = kit.python_dir() / "cpython-3.11.16-windows-x86_64-none"
    real.mkdir(parents=True)
    (real / "python.exe").write_bytes(b"real")
    link = kit.python_dir() / "cpython-3.11-windows-x86_64-none"
    make_junction(link, real)
    assert _is_link(link)
    logged = []
    removed = kit.remove_python_links(logged.append)
    assert removed == [link.name]
    assert not os.path.lexists(link)
    assert (real / "python.exe").read_bytes() == b"real"       # the target is untouched
    assert any(link.name in line for line in logged)
    assert kit.remove_python_links(logged.append) == []        # nothing left to do


def test_is_link_only_for_junctions_and_symlinks(home, monkeypatch):
    from types import SimpleNamespace
    from tests.install_fakes import make_junction

    target = home / "target"
    target.mkdir(parents=True)
    link = home / "link"
    make_junction(link, target)
    assert kit.is_link(link)
    assert not kit.is_link(target)
    # A OneDrive / cloud placeholder folder: reparse point attribute, but another tag.
    placeholder = SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_DIRECTORY,
                                  st_reparse_tag=0x9000001A)          # IO_REPARSE_TAG_CLOUD_6
    monkeypatch.setattr(kit.os, "lstat", lambda path: placeholder)
    assert not kit.is_link(target)


def test_managed_python_accepts_a_cloud_placeholder_folder(home, monkeypatch):
    base = kit.python_dir() / "cpython-3.11.16-windows-x86_64-none"
    base.mkdir(parents=True)
    (base / "python.exe").write_bytes(b"")
    real_lstat = os.lstat

    def lstat(path):
        result = real_lstat(path)
        if str(path) == str(base):
            from types import SimpleNamespace
            return SimpleNamespace(st_file_attributes=result.st_file_attributes | stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                   st_reparse_tag=0x9000001A)
        return result

    monkeypatch.setattr(kit.os, "lstat", lstat)
    assert kit.managed_python() == base / "python.exe"
    assert kit.remove_python_links() == []
    assert base.is_dir()


def test_remove_python_links_without_a_python_folder(home):
    assert kit.remove_python_links() == []


def test_torch_flavor():
    assert kit.torch_flavor(tier_by_name("gpu_full")) == "cu128"
    assert kit.torch_flavor(tier_by_name("cpu")) == "cpu"


def test_uv_env_isolates_uv(home, monkeypatch):
    monkeypatch.setenv("UV_INDEX_URL", "https://evil.invalid/simple")
    monkeypatch.setenv("VIRTUAL_ENV", "C:\\some\\venv")
    env = kit.uv_env()
    assert "UV_INDEX_URL" not in env and "VIRTUAL_ENV" not in env
    assert env["UV_CACHE_DIR"] == str(kit.uv_cache_dir())
    assert env["UV_PYTHON_INSTALL_DIR"] == str(kit.python_dir())
    assert env["UV_NO_CONFIG"] == "1" and env["UV_PYTHON_PREFERENCE"] == "only-managed"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_run_tool_reports_failure_with_last_line(home):
    def fake(args, env, on_line, cancel):
        on_line("Resolved 3 packages")
        on_line("error: No solution found")
        return 2

    ctx, emitted, logged = make_ctx(fake)
    with pytest.raises(BootstrapError, match=r"command_failed: uv.exe pip install exited with 2: error: No solution found"):
        kit.run_tool(ctx, ["C:\\x\\uv.exe", "pip", "install", "torch"])
    assert logged[0].startswith("$ C:\\x\\uv.exe pip install torch")
    assert emitted[-1][2] == "error: No solution found"


def test_run_tool_cancel(home):
    cancel = threading.Event()
    cancel.set()
    ctx, _, _ = make_ctx(lambda args, env, on_line, c: uvtool.CANCELLED, cancel)
    with pytest.raises(BootstrapError, match="^cancelled$"):
        kit.run_tool(ctx, ["uv.exe", "venv"])


def test_probe_tool_never_raises(home):
    def boom(args, env, on_line, cancel):
        raise OSError("not found")

    ctx, _, logged = make_ctx(boom)
    assert kit.probe_tool(ctx, ["python.exe", "--version"]) == (-1, [])
    assert any("cannot start" in line for line in logged)


def test_python_is_311(home):
    ctx, _, _ = make_ctx(lambda args, env, on_line, cancel: on_line("Python 3.11.13") or 0)
    assert kit.python_is_311(ctx, kit.python_dir() / "python.exe")
    ctx, _, _ = make_ctx(lambda args, env, on_line, cancel: on_line("Python 3.12.1") or 0)
    assert not kit.python_is_311(ctx, kit.python_dir() / "python.exe")


def test_rmtree_removes_read_only_files(tmp_path):
    folder = tmp_path / "x" / "y"
    folder.mkdir(parents=True)
    locked = folder / "ro.txt"
    locked.write_text("x", encoding="utf-8")
    os.chmod(locked, stat.S_IREAD)
    kit.rmtree(tmp_path / "x")
    assert not (tmp_path / "x").exists()
    kit.rmtree(tmp_path / "missing")          # no error


def test_copy_atomic_and_dir_size(tmp_path):
    src = tmp_path / "a.bin"
    src.write_bytes(b"12345")
    kit.copy_atomic(src, tmp_path / "out" / "b.bin")
    assert (tmp_path / "out" / "b.bin").read_bytes() == b"12345"
    assert kit.dir_size(tmp_path) == 10


def test_requirements_sha256_uses_the_resource(tmp_path):
    (tmp_path / "worker").mkdir()
    (tmp_path / "worker" / "requirements-engine.txt").write_bytes(b"x\n")
    import hashlib
    assert kit.requirements_sha256(lambda rel: tmp_path / rel) == hashlib.sha256(b"x\n").hexdigest()


def test_disk_free_of_missing_path(tmp_path):
    assert kit.disk_free(tmp_path / "not" / "there") > 0
