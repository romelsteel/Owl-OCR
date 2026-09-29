"""Rule-based corrections of known OCR error types (design 9.2 and the table of section 9).

Character rules R3, R4, R5 always run. Word repairs (R1, plain d/t -> ď/ť, R2 look-alikes) run
only for Czech with the dictionary installed, and only when the result is a dictionary word and
the original is not (design 9.1 point 1). R2 flags foreign letters even without a dictionary.
Every change becomes a Flag of kind 'repaired' whose `original` is the text before the change.
"""
from __future__ import annotations

import dataclasses
import itertools
import re

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import Block, Flag
from owlocr.pipeline.edits import Edit, apply_edits

CZECH_LETTERS = frozenset("áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ")

# Letters from other alphabets -> Czech (or plain) letters that look alike, most likely first.
LOOK_ALIKE: dict[str, tuple[str, ...]] = {
    "ż": ("ž", "z"), "ź": ("ž", "z"), "Ż": ("Ž", "Z"), "Ź": ("Ž", "Z"),
    "ł": ("l",), "Ł": ("L",), "ľ": ("l", "ť"), "Ľ": ("L", "Ť"), "ĺ": ("l",),
    "ą": ("a", "á"), "ę": ("ě", "e", "é"), "ė": ("ě", "e"), "ć": ("č", "c"), "ś": ("š", "s"),
    "ń": ("ň", "n"), "ñ": ("ň", "n"), "ŕ": ("ř", "r"), "Ś": ("Š", "S"), "Ć": ("Č", "C"),
    "ő": ("ó", "o"), "ű": ("ů", "ú"), "ö": ("ó", "o"), "ü": ("ů", "ú"), "ä": ("á", "a"),
    "ë": ("é", "ě"), "à": ("á", "a"), "è": ("é", "ě"), "ì": ("í", "i"), "ò": ("ó", "o"),
    "ù": ("ú", "ů"), "â": ("á", "a"), "ê": ("ě", "é"), "î": ("í", "i"), "ô": ("ó", "o"),
    "û": ("ů", "ú"), "ÿ": ("ý", "y"), "ã": ("á", "a"), "õ": ("ó", "o"), "ç": ("č", "c"),
    "ğ": ("g",), "ş": ("š", "s"), "ı": ("i",), "ŭ": ("ů", "u"),
}
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_SOFTEN = {"d": "ď", "t": "ť", "D": "Ď", "T": "Ť"}
# "bud" is a real dictionary word (imperative of být) but bud'/Bud' almost always means the
# conjunction buď: never let the closing-quote guard below block its repair.
_BUD_EXCEPTION = frozenset({"bud", "Bud"})

_LIGATURE = re.compile("[" + "".join(LIGATURES) + "]")
_LOW_QUOTE = re.compile(",,")
_DASH = re.compile(r"(?<=\w) - (?=\w)")
# a word containing d' or t' (straight or typographic apostrophe), e.g. bud' or pojišt’ovnou
_APOSTROPHE_WORD = re.compile(r"(?<![\w'’])[^\W\d_]*[dDtT]['’][^\W\d_]*(?![\w'’])")
_SKIP_LABELS = ("formula", "image", "figure")
_MAX_CANDIDATES = 64


def _is_foreign(ch: str) -> bool:
    return ch.isalpha() and not (ch.isascii() or ch in CZECH_LETTERS)


def _char_rules(text: str) -> list[Edit]:
    """R5 ligatures, R4 low quote, R3 dash. Offsets refer to `text`; tags are never touched."""
    masked = spellcheck._mask_tags(text)
    edits = [Edit(m.start(), m.end(), LIGATURES[m.group()], "repaired", "R5: ligature")
             for m in _LIGATURE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), "„", "repaired", "R4: ,, is a low quotation mark")
              for m in _LOW_QUOTE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), " – ", "repaired", "R3: hyphen between spaces is a dash")
              for m in _DASH.finditer(masked)]
    return edits


def _first_known(candidates, original: str, language: str) -> str | None:
    for candidate in itertools.islice(candidates, _MAX_CANDIDATES):
        if candidate != original and spellcheck.known_strict(candidate, language):
            return candidate
    return None


