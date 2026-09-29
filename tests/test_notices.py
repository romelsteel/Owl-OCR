import sys

import pytest

from tests.conftest import REPO

sys.path.insert(0, str(REPO / "packaging"))
import notices  # noqa: E402


def test_closure_follows_dependencies():
    names = {notices.norm(d.metadata["Name"]) for d in notices.closure(("flask",))}
    assert {"flask", "werkzeug", "jinja2", "markupsafe", "itsdangerous", "click", "blinker"} <= names


def test_render_contains_summary_texts_and_model_notice():
    text = notices.render(notices.closure(("flask",)), "PSF LICENSE AGREEMENT FOR PYTHON")
    assert "| Flask |" in text and "| Werkzeug |" in text
    assert "### Flask " in text and "````text" in text
    assert "PSF LICENSE AGREEMENT FOR PYTHON" in text
    assert "Apache License" in text and "modeling_deepseekv2.py" in text
    assert "07dea832e22aefee32ad281d4b80551282e1c168" in text


def test_license_name_is_never_empty():
    for dist in notices.closure(("flask",)):
        assert notices.license_name(dist).strip()


def test_roots_come_from_requirements(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("# app\nPillow>=12.1,<13\npypdfium2>=5.10,<6  # PDF\n-r other.txt\n\nFlask>=3\n", encoding="utf-8")
    assert notices.roots_from_requirements(req) == ("Pillow", "pypdfium2", "Flask")


def test_engine_packages_are_refused_as_roots(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("torch==2.10.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="engine packages"):
        notices.roots_from_requirements(req)


def test_committed_notices_cover_every_requirement():
    text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    rows = {notices.norm(line.split("|")[1].strip()) for line in text.splitlines() if line.startswith("| ")}
    for root in notices.roots_from_requirements():
        assert notices.norm(root) in rows, root
    assert "pyinstaller" in rows


def test_fonts_are_listed_with_their_licence(tmp_path):
    licence = tmp_path / "owlocr" / "export" / "fonts" / "DejaVuSans-LICENSE.txt"
    licence.parent.mkdir(parents=True)
    licence.write_text("Bitstream Vera Fonts Copyright ... public domain", encoding="utf-8")
    fonts = notices.font_notices(tmp_path)
    text = notices.render(notices.closure(("flask",)), "", fonts)
    assert "| DejaVu Sans (font) | 2.37 |" in text
    assert "### DejaVu Sans 2.37 (font)" in text and "Bitstream Vera" in text


def test_committed_notices_list_the_plan_c_packages_font_and_dictionaries():
    text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    rows = {notices.norm(line.split("|")[1].strip()) for line in text.splitlines() if line.startswith("| ")}
    assert {"spylls", "pikepdf", "reportlab", "python-docx", "numpy", "dejavu sans (font)",
            "flask", "pywebview", "pythonnet"} <= rows
    assert "LibreOffice dictionaries" in text and "SCOWL" in text
    assert "WebView2" in text


def _summary_row(text, name):
    return next(line for line in text.splitlines() if line.startswith(f"| {name} |"))


def test_committed_notices_state_the_corrected_licences_and_sources():
    """M-6: bootloader exception, clr_loader MIT, charset-normalizer source, proxy_tools author."""
    text = (REPO / "packaging" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "GPLv2 with bootloader exception" in _summary_row(text, "pyinstaller")
    assert "| MIT |" in _summary_row(text, "clr_loader")
    assert "https://github.com/jawah/charset_normalizer" in _summary_row(text, "charset-normalizer")
    assert "Licence: MIT License, stated in the package metadata (author: Jonathan Tushman)." in text


def test_overrides_are_keyed_by_normalised_names():
    for key in (*notices.LICENSE_OVERRIDES, *notices.SOURCE_OVERRIDES):
        assert key == notices.norm(key)
