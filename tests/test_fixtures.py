"""The fixture pages and the recorded model output of the spike."""
from tests.conftest import PAGES, RAW

NAMES = ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
         "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo", "08_screenshot",
         "09_letter_rotated_90", "10_blank_page")


def test_ten_pages_with_ground_truth():
    assert sorted(p.name for p in PAGES.iterdir()) == sorted(
        [f"{n}.png" for n in NAMES] + [f"{n}.gt.txt" for n in NAMES])


def test_recorded_raw_output_of_the_synthetic_pages_only():
    assert sorted(p.name for p in RAW.iterdir()) == sorted(
        [f"{n}.gundam.raw.txt" for n in NAMES] + [f"{n}.base.raw.txt" for n in NAMES])
    assert not [p for p in RAW.parent.rglob("*") if p.name.lower().startswith("sample")]


def test_ground_truth_is_utf8_czech():
    assert "Šťastná" in (PAGES / "01_letter_clean.gt.txt").read_text(encoding="utf-8")
    assert (PAGES / "10_blank_page.gt.txt").read_text(encoding="utf-8").strip() == ""