def _unique_known(candidates, original: str, language: str) -> str | None:
    """The single distinct known candidate; None when zero or more than one are known."""
    found = None
    for candidate in itertools.islice(candidates, _MAX_CANDIDATES):
        if candidate == original or not spellcheck.known_strict(candidate, language):
            continue
        if found is not None and candidate != found:
            return None
        found = candidate
    return found


def _apostrophe_candidates(word: str):
    """R1: every d'/t' (straight or typographic apostrophe) becomes ď/ť."""
    yield re.sub(r"([dDtT])['’]", lambda m: _SOFTEN[m.group(1)], word)


def _soft_candidates(word: str):
    """Variants with one or more d/t replaced by ď/ť; single replacements first."""
    positions = [i for i, ch in enumerate(word) if ch in _SOFTEN][:4]
    for size in range(1, len(positions) + 1):
        for chosen in itertools.combinations(positions, size):
            letters = list(word)
            for i in chosen:
                letters[i] = _SOFTEN[letters[i]]
            yield "".join(letters)


def _look_alike_candidates(word: str):
    options = [LOOK_ALIKE.get(ch, (ch,)) if _is_foreign(ch) else (ch,) for ch in word]
    for letters in itertools.product(*options):
        yield "".join(letters)


def _word_rules(text: str, language: str,
                personal_lower: set[str]) -> tuple[list[Edit], list[Flag]]:
    """R1, plain d/t, R2. Returns edits and the 'foreign_letter' flags (offsets in `text`)."""
    masked = spellcheck._mask_tags(text)
    have_dictionary = spellcheck.available(language)
    edits: list[Edit] = []
    foreign: list[Flag] = []
    covered: list[tuple[int, int]] = []

    if have_dictionary:
        for m in _APOSTROPHE_WORD.finditer(masked):
            word = m.group()
            if spellcheck._protected(word, text, m.start(), personal_lower):
                continue
            # The apostrophe is the last character: nothing word-like follows it, so it may be a
            # closing quote after a real word ('nový plat') rather than d'/t' inside one. Only
            # treat it as d'/t' when the word without the apostrophe is not already a dictionary
            # word itself (bud'/Bud' is the one standing exception: it is almost always ď).
            if (word[-1] in "'’" and word[:-1] not in _BUD_EXCEPTION
                    and spellcheck.known(word[:-1], language)):
                continue
            fixed = _unique_known(_apostrophe_candidates(word), word, language)
            if fixed:
                edits.append(Edit(m.start(), m.end(), fixed, "repaired",
                                  "R1: letter + apostrophe is ď/ť"))
                covered.append((m.start(), m.end()))

    for start, end, word in spellcheck._words(text):
        if any(s < end and start < e for s, e in covered):
            continue
        if spellcheck._protected(word, text, start, personal_lower):
            continue
        if any(_is_foreign(ch) for ch in word):
            fixed = None
            if have_dictionary and not spellcheck.known(word, language):
                fixed = _first_known(_look_alike_candidates(word), word, language)
            if fixed:
                edits.append(Edit(start, end, fixed, "repaired",
                                  "R2: foreign letter replaced by its Czech look-alike"))
            elif not (have_dictionary and spellcheck.known(word, language)):
                foreign.append(Flag("foreign_letter", start, end, word,
                                    "letter does not exist in Czech"))
            continue
        if (have_dictionary and any(ch in _SOFTEN for ch in word)
                and not spellcheck.known(word, language)):
            fixed = _unique_known(_soft_candidates(word), word, language)
            if fixed:
                edits.append(Edit(start, end, fixed, "repaired", "d/t without its háček"))
    return edits, foreign


def repair_block(block: Block, language: str, personal_words: set[str]) -> Block:
    if block.label in _SKIP_LABELS or not block.text:
        return block
    text, flags = apply_edits(block.text, list(block.flags), _char_rules(block.text))
    if language == "cs":
        personal_lower = spellcheck._personal_lower(personal_words)
        edits, foreign = _word_rules(text, language, personal_lower)
        text, flags = apply_edits(text, flags + foreign, edits)
    if text == block.text and flags == block.flags:
        return block
    return dataclasses.replace(block, text=text, flags=flags)
