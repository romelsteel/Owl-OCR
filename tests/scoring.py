"""Accuracy measures for the fixture pages (same method as spike/score.py).

CER = character error rate = edit distance / length of the correct text, after collapsing
whitespace. Accents = share of the Czech accented letters of the correct text that came out right.
"""
import re
import unicodedata

from rapidfuzz.distance import Levenshtein

CZECH = set("ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ")
UPRIGHT = ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
           "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo", "08_screenshot")
MAX_CER = 0.03                 # design 1.3: at most 3 % per page
MIN_ACCENTS = 0.95             # design 1.3: at least 95 % of accented letters, over all pages


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def cer(truth: str, hyp: str) -> float:
    return Levenshtein.distance(truth, hyp) / max(len(truth), 1)


def accents(truth: str, hyp: str) -> tuple[int, int]:
    """(right, total) over the accented letters of the correct text."""
    wrong = set()
    for op, i, _ in Levenshtein.editops(truth, hyp):
        if op in ("replace", "delete"):
            wrong.add(i)
    total = [i for i, c in enumerate(truth) if c in CZECH]
    return sum(1 for i in total if i not in wrong), len(total)


def score(truth_text: str, ocr_text: str) -> dict:
    truth, hyp = normalize(truth_text), normalize(ocr_text)
    right, total = accents(truth, hyp)
    return {"cer": cer(truth, hyp), "accents_right": right, "accents_total": total}
