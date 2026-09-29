"""owlocr.cli, in-process, with tests/fake_worker.py as the engine."""
import json
import shutil
import sys

import pytest

from owlocr import cli, hardware, paths
from owlocr.pipeline.document import load_sidecar
from tests.conftest import FAKE_WORKER, PAGES
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf


def install_fake_engine(flags: str = "", device: str = "cpu") -> None:
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps({
        "engine_id": "unlimited_ocr", "python": sys.executable, "worker_script": str(FAKE_WORKER),
        "device": device, "env": {"FAKE_WORKER": flags}}))


@pytest.fixture
def letter(tmp_path):
    target = tmp_path / "in" / "dopis.png"
    target.parent.mkdir()
    shutil.copy(PAGES / "01_letter_clean.png", target)
    return target


def test_parse_pages():
    assert cli._parse_pages(None, 3) == [0, 1, 2]
    assert cli._parse_pages("1-5,9", 20) == [0, 1, 2, 3, 4, 8]
    assert cli._parse_pages("3, 1-2 ,2", 10) == [0, 1, 2]
    assert cli._parse_pages("5-3", 10) == [2, 3, 4]
    assert cli._parse_pages("2,40", 3) == [1]
    with pytest.raises(ValueError):
        cli._parse_pages("1-", 3)


def test_image_to_markdown_and_text(letter, tmp_path, capsys):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "md,txt", "--out", str(tmp_path / "out")]) == 0
    out = tmp_path / "out"
    assert (out / "dopis.md").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert (out / "dopis.txt").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    doc = load_sidecar(out / "dopis.owl.json")
    assert doc.source_path == str(letter.resolve()) and doc.pages[0].mode == "quality"
    printed = capsys.readouterr().out.splitlines()
    assert printed == [str(out / "dopis.md"), str(out / "dopis.txt"), str(out / "dopis.owl.json")]
    assert not list((paths.data_root() / "work").iterdir())        # scratch folders removed


def test_outputs_go_next_to_the_input_by_default(letter):
    install_fake_engine()
    assert cli.main([str(letter.parent), "--mode", "fast"]) == 0
    assert (letter.parent / "dopis.md").is_file()               # settings default: md only
    assert not (letter.parent / "dopis.txt").exists()
    assert load_sidecar(letter.parent / "dopis.owl.json").pages[0].mode == "fast"


def test_born_digital_pdf_never_starts_ocr(tmp_path):
    install_fake_engine("crash_on_ocr")
    pdf = make_text_pdf(tmp_path / "clanek.pdf", [["Hello from the text layer"]])
    assert cli.main([str(pdf), "--formats", "txt"]) == 0
    assert (tmp_path / "clanek.txt").read_text(encoding="utf-8") == "Hello from the text layer\n"


def test_page_selection(tmp_path):
    install_fake_engine()
    pdf = make_scan_pdf(tmp_path / "sken.pdf", pages=3)
    assert cli.main([str(pdf), "--pages", "2-3", "--dpi", "100"]) == 0
    doc = load_sidecar(tmp_path / "sken.owl.json")
    assert [p.index for p in doc.pages] == [1, 2]
    assert (doc.pages[0].width_px, doc.pages[0].height_px) == (850, 1100)


def test_page_selection_outside_the_document_fails_without_writing(tmp_path, capsys):
    install_fake_engine()
    pdf = make_scan_pdf(tmp_path / "sken.pdf", pages=3)
    assert cli.main([str(pdf), "--pages", "40", "--formats", "md,txt"]) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["owl_config", "owl_home", "sken.pdf"]
    err = capsys.readouterr().err
    assert "sken.pdf: FAILED: no pages in range 40" in err


