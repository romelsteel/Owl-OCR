"""Choosing the data root and moving an existing one (design 4 and 6.1 step 3)."""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

from owlocr import paths
from owlocr.engine import install_kit as kit

# Everything Owl OCR keeps in the data root. Nothing else in that folder is ever touched.
DATA_ITEMS = ("engine", "models", "hf_home", "work", "logs", "dictionaries", "queue.json")

# Ownership of a data root is proven by this marker file, never by the names of the items in it
# (models, logs, work ... are generic and may belong to the user's own folder).
ROOT_MARKER = ".owlocr-root"
ROOT_MARKER_TEXT = "Owl OCR data folder - do not delete\n"

log = logging.getLogger(__name__)

# Source items that could not be deleted after the last successful move (already copied to the
# new place, so nothing is lost). The callers keep the plain Path return value; this list is
# also written to the log.
last_leftovers: list[str] = []


class LocationError(ValueError):
    """The message starts with a code: `<code>: <details>`."""


def free_bytes(path: Path) -> int:
    return kit.disk_free(path)


def has_data(root: Path) -> bool:
    return any((root / item).exists() for item in ("engine", "models"))


def _install_dir() -> Path | None:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


def _resolve(path: Path) -> Path:
    """Checks the folder name without touching the disk."""
    raw = str(path).strip().strip('"')
    if not raw:
        raise LocationError("empty: no folder given")
    folder = Path(os.path.expandvars(raw)).expanduser()
    if not folder.is_absolute():
        raise LocationError(f"not_absolute: {folder}")
    folder = folder.resolve()
    if folder.exists() and not folder.is_dir():
        raise LocationError(f"not_a_folder: {folder}")
    install = _install_dir()
    if install is not None and (folder == install or folder.is_relative_to(install)):
        raise LocationError(f"inside_install: {folder} is inside the program folder {install}")
    return folder


def _prepare(folder: Path, created: list[Path]) -> None:
    """Creates the folder (recording what was created) and checks that it is writable."""
    missing = []
    probe_dir = folder
    while not probe_dir.exists() and probe_dir.parent != probe_dir:
        missing.append(probe_dir)
        probe_dir = probe_dir.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
        created.extend(reversed(missing))
        fd, probe = tempfile.mkstemp(prefix=".owlocr-write-", dir=folder)
        os.close(fd)
        os.unlink(probe)
    except OSError as exc:
        created.extend(m for m in reversed(missing) if m not in created)
        raise LocationError(f"not_writable: {folder}: {exc}") from exc


def _undo_created(created: list[Path]) -> None:
    for folder in reversed(created):        # best effort: rmdir only removes empty folders
        try:
            folder.rmdir()
        except OSError:
            pass


def validate_location(path: Path) -> Path:
    """Returns the absolute folder or raises LocationError. Creates the folder if needed."""
    folder = _resolve(path)
    created: list[Path] = []
    try:
        _prepare(folder, created)
    except LocationError:
        _undo_created(created)
        raise
    return folder


def is_drive_root(path: Path) -> bool:
    return path.parent == path


