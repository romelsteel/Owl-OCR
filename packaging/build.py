"""Builds Owl OCR for Windows (design 12). Never use a .bat file for this.

    py packaging\\build.py                  icon, notices, PyInstaller, smoke test, zip, installer, sums
    py packaging\\build.py --no-installer   everything except Inno Setup

The build runs in build\\venv (created from requirements.txt + requirements-build.txt on the first
run); this script re-starts itself in that venv.

Output in dist\\: OwlOCR\\ (onedir app), OwlOCR-<version>-portable-win64.zip,
OwlOCR-<version>-setup.exe (when Inno Setup 6 is installed) and SHA256SUMS.txt.
"""
from __future__ import annotations

import ast
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "packaging") not in sys.path:
    sys.path.insert(0, str(REPO / "packaging"))
from notices import norm  # noqa: E402
DIST = REPO / "dist"
BUILD = REPO / "build"
APP_DIR = DIST / "OwlOCR"
EXE = APP_DIR / "OwlOCR.exe"
ICON = BUILD / "owl.ico"
VENV = BUILD / "venv"
VENV_PY = VENV / "Scripts" / "python.exe"
REQ_FILES = (REPO / "requirements.txt", REPO / "requirements-build.txt")
CREATE_NO_WINDOW = 0x08000000
FORBIDDEN = ("torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors", "accelerate")
# build tools that must never ship (PyInstaller is GPL; the others have no notices row)
BUILD_TOOLS = ("PyInstaller", "altgraph", "pefile", "ordlookup", "win32ctypes")
INNO_URL = "https://jrsoftware.org/isdl.php"
# Data files that must be inside _internal at these paths (plans A-D read them from there).
REQUIRED_BUNDLE = (
    "owlocr/web/static/index.html", "owlocr/web/static/wizard.js", "owlocr/web/static/wizard_i18n.js",
    "owlocr/web/static/selftest.png", "owlocr/engine/pins.json", "owlocr/pipeline/dictionaries.json",
    "owlocr/export/fonts/DejaVuSans.ttf", "owlocr/export/fonts/DejaVuSans-LICENSE.txt",
    "worker/owl_worker.py", "worker/device_patch.py", "worker/requirements-engine.txt",
    "licenses/Apache-2.0.txt", "LICENSE", "THIRD_PARTY_NOTICES.md",
)
# Files that must also sit next to OwlOCR.exe, where a user looks for them (R-T28-2).
REQUIRED_TOP = ("LICENSE", "THIRD_PARTY_NOTICES.md")
OWN_FOLDERS = ("owlocr", "worker", "licenses")


def version() -> str:
    text = (REPO / "owlocr" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def step(title: str) -> None:
    print(f"\n=== {title}", flush=True)


def check_environment() -> None:
    if sys.platform != "win32":
        raise SystemExit("Owl OCR is built on Windows only.")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(f"Build with Python 3.11 (this is {sys.version.split()[0]}): py -3.11 packaging\\build.py")
    pins = json.loads((REPO / "owlocr" / "engine" / "pins.json").read_text(encoding="utf-8"))["uv"]
    if len(pins["sha256"]) != 64:
        raise SystemExit("owlocr/engine/pins.json is not filled in; run py -3.11 packaging\\pin_uv.py")
    for required in (REPO / "LICENSE", REPO / "licenses" / "Apache-2.0.txt", REPO / "worker" / "owl_worker.py",
                     REPO / "worker" / "device_patch.py", REPO / "owlocr" / "web" / "static" / "selftest.png",
                     REPO / "owlocr" / "pipeline" / "dictionaries.json",
                     REPO / "owlocr" / "export" / "fonts" / "DejaVuSans.ttf", *REQ_FILES):
        if not required.is_file():
            raise SystemExit(f"missing {required}")


def in_build_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV.resolve()


def requirements_stamp() -> str:
    return hashlib.sha256(b"".join(path.read_bytes() for path in REQ_FILES)).hexdigest()


def ensure_build_venv() -> Path:
    """Creates build\\venv when missing and installs the requirements when they changed."""
    if not VENV_PY.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    stamp_file = VENV / "owl-requirements.sha256"
    stamp = requirements_stamp()
    current = stamp_file.read_text(encoding="utf-8").strip() if stamp_file.is_file() else ""
    if current != stamp:
        print("installing the build packages into build\\venv (first time: about 60 MB download)", flush=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQ_FILES[0]), "-r", str(REQ_FILES[1])],
                       check=True)
        stamp_file.write_text(stamp + "\n", encoding="utf-8")
    return VENV_PY