def test_a_damaged_input_does_not_stop_the_others(tmp_path, capsys):
    install_fake_engine()
    folder = tmp_path / "in"
    folder.mkdir()
    good = make_scan_pdf(tmp_path / "whole.pdf", pages=1).read_bytes()
    (folder / "a_broken.pdf").write_bytes(good[: len(good) // 3])       # truncated, sorts first
    shutil.copy(PAGES / "01_letter_clean.png", folder / "b_dopis.png")
    assert cli.main([str(folder)]) == 1
    assert (folder / "b_dopis.md").is_file()
    assert not (folder / "a_broken.md").exists() and not (folder / "a_broken.owl.json").exists()
    assert "a_broken.pdf: FAILED:" in capsys.readouterr().err


def test_not_installed_is_exit_code_2(letter):
    assert cli.main([str(letter)]) == 2


def test_bad_arguments_are_exit_code_1(letter, tmp_path):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "html"]) == 1
    assert cli.main([str(letter), "--pages", "x"]) == 1
    assert cli.main([str(tmp_path / "nothing_here")]) == 1


@pytest.mark.parametrize("bad", [
    ["--mode", "slow"],
    ["--dpi", "abc"],
    ["--dpi", "0"],
    ["--colour", "red"],
    [],                                     # no input at all
])
def test_argument_errors_are_exit_code_1_not_2(letter, bad, capsys):
    # argparse would exit with 2, which means "engine not installed" here (ruling F1)
    install_fake_engine()
    argv = bad if bad == [] else [str(letter), *bad]
    assert cli.main(argv) == 1
    assert "error:" in capsys.readouterr().err
    assert not (letter.parent / "dopis.md").exists()


def test_help_still_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    assert "--formats" in capsys.readouterr().out


def test_word_and_searchable_pdf_are_written(letter):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "md,docx,pdf"]) == 0
    for name in ("dopis.md", "dopis.docx", "dopis.ocr.pdf"):
        assert (letter.parent / name).is_file(), name


def test_formats_not_available_are_rejected_before_any_ocr(letter, monkeypatch, capsys):
    # ruling F2 kept: a format this build cannot write is refused before the engine starts
    install_fake_engine()
    monkeypatch.setattr(cli, "FORMATS_AVAILABLE", ("md", "txt"))
    monkeypatch.setattr(cli, "default_engine", lambda: pytest.fail("the engine was started"))
    monkeypatch.setattr(cli, "process_page", lambda *a, **k: pytest.fail("a page was read"))
    for formats in ("md,docx", "pdf", "txt,pdf,docx"):
        assert cli.main([str(letter), "--formats", formats]) == 1
    assert sorted(p.name for p in letter.parent.iterdir()) == ["dopis.png"]
    assert "not available in this build" in capsys.readouterr().err


def test_missing_input_paths_are_reported_and_fail(letter, tmp_path, capsys):
    install_fake_engine()
    missing = tmp_path / "nothing_here.pdf"
    assert cli.main([str(missing), str(letter)]) == 1
    assert (letter.parent / "dopis.md").is_file()           # the existing input is still read
    err = capsys.readouterr().err
    assert f"not found: {missing}" in err


def test_only_missing_inputs_never_start_the_engine(tmp_path, monkeypatch, capsys):
    install_fake_engine()
    monkeypatch.setattr(cli, "default_engine", lambda: pytest.fail("the engine was started"))
    first, second = tmp_path / "a.png", tmp_path / "b"
    assert cli.main([str(first), str(second)]) == 1
    err = capsys.readouterr().err
    assert f"not found: {first}" in err and f"not found: {second}" in err
    assert "no supported files found" not in err


def test_engine_crash_twice_fails_the_input(letter, capsys):
    install_fake_engine("crash_on_ocr")
    assert cli.main([str(letter)]) == 1
    err = capsys.readouterr().err
    assert "restarting" in err and "FAILED" in err


def test_out_of_memory_in_quality_is_read_again_in_fast(letter):
    install_fake_engine("oom_on_quality")
    assert cli.main([str(letter)]) == 0
    page = load_sidecar(letter.parent / "dopis.owl.json").pages[0]
    assert page.mode == "fast" and page.warnings == ["out_of_memory_fast"]


def test_not_enough_graphics_memory(letter, monkeypatch):
    install_fake_engine(device="cuda")
    monkeypatch.setattr(hardware, "free_vram_mib", lambda: 4000)
    assert cli.main([str(letter)]) == 1
    monkeypatch.setattr(hardware, "free_vram_mib", lambda: 8000)
    assert cli.main([str(letter), "--mode", "fast"]) == 0
