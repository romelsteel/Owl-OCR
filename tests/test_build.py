import hashlib
import http.server
import json
import sys
import threading
import zipfile

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import build  # noqa: E402


def test_version_matches_package():
    import owlocr
    assert build.version() == owlocr.__version__


def test_forbidden_found(tmp_path):
    internal = tmp_path / "OwlOCR" / "_internal"
    for name in ("webview", "flask", "torch", "transformers-4.57.1.dist-info", "torchvision.libs"):
        (internal / name).mkdir(parents=True)
    assert build.forbidden_found(tmp_path / "OwlOCR") == ["torch", "torchvision.libs", "transformers-4.57.1.dist-info"]
    assert build.forbidden_found(tmp_path / "missing") == []


def test_make_zip_and_sums(tmp_path):
    app = tmp_path / "OwlOCR"
    (app / "_internal").mkdir(parents=True)
    (app / "OwlOCR.exe").write_bytes(b"exe")
    (app / "_internal" / "base_library.zip").write_bytes(b"lib")
    out = build.make_zip(app, tmp_path / "OwlOCR-0.1.0-portable-win64.zip")
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["OwlOCR/OwlOCR.exe", "OwlOCR/_internal/base_library.zip"]
    sums = build.write_sums([out], tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert sums == f"{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}\n"


def test_wait_health():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "version": "0.1.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert build.wait_health(server.server_address[1], 5) == {"ok": True, "version": "0.1.0"}
    finally:
        server.shutdown()
    assert build.wait_health(build.free_port(), 1) is None


def test_find_iscc_returns_an_existing_file_or_none():
    found = build.find_iscc()
    assert found is None or found.is_file()


def test_missing_bundle_files(tmp_path):
    app = tmp_path / "OwlOCR"
    for rel in build.REQUIRED_BUNDLE:
        (app / "_internal" / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / "_internal" / rel).write_bytes(b"x")
    assert build.missing_bundle_files(app) == []
    (app / "_internal" / "owlocr" / "export" / "fonts" / "DejaVuSans.ttf").unlink()
    assert build.missing_bundle_files(app) == ["owlocr/export/fonts/DejaVuSans.ttf"]


def test_required_bundle_matches_the_spec():
    spec = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
    for rel in ("owlocr/pipeline", "owlocr/export/fonts", "owlocr/web/static", "worker", "licenses"):
        assert f'"{rel}")' in spec, rel


def test_spec_excludes_build_tools():
    # first real build: cffi's compile helper pulled setuptools (228 modules + dist-info) into the app
    spec = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
    for name in ("setuptools", "pkg_resources", "distutils", "_distutils_hack"):
        assert f'"{name}"' in spec, name


# --- rulings R-T28-1 .. R-T28-7 ---

def test_unlisted_packages_finds_a_package_missing_from_the_notices(tmp_path):
    internal = tmp_path / "OwlOCR" / "_internal"
    for name in ("PIL", "cryptography", "owlocr", "numpy.libs", "foo-1.0.dist-info"):
        (internal / name).mkdir(parents=True)
    notices = ("| Package | Version | Licence | Source |\n|---|---|---|---|\n"
               "| Pillow | 12.3.0 | MIT-CMU | x |\n| numpy | 2.4.6 | BSD | y |\n")
    mapping = {"PIL": ["Pillow"], "cryptography": ["cryptography"], "numpy": ["numpy"]}
    assert build.unlisted_packages(tmp_path / "OwlOCR", notices, mapping) == ["cryptography", "foo"]


def test_clean_keeps_the_build_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "BUILD", tmp_path / "build")
    monkeypatch.setattr(build, "DIST", tmp_path / "dist")
    monkeypatch.setattr(build, "APP_DIR", tmp_path / "dist" / "OwlOCR")
    (tmp_path / "build" / "venv").mkdir(parents=True)
    (tmp_path / "build" / "venv" / "marker").write_text("x")
    (tmp_path / "build" / "pyinstaller").mkdir()
    (tmp_path / "dist" / "OwlOCR").mkdir(parents=True)
    build.clean()
    assert (tmp_path / "build" / "venv" / "marker").is_file()
    assert not (tmp_path / "build" / "pyinstaller").exists()
    assert not (tmp_path / "dist" / "OwlOCR").exists()
    assert build.in_build_venv() is False


