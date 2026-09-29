"""Plan C: rule-based repairs (design 9.2), cases taken from the spike's measured errors."""
from owlocr.pipeline.document import Block
from owlocr.pipeline.repair import repair_block


def _block(text, label="text"):
    return Block(label=label, box=(100, 100, 900, 200), text=text, raw_text=text, flags=[])


def _repaired(block):
    return [(f.original, block.text[f.start:f.end]) for f in block.flags if f.kind == "repaired"]


def test_r3_hyphen_between_spaces_becomes_en_dash(no_dicts):
    out = repair_block(_block("Dub - strom, 4 - 19 září, a-b"), "cs", set())
    assert out.text == "Dub – strom, 4 – 19 září, a-b"
    assert [f.original for f in out.flags] == [" - ", " - "]


def test_r4_double_comma_becomes_low_quote(no_dicts):
    out = repair_block(_block("Řekl: ,,Dnes ne.“"), "cs", set())
    assert out.text == "Řekl: „Dnes ne.“"
    flag = out.flags[0]
    assert (flag.original, out.text[flag.start:flag.end]) == (",,", "„")


def test_r5_ligatures_become_plain_letters(no_dicts):
    out = repair_block(_block("proﬁl a ﬂóra, eﬀekt"), "en", set())
    assert out.text == "profil a flóra, effekt"
    assert [f.original for f in out.flags] == ["ﬁ", "ﬂ", "ﬀ"]


def test_formula_block_is_never_changed(tiny_dicts):
    block = _block("a - b = c", label="formula")
    assert repair_block(block, "cs", set()) is block


def test_r1_straight_apostrophe_becomes_d_caron(tiny_dicts):
    out = repair_block(_block("Rostlina je bud' velký strom, nebo malý stonek."), "cs", set())
    assert out.text == "Rostlina je buď velký strom, nebo malý stonek."
    assert _repaired(out) == [("bud'", "buď")]
    assert out.raw_text == "Rostlina je bud' velký strom, nebo malý stonek."


def test_r1_typographic_apostrophe_inside_word(tiny_dicts):
    out = repair_block(_block("Účet byl uhrazen pojišt’ovnou."), "cs", set())
    assert out.text == "Účet byl uhrazen pojišťovnou."
    assert _repaired(out) == [("pojišt’ovnou", "pojišťovnou")]


def test_r1_capital_at_sentence_start_is_repaired(tiny_dicts):
    out = repair_block(_block("Bud' strom, nebo keř."), "cs", set())
    assert out.text.startswith("Buď strom")


def test_r1_not_applied_when_result_unknown(tiny_dicts):
    out = repair_block(_block("Řekl 'jdeme spát' a odešel."), "cs", set())
    assert out.text == "Řekl 'jdeme spát' a odešel."
    assert _repaired(out) == []


def test_word_repairs_skipped_without_dictionary(no_dicts):
    out = repair_block(_block("Je to bud' strom a kaprad."), "cs", set())
    assert out.text == "Je to bud' strom a kaprad."
    assert out.flags == []


def test_plain_d_becomes_d_caron_when_only_that_is_a_word(tiny_dicts):
    out = repair_block(_block("Druh kaprad roste dole."), "cs", set())
    assert out.text == "Druh kapraď roste dole."
    assert _repaired(out) == [("kaprad", "kapraď")]


def test_known_word_with_d_is_left_alone(tiny_dicts):
    out = repair_block(_block("Roste tam dub a buk."), "cs", set())
    assert out.text == "Roste tam dub a buk."


def test_r2_foreign_letter_repaired_to_known_look_alike(tiny_dicts):
    out = repair_block(_block("Je to także velký strom."), "cs", set())
    assert out.text == "Je to takže velký strom."
    assert _repaired(out) == [("także", "takže")]


def test_r2_foreign_letter_flagged_when_no_look_alike_is_known(tiny_dicts):
    out = repair_block(_block("Je to piękný strom."), "cs", set())
    assert out.text == "Je to piękný strom."
    assert [(f.kind, f.original) for f in out.flags] == [("foreign_letter", "piękný")]
    flag = out.flags[0]
    assert out.text[flag.start:flag.end] == "piękný"


def test_r2_flags_even_without_dictionary(no_dicts):
    out = repair_block(_block("Je to także strom."), "cs", set())
    assert out.text == "Je to także strom."
    assert [(f.kind, f.original) for f in out.flags] == [("foreign_letter", "także")]


def test_r2_capitalised_name_inside_sentence_is_protected(tiny_dicts):
    out = repair_block(_block("Dopis pro pana Wałęsu je dole."), "cs", set())
    assert out.flags == []


def test_personal_word_list_protects(tiny_dicts):
    out = repair_block(_block("Je to także strom."), "cs", {"Także"})
    assert out.text == "Je to także strom."
    assert out.flags == []


