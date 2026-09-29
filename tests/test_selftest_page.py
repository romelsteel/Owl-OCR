from owlocr.engine import install_kit as kit
from owlocr.engine import stages
from tests.conftest import PAGES, RAW, REPO


def test_selftest_page_is_the_letter_fixture():
    bundled = REPO / "owlocr" / "web" / "static" / "selftest.png"
    assert bundled.read_bytes() == (PAGES / "01_letter_clean.png").read_bytes()


def test_expected_words_are_on_the_page():
    truth = (PAGES / "01_letter_clean.gt.txt").read_text(encoding="utf-8")
    assert all(word in truth for word in kit.SELFTEST_WORDS)


def test_both_modes_found_the_words_in_the_spike():
    for mode in ("gundam", "base"):
        raw = (RAW / f"01_letter_clean.{mode}.raw.txt").read_text(encoding="utf-8")
        assert len(stages.selftest_words_found(raw)) >= kit.SELFTEST_MIN_WORDS, mode
