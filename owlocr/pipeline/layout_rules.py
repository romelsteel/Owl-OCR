"""Plan C layout rules used by layout.arrange (design 7.5): page furniture to the page edges,
captions out of the middle of a sentence, dictionary-aware joining of hyphenated words."""
from __future__ import annotations

import dataclasses
import re

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import FURNITURE_LABELS, Block, Flag
from owlocr.pipeline.edits import Edit, apply_edits

CAPTION_LABELS = ("image_caption", "table_caption")
FIGURE_RUN_LABELS = ("image", "figure") + CAPTION_LABELS
FLOW_LABELS = ("text", "list")
SENTENCE_PUNCTUATION = ".!?…:"
_CLOSERS = "\"'“”’»)]"
_OPENERS = "\"'„“‚‘«(["
# word, hyphen, optional line break, word: "kaktu-sovitých" or "kaktu-\nsovitých"
_SPLIT_WORD = re.compile(r"(?<![\w-])([^\W\d_]+)-(?:[ \t]*\n[ \t]*)?([^\W\d_]+)(?![\w-])")
_DEHYPHENATE_LABELS = FLOW_LABELS + CAPTION_LABELS + ("title",)
_GUESSED_JOIN = "word split by a line-break hyphen joined (not in the dictionary)"


def furniture_to_edges(blocks: list[Block]) -> list[Block]:
    """Headers (and page numbers in the upper half of the page) first, footers and the other page
    numbers last, so page furniture never splits a paragraph in exports that keep it."""
    top, middle, bottom = [], [], []
    for block in blocks:
        upper_page_number = (block.label == "page_number" and block.box is not None
                             and block.box[1] < 500)
        if block.label == "header" or upper_page_number:
            top.append(block)
        elif block.label in FURNITURE_LABELS:
            bottom.append(block)
        else:
            middle.append(block)
    return top + middle + bottom


def ends_sentence(text: str) -> bool:
    stripped = text.rstrip().rstrip(_CLOSERS).rstrip()
    return not stripped or stripped[-1] in SENTENCE_PUNCTUATION


def starts_lower(text: str) -> bool:
    stripped = text.lstrip().lstrip(_OPENERS)
    return bool(stripped) and stripped[0].islower()


def move_captions(blocks: list[Block]) -> list[Block]:
    """A run of figure/caption blocks placed in the middle of a sentence (the text block before it
    ends without sentence punctuation and the text block after it starts in lower case) is moved
    after the block that continues the sentence."""
    result = list(blocks)
    i = 0
    while i < len(result):
        if result[i].label not in FIGURE_RUN_LABELS:
            i += 1
            continue
        j = i
        while j < len(result) and result[j].label in FIGURE_RUN_LABELS:
            j += 1
        run = result[i:j]
        before, after = i - 1, j
        if (any(b.label in CAPTION_LABELS for b in run)
                and before >= 0 and after < len(result)
                and result[before].label in FLOW_LABELS and result[after].label in FLOW_LABELS
                and not ends_sentence(result[before].text) and starts_lower(result[after].text)):
            result[i:after + 1] = [result[after]] + run
            i = after + 1
        else:
            i = j
    return result


def dehyphenate(block: Block, language: str) -> Block:
    """Join a word split by a line-break hyphen when the joined word is in the dictionary and the
    hyphenated form is not. Without a dictionary nothing is joined. Each join is a Flag.

    Final review M2: at a LINE BREAK, when neither the joined nor the hyphenated form is known,
    plan A's rule decides (join when the second part starts with a lower-case letter) and the
    joined word is also flagged 'suspicious'. A hyphen inside a line is never joined that way."""
    if block.label not in _DEHYPHENATE_LABELS or "-" not in block.text:
        return block
    if not spellcheck.available(language):
        return block
    edits = []
    for m in _SPLIT_WORD.finditer(block.text):
        joined = m.group(1) + m.group(2)
        hyphenated = f"{m.group(1)}-{m.group(2)}"
        joined_known = spellcheck.known(joined, language)
        if joined_known and not spellcheck.known(hyphenated, language):
            edits.append(Edit(m.start(), m.end(), joined, "repaired",
                              "word split by a line-break hyphen joined"))
        elif ("\n" in m.group() and not joined_known and m.group(2)[0].islower()
                and not spellcheck.known(hyphenated, language)):
            edits.append(Edit(m.start(), m.end(), joined, "repaired", _GUESSED_JOIN))
    if not edits:
        return block
    text, flags = apply_edits(block.text, list(block.flags), edits)
    flags += [Flag("suspicious", f.start, f.end, text[f.start:f.end], "not in the dictionary")
              for f in flags if f.kind == "repaired" and f.note == _GUESSED_JOIN]
    flags.sort(key=lambda f: (f.start, f.end))
    return dataclasses.replace(block, text=text, flags=flags)
