"""Apply text replacements and keep every Flag's character offsets correct."""
from __future__ import annotations

from dataclasses import dataclass

from owlocr.pipeline.document import Flag


@dataclass(frozen=True)
class Edit:
    start: int          # offsets in the text before the edit
    end: int
    new: str            # replacement text
    kind: str           # Flag kind recorded for this edit ('repaired')
    note: str


def apply_edits(text: str, flags: list[Flag], edits: list[Edit]) -> tuple[str, list[Flag]]:
    """Apply non-overlapping edits (an edit overlapping an earlier one is dropped).

    Returns the new text and the flags: the old ones with shifted offsets plus one new Flag per
    edit whose `original` is the replaced text. The result is sorted by (start, end).
    """
    chosen: list[Edit] = []
    for edit in sorted(edits, key=lambda e: (e.start, e.end)):
        if chosen and edit.start < chosen[-1].end:
            continue
        chosen.append(edit)
    if not chosen:
        return text, list(flags)

    pieces: list[str] = []
    spans: list[tuple[int, int, int, int]] = []   # old start, old end, new start, new end
    pos = 0
    length = 0
    for edit in chosen:
        pieces.append(text[pos:edit.start])
        length += edit.start - pos
        spans.append((edit.start, edit.end, length, length + len(edit.new)))
        pieces.append(edit.new)
        length += len(edit.new)
        pos = edit.end
    pieces.append(text[pos:])
    new_text = "".join(pieces)

    def move(p: int, is_end: bool) -> int:
        shift = 0
        for old_s, old_e, new_s, new_e in spans:
            if p <= old_s:                  # before this edit
                break
            if p < old_e:                   # strictly inside the replaced text
                return new_e if is_end else new_s
            shift = new_e - old_e           # at or after the end of this edit
        return p + shift

    moved = [Flag(f.kind, move(f.start, False), move(f.end, True), f.original, f.note)
             for f in flags]
    added = [Flag(edit.kind, new_s, new_e, text[edit.start:edit.end], edit.note)
             for edit, (_os, _oe, new_s, new_e) in zip(chosen, spans)]
    return new_text, sorted(moved + added, key=lambda f: (f.start, f.end))
