"""Plan C: text edits that keep Flag offsets right."""
from owlocr.pipeline.document import Flag
from owlocr.pipeline.edits import Edit, apply_edits


def test_single_edit_records_a_flag_with_the_original():
    text, flags = apply_edits("je to bud' tak", [], [Edit(6, 10, "buď", "repaired", "R1")])
    assert text == "je to buď tak"
    assert flags == [Flag("repaired", 6, 9, "bud'", "R1")]


def test_later_flags_shift_by_the_length_change():
    old = [Flag("suspicious", 10, 15, "slovo", "x")]
    text, flags = apply_edits("ab ,, cd  slovo", old, [Edit(3, 5, "„", "repaired", "R4")])
    assert text == "ab „ cd  slovo"
    moved = [f for f in flags if f.kind == "suspicious"][0]
    assert text[moved.start:moved.end] == "slovo"


def test_several_edits_of_different_lengths():
    edits = [Edit(0, 1, "fi", "repaired", "R5"), Edit(4, 7, " – ", "repaired", "R3"),
             Edit(10, 12, "„", "repaired", "R4")]
    text, flags = apply_edits("ﬁ ab - cd ,,x", [], edits)
    assert text == "fi ab – cd „x"
    assert [(f.original, text[f.start:f.end]) for f in flags] == [
        ("ﬁ", "fi"), (" - ", " – "), (",,", "„")]


def test_flag_containing_an_edit_grows_with_it():
    old = [Flag("repaired", 0, 8, "abcdefgh", "outer")]
    text, flags = apply_edits("abcdefgh", old, [Edit(2, 4, "XYZW", "repaired", "inner")])
    outer = [f for f in flags if f.note == "outer"][0]
    assert text == "abXYZWefgh" and (outer.start, outer.end) == (0, 10)


def test_overlapping_edit_is_dropped():
    text, flags = apply_edits("abcdef", [], [Edit(0, 3, "X", "repaired", "a"),
                                             Edit(2, 4, "Y", "repaired", "b")])
    assert text == "Xdef" and [f.note for f in flags] == ["a"]


def test_no_edits_returns_the_same_text():
    old = [Flag("suspicious", 0, 3, "abc", "x")]
    assert apply_edits("abc", old, []) == ("abc", old)