def app_running() -> bool:
    done = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OwlOCR.exe", "/NH"], capture_output=True,
                          text=True, creationflags=CREATE_NO_WINDOW)
    return "owlocr.exe" in done.stdout.lower()


def clean() -> None:
    """Removes the previous build output; never touches build\\venv."""
    for path in (BUILD / "pyinstaller", BUILD / "smoke", APP_DIR):
        if path.exists():
            shutil.rmtree(path)
    DIST.mkdir(parents=True, exist_ok=True)
    for old in list(DIST.glob("OwlOCR-*")) + [DIST / "SHA256SUMS.txt"]:
        if old.is_file():
            old.unlink()


def run_pyinstaller() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
                    "--workpath", str(BUILD / "pyinstaller"), str(REPO / "packaging" / "owlocr.spec")],
                   check=True, cwd=str(REPO))


def copy_top_level_notices(app_dir: Path) -> None:
    shutil.copyfile(REPO / "LICENSE", app_dir / "LICENSE")
    shutil.copyfile(REPO / "packaging" / "THIRD_PARTY_NOTICES.md", app_dir / "THIRD_PARTY_NOTICES.md")


def missing_top_files(app_dir: Path) -> list[str]:
    return [name for name in REQUIRED_TOP if not (app_dir / name).is_file()]


def forbidden_found(app_dir: Path) -> list[str]:
    internal = app_dir / "_internal"
    found = []
    for entry in internal.iterdir() if internal.is_dir() else []:
        name = entry.name.lower()
        base = re.split(r"[-.]", name, maxsplit=1)[0]
        banned = set(FORBIDDEN) | {tool.lower() for tool in BUILD_TOOLS}
        if name in banned or base in banned:
            found.append(entry.name)
    return sorted(found)


def forbidden_in_pyz(work_dir: Path | None = None) -> list[str]:
    """Engine libraries and build tools compiled into the PYZ archive (they would not show up as folders)."""
    work_dir = BUILD / "pyinstaller" if work_dir is None else work_dir
    text = "".join(toc.read_text(encoding="utf-8", errors="replace") for toc in work_dir.glob("*/PYZ-*.toc"))
    return sorted(name for name in FORBIDDEN + BUILD_TOOLS if f"'{name}'" in text or f"'{name}." in text)


def pyz_modules(work_dir: Path | None = None) -> set[str]:
    """Top-level module names in every PYZ-*.toc (the pure-Python code inside OwlOCR's archive)."""
    work_dir = BUILD / "pyinstaller" if work_dir is None else work_dir
    tops: set[str] = set()
    for toc in work_dir.glob("*/PYZ-*.toc"):
        _name, entries = ast.literal_eval(toc.read_text(encoding="utf-8"))
        tops |= {entry[0].split(".", 1)[0] for entry in entries}
    return tops


def missing_bundle_files(app_dir: Path) -> list[str]:
    internal = app_dir / "_internal"
    return [rel for rel in REQUIRED_BUNDLE if not (internal / rel).is_file()]


def unwanted_data(app_dir: Path) -> list[str]:
    """spylls' bundled dictionaries and reportlab's fonts must not ship (plan C, R-T28-3)."""
    internal = app_dir / "_internal"
    if not internal.is_dir():
        return []
    found = [p for p in internal.rglob("*") if p.is_file() and p.suffix.lower() in (".dic", ".aff")]
    if (internal / "reportlab" / "fonts").exists():
        found.append(internal / "reportlab" / "fonts")
    return sorted(p.relative_to(internal).as_posix() for p in found)


def notice_rows(notices_text: str) -> set[str]:
    rows = set()
    for line in notices_text.splitlines():
        match = re.match(r"\|\s*([^|]+?)\s*\|", line)
        if match:
            rows.add(norm(match.group(1)))
    return rows


def default_top_to_dists() -> dict:
    import importlib.metadata
    return importlib.metadata.packages_distributions()


def unlisted_packages(app_dir: Path, notices_text: str, top_to_dists: dict | None = None) -> list[str]:
    """Bundled distributions (folders in _internal) that have no row in THIRD_PARTY_NOTICES.md."""
    top_to_dists = default_top_to_dists() if top_to_dists is None else top_to_dists
    rows = notice_rows(notices_text)
    internal = app_dir / "_internal"
    missing: set[str] = set()
    for entry in internal.iterdir() if internal.is_dir() else []:
        if not entry.is_dir():
            continue
        if entry.name.endswith(".dist-info"):
            dist = re.sub(r"-[^-]+\.dist-info$", "", entry.name)
            if norm(dist) not in rows:
                missing.add(norm(dist))
            continue
        top = entry.name[:-5] if entry.name.endswith(".libs") else entry.name
        if top in OWN_FOLDERS:
            continue
        dists = top_to_dists.get(top)
        if not dists:
            missing.add(top)
        else:
            missing.update(norm(d) for d in dists if norm(d) not in rows)
    return sorted(missing)


