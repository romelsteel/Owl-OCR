"""Plan C: caption move, furniture order and dictionary-aware de-hyphenation (design 7.5)."""
from owlocr.pipeline.document import Block
from owlocr.pipeline.layout import arrange


def _b(label, text, box=(100, 100, 900, 200)):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def _texts(blocks):
    return [(b.label, b.text) for b in blocks]


def test_caption_in_mid_sentence_moves_after_the_paragraph(no_dicts):
    blocks = [
        _b("text", "Listy rostou na stonku a jsou", (100, 100, 900, 200)),
        _b("image", "", (100, 210, 900, 400)),
        _b("image_caption", "Obr. 3 List kapradí", (100, 410, 900, 440)),
        _b("text", "střídavé nebo vstřícné.", (100, 450, 900, 550)),
        _b("text", "Další odstavec.", (100, 560, 900, 650)),
    ]
    out = arrange(blocks, "cs")
    assert _texts(out) == [
        ("text", "Listy rostou na stonku a jsou"),
        ("text", "střídavé nebo vstřícné."),
        ("image", ""),
        ("image_caption", "Obr. 3 List kapradí"),
        ("text", "Další odstavec."),
    ]


def test_caption_after_finished_sentence_stays(no_dicts):
    blocks = [
        _b("text", "Listy jsou střídavé.", (100, 100, 900, 200)),
        _b("image_caption", "Obr. 3 List", (100, 210, 900, 240)),
        _b("text", "dále platí, že ...", (100, 250, 900, 350)),
    ]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_caption_before_capitalised_sentence_stays(no_dicts):
    blocks = [
        _b("text", "Listy jsou střídavé a", (100, 100, 900, 200)),
        _b("image_caption", "Obr. 3 List", (100, 210, 900, 240)),
        _b("text", "Další věta začíná velkým písmenem.", (100, 250, 900, 350)),
    ]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_image_without_caption_is_not_moved(no_dicts):
    blocks = [_b("text", "Listy jsou", (100, 100, 900, 200)), _b("image", "", (100, 210, 900, 400)),
              _b("text", "střídavé.", (100, 410, 900, 500))]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_furniture_goes_to_the_edges(no_dicts):
    blocks = [
        _b("text", "První odstavec."),
        _b("page_number", "12", (480, 950, 520, 970)),
        _b("header", "Kapitola 2", (100, 20, 900, 40)),
        _b("text", "Druhý odstavec."),
        _b("footer", "Učebnice botaniky", (100, 960, 900, 980)),
    ]
    out = arrange(blocks, "cs")
    assert [b.label for b in out] == ["header", "text", "text", "page_number", "footer"]


def test_page_number_at_the_top_stays_at_the_top(no_dicts):
    blocks = [_b("page_number", "7", (480, 20, 520, 40)), _b("text", "Text.")]
    assert [b.label for b in arrange(blocks, "cs")] == ["page_number", "text"]


def test_hyphen_inside_line_joined_when_joined_word_is_known(tiny_dicts):
    out = arrange([_b("text", "Čeleď kaktu-sovitých je velká.")], "cs")
    assert out[0].text == "Čeleď kaktusovitých je velká."
    flag = out[0].flags[0]
    assert (flag.kind, flag.original, out[0].text[flag.start:flag.end]) == (
        "repaired", "kaktu-sovitých", "kaktusovitých")


def test_hyphen_at_line_break_joined(tiny_dicts):
    out = arrange([_b("text", "Čeleď kaktu-\nsovitých je velká.")], "cs")
    assert out[0].text == "Čeleď kaktusovitých je velká."


def test_real_compound_keeps_its_hyphen(tiny_dicts):
    out = arrange([_b("text", "Je to česko-slovenský text.")], "cs")
    assert out[0].text == "Je to česko-slovenský text."
    assert out[0].flags == []


def test_no_joining_without_dictionary(no_dicts):
    out = arrange([_b("text", "Čeleď kaktu-sovitých.")], "cs")
    assert out[0].text == "Čeleď kaktu-sovitých."


def test_raw_text_is_kept(tiny_dicts):
    out = arrange([_b("text", "kaktu-sovitých")], "cs")
    assert out[0].raw_text == "kaktu-sovitých"


def test_with_a_dictionary_a_line_break_join_needs_the_dictionary(tiny_dicts):
    # plan A alone would join this into "československý"; the dictionary knows the hyphenated form
    out = arrange([_b("text", "Je to česko-\nslovenský text.")], "cs")
    assert out[0].text == "Je to česko-\nslovenský text."


# ---- final review M2: unknown joined word at a line break --------------------------------------

def test_unknown_word_at_a_line_break_is_joined_by_plan_a_rule_and_flagged(tiny_dicts):
    from owlocr.pipeline import spellcheck
    out = arrange([_b("text", "Je to slo-\nvo a list.")], "cs")
    assert out[0].text == "Je to slovo a list."
    assert [(f.kind, f.start, f.end, f.original) for f in out[0].flags] == [
        ("repaired", 6, 11, "slo-\nvo"), ("suspicious", 6, 11, "slovo")]
    flagged = spellcheck.flag_suspicious(out[0], "cs", set())
    assert flagged.flags == out[0].flags                      # flagged once, not twice


def test_unknown_word_at_a_line_break_before_a_capital_keeps_its_hyphen(tiny_dicts):
    out = arrange([_b("text", "Je to slo-\nVo a list.")], "cs")
    assert out[0].text == "Je to slo-\nVo a list." and out[0].flags == []


def test_unknown_hyphenated_word_inside_a_line_is_not_joined(tiny_dicts):
    out = arrange([_b("text", "Je to slo-vo a list.")], "cs")
    assert out[0].text == "Je to slo-vo a list." and out[0].flags == []
