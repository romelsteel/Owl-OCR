from owlocr.pipeline import layout, repair, spellcheck
from owlocr.pipeline.document import Block


def block(text: str, label: str = "text") -> Block:
    return Block(label=label, box=(0, 0, 10, 10), text=text, raw_text=text, flags=[])


def test_order_is_kept_and_unchanged_blocks_are_the_same_objects():
    blocks = [block("první"), block("druhý", "title"), block("třetí")]
    arranged = layout.arrange(blocks)
    assert [b.text for b in arranged] == ["první", "druhý", "třetí"]
    assert all(a is b for a, b in zip(arranged, blocks))


def test_line_break_hyphen_is_joined():
    (b,) = layout.arrange([block("rostliny kaktu-\nsovitých rostou")])
    assert b.text == "rostliny kaktusovitých rostou"
    assert b.raw_text == "rostliny kaktu-\nsovitých rostou"


def test_hyphen_with_spaces_around_the_break():
    (b,) = layout.arrange([block("děle- \n  ní buněk")])
    assert b.text == "dělení buněk"


def test_capital_after_the_break_keeps_the_hyphen():
    (b,) = layout.arrange([block("Česko-\nSlovensko")])
    assert b.text == "Česko-\nSlovensko"


def test_hyphen_inside_a_line_and_numbers_stay():
    (b,) = layout.arrange([block("ATP-syntáza a 4.-19. září a 12-\n15")])
    assert b.text == "ATP-syntáza a 4.-19. září a 12-\n15"


def test_tables_are_left_alone():
    table = block("<table><tr><td>kaktu-\nsovitý</td></tr></table>", "table")
    assert layout.arrange([table]) == [table]


def test_formulas_are_left_alone():
    formula = block("x-\ny = 1", "formula")
    assert layout.arrange([formula]) == [formula]


def test_repair_and_spellcheck_stubs():
    b = block("bud'")
    assert repair.repair_block(b, "cs", set()) is b
    assert spellcheck.flag_suspicious(b, "cs", {"x"}) is b
    assert spellcheck.available("cs") is False
    assert spellcheck.known("slovo", "cs") is True
    assert spellcheck.detect_language("The quick brown fox") == "cs"


def test_dictionaries_dir(owl_env):
    assert spellcheck.dictionaries_dir() == owl_env["home"] / "dictionaries"