def unlisted_modules(notices_text: str, work_dir: Path | None = None, app_dir: Path | None = None,
                     top_to_dists: dict | None = None) -> list[str]:
    """Code without a folder: top-level modules in the PYZ and top-level .pyd files in _internal whose
    distribution has no row in THIRD_PARTY_NOTICES.md (stdlib and our own code are skipped)."""
    top_to_dists = default_top_to_dists() if top_to_dists is None else top_to_dists
    app_dir = APP_DIR if app_dir is None else app_dir
    rows = notice_rows(notices_text)
    tops = pyz_modules(work_dir)
    internal = app_dir / "_internal"
    if internal.is_dir():
        tops |= {p.name.split(".", 1)[0] for p in internal.glob("*.pyd")}
    missing: set[str] = set()
    for top in tops:
        if top in sys.stdlib_module_names or top in OWN_FOLDERS:
            continue
        dists = top_to_dists.get(top)
        if not dists:
            missing.add(top)
        else:
            missing.update(norm(d) for d in dists if norm(d) not in rows)
    return sorted(missing)


def user_name_hits(app_dir: Path, user: str) -> list[str]:
    """Files that contain C:\\Users\\<user> (UTF-8 or UTF-16-LE, any case): a leaked build path."""
    if not user:
        return []
    needle = f"c:\\users\\{user}".lower()
    patterns = (needle.encode("utf-8"), needle.encode("utf-16-le"))
    hits = []
    for path in sorted(app_dir.rglob("*")):
        if path.is_file():
            data = path.read_bytes().lower()
            if any(p in data for p in patterns):
                hits.append(path.relative_to(app_dir).as_posix())
    return hits


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_json(url: str, timeout: float = 5.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def wait_health(port: int, timeout_s: float) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = get_json(f"http://127.0.0.1:{port}/api/health", timeout=2.0)
        if data and data.get("ok"):
            return data
        time.sleep(0.5)
    return None


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)


def stop_process(proc) -> None:
    """Kills the process tree and waits, so the next start does not meet the single-instance mutex."""
    kill_tree(proc.pid)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def window_titles(pid: int) -> list[str]:
    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def callback(hwnd, _lparam):
        owner = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            titles.append(buffer.value)
        return True

    user32.EnumWindows(callback, 0)
    return titles


def smoke_env() -> dict[str, str]:
    """Private data and config folders, and the fake worker: the smoke test never touches the
    owner's engine or settings and never starts torch."""
    home = BUILD / "smoke"
    env = dict(os.environ)
    env.update(OWLOCR_HOME=str(home / "data"), OWLOCR_CONFIG=str(home / "config"),
               OWLOCR_ENGINE_WORKER=str(REPO / "tests" / "fake_worker.py"))
    return env