def test_offsets_stay_right_after_several_length_changes(tiny_dicts):
    text = "Řekl: ,,Je to bud' ﬁkus - nebo kaprad."
    out = repair_block(_block(text), "cs", set())
    assert out.text == "Řekl: „Je to buď fikus – nebo kapraď."
    pairs = [(f.original, out.text[f.start:f.end]) for f in out.flags]
    assert pairs == [(",,", "„"), ("bud'", "buď"), ("ﬁ", "fi"), (" - ", " – "), ("kaprad", "kapraď")]


def test_english_gets_no_czech_word_rules(tiny_dicts):
    out = repair_block(_block("that’s the doctor’s letter"), "en", set())
    assert out.text == "that’s the doctor’s letter"


def test_table_html_is_not_touched_but_cells_are(tiny_dicts):
    html = "<table><tr><td>bud'</td><td>a - b</td></tr></table>"
    out = repair_block(_block(html, label="table"), "cs", set())
    assert out.text == "<table><tr><td>buď</td><td>a – b</td></tr></table>"


def test_r1_closing_quote_after_real_word_is_not_repaired(tiny_dicts):
    from tests.conftest import TINY_CS_WORDS, _write_tiny_dictionary
    from owlocr.pipeline import spellcheck
    _write_tiny_dictionary(tiny_dicts, "cs_CZ", TINY_CS_WORDS + ["plat", "plať"])
    spellcheck._reset_cache()

    out = repair_block(_block("Dostali jsme 'nový plat' včas."), "cs", set())
    assert out.text == "Dostali jsme 'nový plat' včas."
    assert _repaired(out) == []

    out2 = repair_block(_block("Dostali jsme \u2018nový plat\u2019 včas."), "cs", set())
    assert out2.text == "Dostali jsme \u2018nový plat\u2019 včas."
    assert _repaired(out2) == []


def test_r1_apostrophe_in_middle_of_word_still_repaired(tiny_dicts):
    out = repair_block(_block("Účet byl uhrazen pojišt’ovnou."), "cs", set())
    assert out.text == "Účet byl uhrazen pojišťovnou."
    assert _repaired(out) == [("pojišt’ovnou", "pojišťovnou")]


def test_bud_exception_still_repairs_despite_being_a_real_word(tiny_dicts):
    # In the real cs_CZ dictionary "bud" is itself a known word (imperative of být); make that
    # true here too, so this test actually exercises the _BUD_EXCEPTION bypass instead of relying
    # on the tiny dictionary happening not to know "bud".
    from tests.conftest import TINY_CS_WORDS, _write_tiny_dictionary
    from owlocr.pipeline import spellcheck
    _write_tiny_dictionary(tiny_dicts, "cs_CZ", TINY_CS_WORDS + ["bud"])
    spellcheck._reset_cache()

    out = repair_block(_block("Rostlina je bud' velký strom."), "cs", set())
    assert out.text == "Rostlina je buď velký strom."
    assert _repaired(out) == [("bud'", "buď")]


def test_ambiguous_d_t_repair_is_skipped(tiny_dicts):
    from tests.conftest import TINY_CS_WORDS, _write_tiny_dictionary
    from owlocr.pipeline import spellcheck
    _write_tiny_dictionary(tiny_dicts, "cs_CZ", TINY_CS_WORDS + ["ťod", "toď"])
    spellcheck._reset_cache()

    out = repair_block(_block("Bylo to tod dnes."), "cs", set())
    assert out.text == "Bylo to tod dnes."
    assert _repaired(out) == []


# ---- final review M3: a failed look-up never makes a repair ------------------------------------

class _BrokenDictionary:
    def lookup(self, word):
        raise RuntimeError("broken affix rule")


def test_a_failed_lookup_is_not_known_for_repairs(tiny_dicts, monkeypatch):
    from owlocr.pipeline import spellcheck
    monkeypatch.setattr(spellcheck, "_dictionary", lambda language: _BrokenDictionary())
    assert spellcheck.known("buď", "cs") is True              # flags: no false alarm
    assert spellcheck.known_strict("buď", "cs") is False      # repairs: not a dictionary word
    block = Block("text", None, "Je to bud' strom.", "Je to bud' strom.", [])
    assert repair_block(block, "cs", set()).text == "Je to bud' strom."


def test_known_strict_follows_the_dictionary(tiny_dicts):
    from owlocr.pipeline import spellcheck
    assert spellcheck.known_strict("strom", "cs") is True
    assert spellcheck.known_strict("xqzt", "cs") is False


def test_known_strict_without_a_dictionary_knows_nothing(no_dicts):
    from owlocr.pipeline import spellcheck
    assert spellcheck.known_strict("strom", "cs") is False