def default_root() -> Path:
    """Where paths.data_root() points when no location was chosen."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "OwlOCR"


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def is_owl_root(folder: Path, include_current: bool = True) -> bool:
    """True when the folder is proven to be an Owl OCR data root: it holds the marker, or it is
    the default location, or (include_current) the data root currently in use."""
    return ((folder / ROOT_MARKER).is_file() or _same(folder, default_root())
            or (include_current and _same(folder, paths.data_root())))


def _write_marker(folder: Path) -> None:
    marker = folder / ROOT_MARKER
    if not marker.exists():
        marker.write_text(ROOT_MARKER_TEXT, encoding="utf-8")


def _effective(folder: Path, created: list[Path]) -> Path:
    folder = _resolve(folder)
    if is_drive_root(folder) or (folder.exists() and any(folder.iterdir()) and not is_owl_root(folder)):
        folder = folder / "OwlOCR"
        if folder.exists() and any(folder.iterdir()) and not is_owl_root(folder):
            raise LocationError(f"not_empty: {folder} exists, is not empty and is not an Owl OCR folder")
    _prepare(folder, created)
    return folder


def effective_root(folder: Path) -> Path:
    """The folder Owl OCR really uses for a folder the user picked.

    The item names (models, logs, work ...) are generic, so only a folder that holds the marker,
    the default location or the current data root is used as it is (an empty folder too). A drive
    root or any other non-empty folder gets an `OwlOCR` subfolder instead."""
    created: list[Path] = []
    try:
        return _effective(folder, created)
    except LocationError:
        _undo_created(created)
        raise


def choose_location(path: Path) -> Path:
    """Wizard step 3: makes `path` (or its OwlOCR subfolder, see effective_root) the data root.
    An existing data root is moved there. Returns the folder really used."""
    if os.environ.get("OWLOCR_HOME"):
        raise LocationError("env_override: OWLOCR_HOME is set, the data folder cannot be changed")
    created: list[Path] = []
    try:
        folder = _effective(path, created)
        current = paths.data_root().resolve()
        if folder == current:
            return folder
        if has_data(current):
            return move_data_root(folder)
        wrote = not (folder / ROOT_MARKER).exists()
        _write_marker(folder)
        try:
            paths.set_data_root(folder)
        except Exception:
            if wrote:
                (folder / ROOT_MARKER).unlink(missing_ok=True)
            raise
        return folder
    except BaseException:
        _undo_created(created)
        raise


def _copy_item(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _delete_path(target: Path) -> None:
    if target.is_dir():
        kit.rmtree(target)
    elif target.exists():
        target.unlink()


def move_data_root(dest: Path) -> Path:
    """Moves every item of DATA_ITEMS to `dest` (or its OwlOCR subfolder, see effective_root),
    points location.txt there and returns the folder really used.

    The engine must be stopped. On the same drive an item is renamed (atomic); otherwise it is
    copied. If anything fails before all items are in place, only what this call created is
    removed (the sources stay intact) and LocationError("move_failed: ...") names anything that
    could not be undone. Only after location.txt points at the new folder are the copied sources
    deleted; a source that cannot be deleted is NOT rolled back (the copy is complete) but is
    listed in `last_leftovers` and in the log.

    The venv stores absolute paths, so afterwards `bootstrap.is_installed()` is False until the
    installer has rebuilt the venv from the kept downloads (no network needed)."""
    if os.environ.get("OWLOCR_HOME"):
        raise LocationError("env_override: OWLOCR_HOME is set, the data folder cannot be moved")
    src = paths.data_root().resolve()
    created: list[Path] = []
    try:
        return _move(src, _effective(dest, created), created)
    except BaseException:
        _undo_created(created)
        raise


def _move(src: Path, dest: Path, created: list[Path]) -> Path:
    last_leftovers.clear()
    if dest == src:
        _write_marker(dest)
        return dest
    if dest.is_relative_to(src) or src.is_relative_to(dest):
        raise LocationError(f"nested: {dest} and {src} contain each other")
    items = [item for item in DATA_ITEMS if (src / item).exists()]
    clashes = [item for item in items if (dest / item).exists()]
    if clashes:
        raise LocationError(f"exists: {dest} already contains {', '.join(clashes)}")
    needed = sum(kit.dir_size(src / i) if (src / i).is_dir() else (src / i).stat().st_size for i in items)
    same_drive = os.path.splitdrive(str(src))[0].lower() == os.path.splitdrive(str(dest))[0].lower()
    if not same_drive and free_bytes(dest) < needed:
        raise LocationError(f"not_enough_space: {needed} bytes needed, {free_bytes(dest)} free")
    renamed: list[str] = []
    copied: list[str] = []
    started: str | None = None
    marker_new = not (dest / ROOT_MARKER).exists()
    try:
        _write_marker(dest)
        for item in items:
            started = item
            try:
                os.rename(src / item, dest / item)
                renamed.append(item)
            except OSError:
                _copy_item(src / item, dest / item)
                copied.append(item)
            started = None
        paths.set_data_root(dest)
    except Exception as exc:
        stuck: list[str] = []
        for item in reversed(renamed):
            try:
                os.rename(dest / item, src / item)
            except OSError as back:
                stuck.append(f"{item} (still in {dest}: {back})")
        for item in copied + ([started] if started else []):   # copies of this call, incl. a half-made one
            try:
                _delete_path(dest / item)
            except Exception as gone:
                stuck.append(f"{item} (copy left in {dest}: {gone})")
        if marker_new:
            (dest / ROOT_MARKER).unlink(missing_ok=True)
        note = f"; not undone: {'; '.join(stuck)}" if stuck else ""
        raise LocationError(f"move_failed: {exc}{note}") from exc
    for item in copied:
        try:
            _delete_path(src / item)
        except Exception as exc:
            last_leftovers.append(f"{src / item}: {exc}")
    if last_leftovers:
        log.warning("moved the data folder, but could not delete the old copies: %s",
                    "; ".join(last_leftovers))
    return dest
