r"""Where Owl OCR keeps its files (design section 4).

Config dir (small files): env OWLOCR_CONFIG, else %APPDATA%\OwlOCR.
Data root (large files):  env OWLOCR_HOME, else the path in <config dir>\location.txt,
                          else %LOCALAPPDATA%\OwlOCR.
"""
import os
import sys
import time
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def config_dir() -> Path:
    folder = _env_path("OWLOCR_CONFIG")
    if folder is None:
        folder = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "OwlOCR"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def data_root() -> Path:
    home = _env_path("OWLOCR_HOME")
    if home is not None:
        return home
    location = config_dir() / "location.txt"
    if location.is_file():
        stored = location.read_text(encoding="utf-8").strip()
        if stored:
            return Path(stored)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "OwlOCR"


def set_data_root(path: Path) -> None:
    atomic_write_text(config_dir() / "location.txt", str(Path(path).resolve()) + "\n")


def engine_dir() -> Path:
    return data_root() / "engine"


def engine_python() -> Path:
    return engine_dir() / "venv" / "Scripts" / "python.exe"


def worker_dir() -> Path:
    return engine_dir() / "worker"


def models_dir() -> Path:
    return data_root() / "models"


def model_dir(engine_id: str = "unlimited_ocr") -> Path:
    return models_dir() / engine_id


def hf_home() -> Path:
    return data_root() / "hf_home"


def work_dir(job_id: str) -> Path:
    folder = data_root() / "work" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def logs_dir() -> Path:
    folder = data_root() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def queue_file() -> Path:
    return data_root() / "queue.json"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def resource_path(rel: str) -> Path:
    """Files shipped with the app. In a PyInstaller build they live under sys._MEIPASS,
    in development under the repository root."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / rel


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text so that readers see either the old or the new file, never half of it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows: a virus scanner or indexer may hold the target open for a moment.
            if attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def atomic_write_file(path: Path, write) -> None:
    """Call write(tmp) with a temporary path in the same folder as `path`, then move the file
    into place. If writing fails, the temporary file is removed and `path` is never created, so
    a failed export leaves no broken file behind (final review M5)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        write(tmp)
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Windows: a virus scanner or indexer may hold the target open for a moment.
                if attempt == 19:
                    raise
                time.sleep(0.05)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


_COMPOUND_SUFFIXES = (".ocr.pdf", ".owl.json")


def unique_path(path: Path) -> Path:
    """Return `path` if it is free, else the first free name with _1, _2 ... before the suffix."""
    path = Path(path)
    if not path.exists():
        return path
    name = path.name
    suffix = next((s for s in _COMPOUND_SUFFIXES if name.lower().endswith(s)), path.suffix)
    stem = name[: len(name) - len(suffix)] if suffix else name
    n = 1
    while True:
        candidate = path.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1
