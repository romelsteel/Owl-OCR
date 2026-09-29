"""Hunspell dictionary look-ups through spylls and flags for suspicious words (design 9).

Without a dictionary every function degrades gracefully: known() says True, nothing is flagged.
"""
from __future__ import annotations

import dataclasses
import logging
import re
import threading
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Block, Flag

log = logging.getLogger(__name__)

DICTIONARY_NAMES = {"cs": "cs_CZ", "en": "en_US"}

# A word: letters of any alphabet (Czech included), optionally joined by a hyphen or an
# apostrophe. A letter run that touches a digit or an underscore is not a word ("H2O", "5x").
_WORD = re.compile(r"(?<![\w'’-])[^\W\d_]+(?:[-'’][^\W\d_]+)*(?!\w)")
_TAG = re.compile(r"<[^>]*>")
_SENTENCE_END = ".!?…"
_OPENERS = "\"'„“”‚‘’«»([{–—-*•"
_SKIP_LABELS = ("formula", "image", "figure")
_MIN_WORD = 2
_RATE_WORDS = 300

_lock = threading.RLock()
_dictionaries: dict[tuple[str, str], object] = {}
_lookups: dict[tuple[str, str, str], object] = {}   # bool or _FAILED


def dictionaries_dir() -> Path:
    return paths.data_root() / "dictionaries"


def _files(language: str) -> tuple[Path, Path] | None:
    name = DICTIONARY_NAMES.get(language)
    if name is None:
        return None
    folder = dictionaries_dir()
    return folder / f"{name}.aff", folder / f"{name}.dic"


def available(language: str) -> bool:
    files = _files(language)
    return files is not None and files[0].is_file() and files[1].is_file()


def _reset_cache() -> None:
    """Forget loaded dictionaries and cached look-ups (after a download, and in tests)."""
    with _lock:
        _dictionaries.clear()
        _lookups.clear()


def _dictionary(language: str):
    """The loaded spylls Dictionary, or None when it is not installed or cannot be read."""
    if not available(language):
        return None
    aff, _dic = _files(language)
    key = (str(aff.parent), language)
    with _lock:
        if key not in _dictionaries:
            from spylls.hunspell import Dictionary
            try:
                _dictionaries[key] = Dictionary.from_files(str(aff.with_suffix("")))
            except Exception as exc:  # a damaged file must not stop OCR: behave as "no dictionary"
                log.warning("could not load the %s dictionary (%s): %s", language, aff, exc)
                _dictionaries[key] = None      # cached: logged once per language, not per word
        return _dictionaries[key]


_FAILED = "failed"          # cached look-up result: spylls raised for this word


def _lookup(word: str, language: str):
    """True/False from the dictionary, None without a dictionary, _FAILED when spylls raised."""
    dictionary = _dictionary(language)
    if dictionary is None:
        return None
    key = (str(dictionaries_dir()), language, word)
    with _lock:
        hit = _lookups.get(key)
        if hit is None:
            try:
                hit = bool(dictionary.lookup(word))
            except Exception as exc:
                log.debug("lookup failed for %r (%s): %s", word, language, exc)
                hit = _FAILED
            _lookups[key] = hit
        return hit


def known(word: str, language: str) -> bool:
    """For flags and hit rates: a word the dictionary cannot judge counts as known."""
    word = word.replace("’", "'").strip()
    if not word:
        return True
    hit = _lookup(word, language)
    return True if hit is None or hit == _FAILED else hit


def known_strict(word: str, language: str) -> bool:
    """For repairs (final review M3): only a word the dictionary really knows; without a
    dictionary, or when the look-up fails, the word is not known."""
    word = word.replace("’", "'").strip()
    return bool(word) and _lookup(word, language) is True


def _mask_tags(text: str) -> str:
    """Replace HTML and model tags by spaces of the same length, so offsets stay valid."""
    return _TAG.sub(lambda m: " " * len(m.group()), text)


def _words(text: str) -> list[tuple[int, int, str]]:
    """(start, end, word) for every word of the text; tags are ignored."""
    return [(m.start(), m.end(), m.group()) for m in _WORD.finditer(_mask_tags(text))]


def _at_sentence_start(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and (text[i].isspace() or text[i] in _OPENERS):
        i -= 1
    return i < 0 or text[i] in _SENTENCE_END


def _personal_lower(personal_words) -> set[str]:
    return {w.lower() for w in personal_words}


def _protected(word: str, text: str, start: int, personal_lower: set[str]) -> bool:
    """Design 9.1 point 3: capitalised inside a sentence, or in the personal word list."""
    if word.lower() in personal_lower:
        return True
    return word[:1].isupper() and not _at_sentence_start(text, start)


def _hit_rate(text: str, language: str) -> float | None:
    """Share of words (2+ letters) the dictionary knows.

    None without a dictionary, 0.0 when the text has no words."""
    if not available(language):
        return None
    words = [w for _s, _e, w in _words(text) if len(w) >= _MIN_WORD][:_RATE_WORDS]
    if not words:
        return 0.0
    return sum(known(w, language) for w in words) / len(words)


def flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block:
    if block.label in _SKIP_LABELS or not available(language):
        return block
    personal_lower = _personal_lower(personal_words)
    taken = [(f.start, f.end) for f in block.flags if f.kind in ("foreign_letter", "suspicious")]
    new = []
    for start, end, word in _words(block.text):
        if len(word) < _MIN_WORD or _protected(word, block.text, start, personal_lower):
            continue
        if any(s < end and start < e for s, e in taken):
            continue
        if not known(word, language):
            new.append(Flag("suspicious", start, end, word, "not in the dictionary"))
    if not new:
        return block
    flags = sorted(block.flags + new, key=lambda f: (f.start, f.end))
    return dataclasses.replace(block, flags=flags)


def detect_language(text: str) -> str:
    cs, en = _hit_rate(text, "cs"), _hit_rate(text, "en")
    if cs is None and en is None:
        return "cs"
    if cs is not None and en is not None:
        return "en" if en > cs else "cs"
    if en is not None:
        return "en" if en >= 0.5 else "cs"
    return "cs" if cs >= 0.5 else "en"
