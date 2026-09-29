"""Reading order and line-break hyphens (design 7.5).

Plan A (basic): the model's block order is kept, and a word split by a hyphen at a line break
(`kaktu-\\nsovitých`) is joined when the second part starts with a lower-case letter.
Plan C adds the caption move and the dictionary-aware join of `kaktu-sovitých` without a line break.
"""
import dataclasses
import re

from owlocr.pipeline.document import Block
from owlocr.pipeline import layout_rules
from owlocr.pipeline import spellcheck

_LINE_BREAK_HYPHEN = re.compile(r"([^\W\d_])-[ \t]*\n[ \t]*([^\W\d_])")


def _join(match: re.Match) -> str:
    before, after = match.group(1), match.group(2)
    if after.islower():
        return before + after
    return match.group(0)             # "Česko-\nSlovensko" keeps its hyphen and line break


def _dehyphenate(text: str) -> str:
    return _LINE_BREAK_HYPHEN.sub(_join, text)


_NO_DEHYPHENATE_LABELS = ("table", "formula")   # joining "x-\ny" into "xy" would change the math


def _arrange_basic(blocks: list[Block], language: str = "cs") -> list[Block]:
    arranged = []
    for block in blocks:
        if block.label in _NO_DEHYPHENATE_LABELS:
            arranged.append(block)
            continue
        text = _dehyphenate(block.text)
        arranged.append(block if text == block.text else dataclasses.replace(block, text=text))
    return arranged


def arrange(blocks: list[Block], language: str = "cs") -> list[Block]:
    """Design 7.5. Without a dictionary plan A's rule joins a line-break hyphen when a lower-case
    letter follows; with a dictionary layout_rules.dehyphenate decides for both forms
    (kaktu- at the end of a line and kaktu-sovitých in one line) and records each join as a Flag."""
    if not spellcheck.available(language):
        blocks = _arrange_basic(blocks, language)
    blocks = layout_rules.furniture_to_edges(blocks)
    blocks = layout_rules.move_captions(blocks)
    return [layout_rules.dehyphenate(block, language) for block in blocks]