def test_copy_top_level_notices(tmp_path):
    app = tmp_path / "OwlOCR"
    app.mkdir()
    assert build.missing_top_files(app) == list(build.REQUIRED_TOP)
    build.copy_top_level_notices(app)
    assert (app / "LICENSE").read_bytes() == (REPO / "LICENSE").read_bytes()
    assert (app / "THIRD_PARTY_NOTICES.md").read_bytes() == \
        (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_bytes()
    assert build.missing_top_files(app) == []


def test_unwanted_data(tmp_path):
    app = tmp_path / "OwlOCR"
    internal = app / "_internal"
    (internal / "spylls" / "data").mkdir(parents=True)
    (internal / "spylls" / "data" / "en.dic").write_text("x")
    (internal / "spylls" / "data" / "en.aff").write_text("x")
    (internal / "reportlab" / "fonts").mkdir(parents=True)
    (internal / "owlocr" / "export" / "fonts").mkdir(parents=True)
    (internal / "owlocr" / "export" / "fonts" / "DejaVuSans.ttf").write_text("x")
    assert build.unwanted_data(app) == ["reportlab/fonts", "spylls/data/en.aff", "spylls/data/en.dic"]
    assert build.unwanted_data(tmp_path / "missing") == []


def test_forbidden_in_pyz(tmp_path):
    toc = tmp_path / "OwlOCR" / "PYZ-00.toc"
    toc.parent.mkdir(parents=True)
    toc.write_text("('PYZ-00.pyz', [('flask', 'x', 'PYMODULE'), ('torch.nn', 'y', 'PYMODULE')])",
                   encoding="utf-8")
    assert build.forbidden_in_pyz(tmp_path) == ["torch"]
    toc.write_text("('PYZ-00.pyz', [('flask', 'x', 'PYMODULE'), ('torchlike', 'y', 'PYMODULE')])",
                   encoding="utf-8")
    assert build.forbidden_in_pyz(tmp_path) == []


def test_stop_process_kills_then_waits(monkeypatch):
    import subprocess
    calls = []
    monkeypatch.setattr(build, "kill_tree", lambda pid: calls.append(("kill", pid)))

    class Dummy:
        pid = 4242

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            raise subprocess.TimeoutExpired("x", timeout)

    build.stop_process(Dummy())
    assert calls == [("kill", 4242), ("wait", 15)]


def test_user_name_hits(tmp_path):
    import uuid
    user = "u" + uuid.uuid4().hex[:10]
    app = tmp_path / "OwlOCR"
    (app / "_internal").mkdir(parents=True)
    (app / "clean.txt").write_bytes(b"nothing here")
    (app / "_internal" / "a.bin").write_bytes(("x C:\\USERS\\" + user.upper() + "\\y").encode("utf-8"))
    (app / "_internal" / "b.bin").write_bytes(("C:\\Users\\" + user + "\\z").encode("utf-16-le"))
    assert build.user_name_hits(app, user) == ["_internal/a.bin", "_internal/b.bin"]


# --- fix round 1 ---

def test_unlisted_modules_reads_the_pyz_and_top_level_pyd(tmp_path):
    work = tmp_path / "pyinstaller"
    (work / "OwlOCR").mkdir(parents=True)
    (work / "OwlOCR" / "PYZ-00.toc").write_text(repr(("x.pyz", [
        ("flask", "a", "PYMODULE"), ("flask.app", "a", "PYMODULE"), ("json", "b", "PYMODULE"),
        ("owlocr.web", "c", "PYMODULE"), ("altgraph.Graph", "d", "PYMODULE"), ("mystery", "e", "PYMODULE")])),
        encoding="utf-8")
    internal = tmp_path / "OwlOCR" / "_internal"
    internal.mkdir(parents=True)
    (internal / "_cffi_backend.cp311-win_amd64.pyd").write_bytes(b"x")
    (internal / "_socket.pyd").write_bytes(b"x")
    notices = "| Package | Version |\n|---|---|\n| Flask | 3.1.3 |\n"
    mapping = {"flask": ["Flask"], "altgraph": ["altgraph"], "_cffi_backend": ["cffi"]}
    assert build.unlisted_modules(notices, work, tmp_path / "OwlOCR", mapping) == ["altgraph", "cffi", "mystery"]


def test_forbidden_in_pyz_catches_build_tools(tmp_path):
    toc = tmp_path / "OwlOCR" / "PYZ-00.toc"
    toc.parent.mkdir(parents=True)
    toc.write_text(repr(("x.pyz", [("PyInstaller.utils.hooks", "a", "PYMODULE"), ("pefile", "b", "PYMODULE")])),
                   encoding="utf-8")
    assert build.forbidden_in_pyz(tmp_path) == ["PyInstaller", "pefile"]


def test_spec_drops_pyinstaller_hook_modules_and_build_tools():
    spec = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
    assert "_pyinstaller" in spec
    for name in ("PyInstaller", "altgraph", "pefile", "ordlookup", "win32ctypes"):
        assert f'"{name}"' in spec, name


def test_user_name_hits_empty_user_is_skipped(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"C:\\Users\\x")
    assert build.user_name_hits(tmp_path, "") == []


def test_dictionaries_problem_handles_bad_shapes():
    good = {"languages": [{"language": "cs"}, {"language": "en"}]}
    assert build.dictionaries_problem(good) is None
    for bad in (None, {}, {"languages": None}, {"languages": ["cs"]}, {"languages": [{"language": "cs"}]}):
        assert build.dictionaries_problem(bad), bad


def test_check_imports_failure_is_a_problem(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "BUILD", tmp_path)
    # python.exe rejects the unknown option --check-imports and exits 2: a problem, not an exception
    problems = build.run_check_imports(__import__("pathlib").Path(sys.executable))
    assert problems == ["check-imports: (no log written)"]