def get_status(url: str, timeout: float = 5.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except OSError:
        return 0


def run_check_imports(exe: Path) -> list[str]:
    """OwlOCR.exe --check-imports (R-T28-7); a hung run is stopped together with its process tree."""
    proc = subprocess.Popen([str(exe), "--check-imports"], env=smoke_env(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        code = proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        stop_process(proc)
        return ["check-imports: did not finish within 180 s"]
    if code == 0:
        return []
    log = BUILD / "smoke" / "data" / "logs" / "check-imports.txt"
    detail = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "(no log written)"
    return [f"check-imports: {detail}"]


def dictionaries_problem(dicts) -> str | None:
    """None when /api/dictionaries lists exactly cs and en; otherwise the problem text (never raises)."""
    try:
        if [d["language"] for d in dicts["languages"]] == ["cs", "en"]:
            return None
    except (KeyError, TypeError, IndexError):
        pass
    return f"--server-only: /api/dictionaries failed (dictionaries.json not bundled?): {dicts!r:.200}"


def smoke_test(exe: Path, expected_version: str) -> list[str]:
    problems: list[str] = run_check_imports(exe)
    port = free_port()
    proc = subprocess.Popen([str(exe), "--server-only", "--port", str(port)], env=smoke_env(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        health = wait_health(port, 90)
        if health is None:
            problems.append("--server-only: /api/health did not answer within 90 s")
        elif health.get("version") != expected_version:
            problems.append(f"--server-only: version {health.get('version')} != {expected_version}")
        else:
            for asset in ("index.html", "static/wizard.js", "static/wizard_i18n.js", "static/selftest.png"):
                url = f"http://127.0.0.1:{port}/" + ("" if asset == "index.html" else asset)
                if get_status(url) != 200:
                    problems.append(f"--server-only: {asset} is not served (static files not bundled?)")
            probe = get_json(f"http://127.0.0.1:{port}/api/wizard/probe", timeout=30)
            if not probe or "tier" not in probe:
                problems.append("--server-only: /api/wizard/probe failed")
            problem = dictionaries_problem(get_json(f"http://127.0.0.1:{port}/api/dictionaries"))
            if problem:
                problems.append(problem)
    finally:
        stop_process(proc)
    port = free_port()
    proc = subprocess.Popen([str(exe), "--port", str(port)], env=smoke_env())
    try:
        deadline, titles = time.monotonic() + 90, []
        while time.monotonic() < deadline and not any("Owl" in t for t in titles):
            time.sleep(1)
            titles = window_titles(proc.pid)
        if not any("Owl" in t for t in titles):
            problems.append(f"window: no visible 'Owl OCR' window within 90 s (titles: {titles})")
        if wait_health(port, 30) is None:
            problems.append("window: /api/health did not answer")
    finally:
        stop_process(proc)
    return problems


def make_zip(app_dir: Path, out: Path) -> Path:
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(Path(app_dir.name) / path.relative_to(app_dir)))
    return out


def find_iscc() -> Path | None:
    candidates = [shutil.which("ISCC")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe"))
    candidates += [r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def build_installer(iscc: Path, app_version: str) -> Path:
    subprocess.run([str(iscc), f"/DAppVersion={app_version}", f"/DRepoDir={REPO}", f"/DSourceDir={APP_DIR}",
                    f"/DOutputDir={DIST}", f"/DIconFile={ICON}", str(REPO / "packaging" / "installer.iss")],
                   check=True)
    return DIST / f"OwlOCR-{app_version}-setup.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sums(files: list[Path], out: Path) -> Path:
    out.write_text("".join(f"{sha256(f)}  {f.name}\n" for f in files), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    app_version = version()
    step(f"Owl OCR {app_version}: checks")
    check_environment()
    if not in_build_venv():
        return subprocess.run([str(ensure_build_venv()), str(Path(__file__).resolve()), *argv],
                              cwd=str(REPO)).returncode
    if app_running():
        print("Close Owl OCR first (OwlOCR.exe is running).")
        return 1
    step("clean")
    clean()
    step("icon and third-party notices")
    subprocess.run([sys.executable, str(REPO / "packaging" / "make_icon.py"), str(ICON)], check=True)
    subprocess.run([sys.executable, str(REPO / "packaging" / "notices.py")], check=True)
    step("PyInstaller (onedir, windowed)")
    run_pyinstaller()
    copy_top_level_notices(APP_DIR)
    bad = forbidden_found(APP_DIR) + forbidden_in_pyz()
    if bad:
        print("FAILED: engine libraries ended up in the app:", bad)
        return 1
    missing = missing_bundle_files(APP_DIR) + missing_top_files(APP_DIR)
    if missing:
        print("FAILED: data files missing from the app:", missing)
        return 1
    notices_text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    unlisted = sorted(set(unlisted_packages(APP_DIR, notices_text)) | set(unlisted_modules(notices_text)))
    if unlisted:
        print("FAILED: bundled but not in THIRD_PARTY_NOTICES.md:", unlisted)
        return 1
    unwanted = unwanted_data(APP_DIR)
    if unwanted:
        print("FAILED: data that must not ship:", unwanted)
        return 1
    hits = user_name_hits(APP_DIR, os.environ.get("USERNAME", ""))
    if hits:
        print("WARNING: user name found in:", hits)
    step("smoke test of the built app")
    problems = smoke_test(EXE, app_version)
    if problems:
        for problem in problems:
            print("FAILED:", problem)
        return 1
    print("smoke test passed")
    step("portable zip")
    artefacts = [make_zip(APP_DIR, DIST / f"OwlOCR-{app_version}-portable-win64.zip")]
    step("installer")
    iscc = find_iscc()
    if "--no-installer" in argv:
        print("skipped (--no-installer)")
    elif iscc is None:
        print(f"Inno Setup 6 is not installed. Download it from {INNO_URL}, install it for the current user "
              "and run this build again. The portable zip is ready.")
    else:
        artefacts.append(build_installer(iscc, app_version))
    step("checksums")
    print(write_sums(artefacts, DIST / "SHA256SUMS.txt").read_text(encoding="utf-8"))
    for artefact in artefacts:
        print(f"{artefact}  {artefact.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
