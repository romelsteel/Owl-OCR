r"""Entry point of the packaged Owl OCR (PyInstaller starts this file).

    OwlOCR.exe                 normal start (window)
    OwlOCR.exe --server-only   only the local server, no window (smoke tests)
    OwlOCR.exe --remove-data   used by the uninstaller: deletes the engine and the app's data
    OwlOCR.exe --check-imports hidden build check: imports the export/UI libraries and writes a Word
                               and a searchable PDF; the result goes to <logs>\check-imports.txt
"""
import sys


class _NullStream:
    """A windowed build has no console: sys.stdout and sys.stderr are None (design 12)."""

    def write(self, *_args, **_kwargs):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

CHECK_MODULES = ("pikepdf", "reportlab.pdfgen.canvas", "reportlab.pdfbase.ttfonts", "docx",
                 "spylls.hunspell", "pypdfium2", "numpy", "lxml.etree", "PIL.Image", "webview")


def check_exports() -> int:
    r"""Build check (a windowed build has no console): result is written to <logs>\check-imports.txt."""
    import importlib
    problems: list[str] = []
    for name in CHECK_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - every failure is reported
            problems.append(f"import {name}: {type(exc).__name__}: {exc}")
    try:
        from PIL import Image

        from owlocr import paths
        from owlocr.export import export_all
        from owlocr.pipeline.document import Block, Document, Page

        folder = paths.work_dir("check-imports")
        source = folder / "blank.png"
        Image.new("RGB", (200, 200), "white").save(source)
        text = "Příliš žluťoučký kůň"
        page = Page(0, "ocr", "quality", 200, 200, 0,
                    [Block("text", (100, 100, 900, 300), text, text, [])], "", [], 0.0)
        doc = Document(str(source), "unlimited_ocr", "check", "0", "2026-01-01T00:00:00", [page])
        written = export_all(doc, source, ["docx", "pdf"], folder, {})
        for fmt in ("docx", "pdf"):
            path = written.get(fmt)
            if path is None or not path.is_file() or path.stat().st_size == 0:
                problems.append(f"export {fmt}: no file written")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"export: {type(exc).__name__}: {exc}")
    try:
        from owlocr import paths
        (paths.logs_dir() / "check-imports.txt").write_text("\n".join(problems) or "ok", encoding="utf-8")
    except Exception:  # noqa: BLE001
        return 1
    return 1 if problems else 0


def app_is_running() -> bool:
    """True when the app's single-instance mutex (named after the config folder) exists."""
    import ctypes
    from ctypes import wintypes

    from owlocr.__main__ import mutex_name
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenMutexW(0x00100000, False, mutex_name())   # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def main() -> int:
    if "--check-imports" in sys.argv[1:]:
        return check_exports()
    if "--remove-data" in sys.argv[1:]:
        try:
            running = app_is_running()
        except Exception as exc:  # noqa: BLE001 - an unhandled error would show a bootloader dialog
            print(f"Could not check whether Owl OCR is running ({exc}). Nothing was deleted.")
            return 1
        if running:
            print("Owl OCR is running; close it before removing its data. Nothing was deleted.")
            return 1
        from owlocr.uninstall import main as remove_data
        return remove_data()
    from owlocr.__main__ import main as app_main
    result = app_main()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
