import ctypes
import os

import pytest

from owlocr.web.bridge import Bridge, FILE_TYPES, get_clipboard_text, set_clipboard_text


def test_without_window_dialogs_return_nothing():
    bridge = Bridge()
    assert bridge.pick_files() == []
    assert bridge.pick_folder() is None


def test_dialogs_use_the_window(monkeypatch):
    import webview

    calls = []

    class FakeWindow:
        def create_file_dialog(self, dialog_type, allow_multiple=False, file_types=()):
            calls.append((dialog_type, allow_multiple, file_types))
            return ("C:\\a.pdf", "C:\\b.png") if dialog_type == webview.FileDialog.OPEN else ("C:\\dir",)

    bridge = Bridge()
    bridge.attach(FakeWindow())
    assert bridge.pick_files() == ["C:\\a.pdf", "C:\\b.png"]
    assert bridge.pick_folder() == "C:\\dir"
    assert calls[0] == (webview.FileDialog.OPEN, True, FILE_TYPES)
    assert calls[1][0] == webview.FileDialog.FOLDER


def test_file_types_parse_in_pywebview():
    from webview.util import parse_file_type

    for entry in FILE_TYPES:
        parse_file_type(entry)


def test_open_folder_rejects_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        Bridge().open_folder(str(tmp_path / "missing"))


@pytest.mark.skipif(os.environ.get("OWLOCR_TEST_CLIPBOARD") != "1",
                    reason="overwrites the real clipboard; set OWLOCR_TEST_CLIPBOARD=1 to run")
def test_clipboard_roundtrip_keeps_czech_letters():
    try:
        previous = get_clipboard_text()
    except OSError:
        pytest.skip("clipboard busy")
    try:
        Bridge().copy_text("Příliš žluťoučký kůň úpěl ďábelské ódy")
        assert get_clipboard_text() == "Příliš žluťoučký kůň úpěl ďábelské ódy"
    finally:
        if previous is not None:
            set_clipboard_text(previous)


class _FakeWin:
    """Stands in for user32 + kernel32; records calls and never touches the real clipboard."""

    def __init__(self, lock_result=0x1000, set_result=1, set_error=0):
        self.calls = []
        self.lock_result = lock_result
        self.set_result = set_result
        self.set_error = set_error

    def __getattr__(self, name):
        def call(*args):
            self.calls.append(name)
            if name == "GlobalAlloc":
                return 0x42
            if name == "GlobalLock":
                ctypes.set_last_error(8)          # ERROR_NOT_ENOUGH_MEMORY
                return self.lock_result
            if name == "SetClipboardData":
                ctypes.set_last_error(self.set_error)
                return self.set_result
            if name == "GetClipboardData":
                return 0x42
            if name == "GlobalFree":
                ctypes.set_last_error(0)          # like the real call: overwrites the error
                return 0
            return 1
        return call


@pytest.fixture
def fake_win(monkeypatch):
    from owlocr.web import bridge

    def install(**kwargs):
        fake = _FakeWin(**kwargs)
        monkeypatch.setattr(bridge, "_user32", fake)
        monkeypatch.setattr(bridge, "_kernel32", fake)
        return fake
    return install


def test_clipboard_lock_failure_raises_instead_of_writing_to_null(fake_win, monkeypatch):
    fake = fake_win(lock_result=None)
    monkeypatch.setattr(ctypes, "memmove", lambda *a: pytest.fail("memmove to NULL"))
    with pytest.raises(OSError) as info:
        set_clipboard_text("abc")
    assert info.value.winerror == 8
    assert "GlobalFree" in fake.calls and "SetClipboardData" not in fake.calls
    assert fake.calls[-1] == "CloseClipboard"


def test_clipboard_set_failure_reports_its_own_error_and_frees(fake_win, monkeypatch):
    fake = fake_win(set_result=0, set_error=5)
    monkeypatch.setattr(ctypes, "memmove", lambda *a: None)
    with pytest.raises(OSError) as info:
        set_clipboard_text("abc")
    assert info.value.winerror == 5                # read before GlobalFree reset it
    assert fake.calls.index("SetClipboardData") < fake.calls.index("GlobalFree")
    assert fake.calls[-1] == "CloseClipboard"


def test_clipboard_copy_failure_frees_the_handle(fake_win, monkeypatch):
    fake = fake_win()

    def broken(*args):
        raise ValueError("copy failed")
    monkeypatch.setattr(ctypes, "memmove", broken)
    with pytest.raises(ValueError):
        set_clipboard_text("abc")
    assert "GlobalUnlock" in fake.calls and "GlobalFree" in fake.calls
    assert "SetClipboardData" not in fake.calls and fake.calls[-1] == "CloseClipboard"


def test_clipboard_read_lock_failure_raises_instead_of_reading_null(fake_win, monkeypatch):
    fake = fake_win(lock_result=None)
    monkeypatch.setattr(ctypes, "wstring_at", lambda *a: pytest.fail("read from NULL"))
    with pytest.raises(OSError):
        get_clipboard_text()
    assert fake.calls[-1] == "CloseClipboard"
