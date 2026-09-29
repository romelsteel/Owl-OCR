"""pywebview js_api: native file dialogs, Explorer and the clipboard.

JavaScript calls these as `window.pywebview.api.<name>(...)`. Only public methods are exposed;
the window reference is kept in a private attribute so pywebview does not try to expose it.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

FILE_TYPES = (
    "Documents and images (*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff)",
    "All files (*.*)",
)

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.CloseClipboard.restype = wintypes.BOOL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL


def _open_clipboard() -> None:
    for _ in range(20):  # another program may hold the clipboard for a moment
        if _user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError("the clipboard is busy")


def _raise_last_error(free_handle=None):
    """Raises the Windows error of the call that just failed; frees free_handle afterwards
    (GlobalFree would overwrite the thread's last error)."""
    error = ctypes.WinError(ctypes.get_last_error())
    if free_handle:
        _kernel32.GlobalFree(free_handle)
    raise error


def set_clipboard_text(text: str) -> None:
    data = text.encode("utf-16-le") + b"\x00\x00"
    _open_clipboard()
    try:
        _user32.EmptyClipboard()
        handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            _raise_last_error()
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:                     # never copy to NULL: that kills the whole process
            _raise_last_error(handle)
        try:
            ctypes.memmove(pointer, data, len(data))
        except BaseException:
            _kernel32.GlobalUnlock(handle)
            _kernel32.GlobalFree(handle)
            raise
        _kernel32.GlobalUnlock(handle)
        if not _user32.SetClipboardData(_CF_UNICODETEXT, handle):
            _raise_last_error(handle)       # the clipboard owns the handle only on success
    finally:
        _user32.CloseClipboard()


def get_clipboard_text() -> str | None:
    _open_clipboard()
    try:
        handle = _user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return None
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:                     # wstring_at(NULL) would kill the process
            _raise_last_error()
        try:
            return ctypes.wstring_at(pointer)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


class Bridge:
    def __init__(self) -> None:
        self._window = None

    def attach(self, window) -> None:
        self._window = window

    def pick_files(self) -> list[str]:
        if self._window is None:
            return []
        import webview

        result = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                 file_types=FILE_TYPES)
        return [str(p) for p in result] if result else []

    def pick_folder(self) -> str | None:
        if self._window is None:
            return None
        import webview

        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(result[0]) if result else None

    def open_folder(self, path: str) -> None:
        target = Path(path)
        if target.is_file():
            subprocess.Popen(f'explorer /select,"{target}"')
        elif target.is_dir():
            os.startfile(str(target))
        else:
            raise FileNotFoundError(path)

    def copy_text(self, text: str) -> None:
        set_clipboard_text(text)
