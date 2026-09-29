import os
import sys

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import scrub_local_paths as scrub  # noqa: E402

USER = "jana"          # any name: the real one is read from USERNAME at run time


def test_windows_paths_become_userprofile():
    text = r"Python 3.11.9 only (`C:\Users\jana\AppData\Local\Programs\Python\Python311`)"
    assert scrub.scrub_text(text, USER) == (r"Python 3.11.9 only (`%USERPROFILE%\AppData\Local\Programs\Python\Python311`)", 1)
    assert scrub.scrub_text(r"`C:\Users\Jana\Desktop\OCR project` is empty", USER)[0] == r"`%USERPROFILE%\Desktop\OCR project` is empty"
    assert scrub.scrub_text("C:/Users/jana/x", USER)[0] == "%USERPROFILE%/x"


def test_escaped_and_mangled_forms():
    assert scrub.scrub_text('"C:\\\\Users\\\\jana\\\\Desktop"', USER)[0] == '"%USERPROFILE%\\\\Desktop"'
    assert scrub.scrub_text('"C:\\Users\\jana\\Desktop"', USER)[0] == '"%USERPROFILE%\\Desktop"'
    mangled = r"C:\Users\jana\.claude\projects\C--Users-jana-Desktop-Claude-code\memory"
    assert scrub.scrub_text(mangled, USER) == (r"%USERPROFILE%\.claude\projects\C--Users-<user>-Desktop-Claude-code\memory", 2)


def test_other_names_and_words_are_left_alone():
    text = r"janapi C:\Users\janak\x and C:\Users\Public"
    assert scrub.scrub_text(text, USER) == (text, 0)


def test_the_script_does_not_contain_the_user_name():
    user = os.environ.get("USERNAME", "").strip().lower()
    source = (REPO / "packaging" / "scrub_local_paths.py").read_text(encoding="utf-8").lower()
    assert user and user not in source


def test_name_must_end_at_a_path_boundary():
    text = r"C:\Users\jana.bak\x C:\Users\jana-x\y C:/Users/jana_z/q"
    assert scrub.scrub_text(text, USER) == (text, 0)
    assert scrub.scrub_text(r"see C:\Users\jana, and C:\Users\jana", USER)[0] == "see %USERPROFILE%, and %USERPROFILE%"
