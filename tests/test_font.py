"""Plan C: the bundled font for the invisible text layer."""
import hashlib
from pathlib import Path

from reportlab.pdfbase.ttfonts import TTFont

FONTS = Path(__file__).parent.parent / "owlocr" / "export" / "fonts"
DEJAVU_SHA256 = "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954"


def test_font_file_is_the_pinned_dejavu_sans():
    data = (FONTS / "DejaVuSans.ttf").read_bytes()
    assert hashlib.sha256(data).hexdigest() == DEJAVU_SHA256


def test_font_licence_travels_with_the_font():
    licence = (FONTS / "DejaVuSans-LICENSE.txt").read_text(encoding="utf-8")
    assert "Bitstream Vera" in licence and "public domain" in licence


def test_font_has_every_czech_letter():
    face = TTFont("OwlTestFont", str(FONTS / "DejaVuSans.ttf")).face
    letters = "ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ„“–"
    assert all(ord(ch) in face.charToGlyph for ch in letters)
