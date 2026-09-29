"""Plan C: dictionary look-ups and suspicious-word flags (design 9)."""
import pytest

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import Block, Flag


def _block(text, label="text", flags=None):
    return Block(label=label, box=(100, 100, 900, 200), text=text, raw_text=text, flags=flags or [])


def _flagged(block):
    return [(f.kind, f.original, block.text[f.start:f.end]) for f in block.flags]


def test_dictionaries_dir_is_under_the_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "root"))
    assert spellcheck.dictionaries_dir() == tmp_path / "root" / "dictionaries"


def test_available(tiny_dicts):
    assert spellcheck.available("cs") and spellcheck.available("en")
    assert not spellcheck.available("de")


def test_nothing_available_without_files(no_dicts):
    assert not spellcheck.available("cs") and not spellcheck.available("en")


def test_known_words_and_case(tiny_dicts):
    for word in ("buď", "Buď", "BUĎ", "pojišťovnou", "Praha", "česko-slovenský"):
        assert spellcheck.known(word, "cs"), word
    for word in ("bud", "praha", "bylinny", "także", "kaktu-sovitých"):
        assert not spellcheck.known(word, "cs"), word


def test_typographic_apostrophe_is_looked_up_as_straight(tiny_dicts):
    assert spellcheck.known("doctor’s", "en") == spellcheck.known("doctor's", "en")


def test_known_is_true_without_dictionary(no_dicts):
    assert spellcheck.known("xqzt", "cs") is True


def test_lookups_are_cached(tiny_dicts, monkeypatch):
    assert spellcheck.known("strom", "cs")
    dictionary = spellcheck._dictionary("cs")
    monkeypatch.setattr(dictionary, "lookup", lambda word: pytest.fail("not cached"))
    assert spellcheck.known("strom", "cs")


def test_words_keep_czech_letters_and_skip_numbers():
    words = [w for _s, _e, w in spellcheck._words("Žluťoučký kůň, H2O, 1968, 5x, e-mail a bud'")]
    assert words == ["Žluťoučký", "kůň", "e-mail", "a", "bud"]


def test_words_ignore_html_tags():
    words = [w for _s, _e, w in spellcheck._words("<table><tr><td>Dub</td></tr></table>")]
    assert words == ["Dub"]


def test_unknown_words_are_flagged_with_offsets(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Rostlina je bylinny a sporořyly strom."), "cs", set())
    assert _flagged(out) == [("suspicious", "bylinny", "bylinny"),
                             ("suspicious", "sporořyly", "sporořyly")]
    assert out.text == "Rostlina je bylinny a sporořyly strom."


def test_capitalised_word_inside_a_sentence_is_protected(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Rod Opuntia roste. Opuntia je strom."), "cs", set())
    assert _flagged(out) == [("suspicious", "Opuntia", "Opuntia")]   # only the sentence start
    assert out.flags[0].start == 19


def test_personal_words_are_protected(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Je to bylinny strom."), "cs", {"Bylinny"})
    assert out.flags == []


def test_numbers_and_single_letters_are_not_flagged(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Strom 1968 x 25 H2O q."), "cs", set())
    assert out.flags == []


def test_foreign_letter_flag_is_not_duplicated(tiny_dicts):
    flag = Flag("foreign_letter", 6, 12, "piękný", "letter does not exist in Czech")
    out = spellcheck.flag_suspicious(_block("Je to piękný strom.", flags=[flag]), "cs", set())
    assert [f.kind for f in out.flags] == ["foreign_letter"]


def test_formula_and_image_blocks_are_skipped(tiny_dicts):
    for label in ("formula", "image", "figure"):
        block = _block("xqzt wvpl", label=label)
        assert spellcheck.flag_suspicious(block, "cs", set()) is block


def test_no_flags_without_dictionary(no_dicts):
    block = _block("xqzt wvpl")
    assert spellcheck.flag_suspicious(block, "cs", set()) is block


def test_detect_language(tiny_dicts):
    assert spellcheck.detect_language("The tree is green and the leaf is green.") == "en"
    assert spellcheck.detect_language("Rostlina je velký strom a list je malý.") == "cs"


def test_detect_language_defaults_to_czech_without_dictionaries(no_dicts):
    assert spellcheck.detect_language("The tree is green.") == "cs"


def test_detect_language_with_only_english_installed(tiny_dicts):
    (tiny_dicts / "cs_CZ.dic").unlink()
    spellcheck._reset_cache()
    assert spellcheck.detect_language("The tree is green and the leaf is green.") == "en"
    assert spellcheck.detect_language("Rostlina je velký strom a list je malý.") == "cs"


def test_corrupt_dictionary_degrades_gracefully_and_logs_a_warning(tiny_dicts, caplog):
    (tiny_dicts / "cs_CZ.aff").write_text("SET NOT-A-REAL-ENCODING\n", encoding="utf-8")
    spellcheck._reset_cache()
    with caplog.at_level("WARNING", logger="owlocr.pipeline.spellcheck"):
        assert spellcheck.known("strom", "cs") is True
    assert spellcheck.available("cs") is True   # the files are still there, only unreadable
    assert any("cs" in record.message for record in caplog.records)
    caplog.clear()
    assert spellcheck.known("dub", "cs") is True   # second lookup: no second warning
    assert caplog.records == []
