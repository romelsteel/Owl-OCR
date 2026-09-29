"""`OwlOCR.exe --remove-data`: called by the uninstaller when the user agrees to delete the
engine and the app's data. Deletes only what Owl OCR created; documents and the files written
next to them are never touched."""
from __future__ import annotations

import sys
from pathlib import Path

from owlocr import paths
from owlocr.engine import install_kit as kit
from owlocr.engine import relocate
from owlocr.engine.relocate import DATA_ITEMS

CONFIG_ITEMS = ("settings.json", "location.txt", "instance.json")


def _remove(target: Path, problems: list[str]) -> None:
    try:
        if target.is_dir():
            kit.rmtree(target)
        elif target.exists():
            target.unlink()
    except OSError as exc:
        problems.append(f"{target}: {exc}")


def remove_all_data() -> list[str]:
    """Returns a list of problems; empty when everything was removed."""
    problems: list[str] = []
    try:
        from owlocr.engine.client import sweep_stale_worker
        sweep_stale_worker()            # an engine left running would keep files locked
    except Exception as exc:            # a failed sweep must not stop the uninstall
        problems.append(f"sweep: {exc}")
    root, config = paths.data_root(), paths.config_dir()
    owned = not relocate.is_drive_root(root) and relocate.is_owl_root(root, include_current=False)
    before = len(problems)
    for item in DATA_ITEMS:
        if not owned:       # generic names (models, logs ...) in a folder not proven to be ours
            if (root / item).exists():
                problems.append(f"{root / item}: not deleted, {root} is not marked as an Owl OCR folder")
            continue
        _remove(root / item, problems)
    # Something stayed behind: keep the marker and location.txt, so the leftover data can still be
    # found (and removed by a later uninstall) instead of being orphaned in a folder nothing points to.
    leftovers = len(problems) > before
    if owned and not leftovers:
        _remove(root / relocate.ROOT_MARKER, problems)
    for item in CONFIG_ITEMS:
        if leftovers and item == "location.txt":
            continue
        _remove(config / item, problems)
    for folder in (root, config):
        if relocate.is_drive_root(folder):
            continue
        try:
            folder.rmdir()               # only succeeds when nothing else is left in it
        except OSError:
            pass
    return problems


def main() -> int:
    return 0 if not remove_all_data() else 1


if __name__ == "__main__":
    sys.exit(main())
