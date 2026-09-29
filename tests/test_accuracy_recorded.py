"""Design 1.3 thresholds on the model output recorded in the spike (no GPU needed).

This checks the scoring and the text pipeline (parse -> layout -> plain text) on real model output;
test_accuracy_gpu.py runs the same check on fresh output of the installed engine.
"""
import pytest

from owlocr.pipeline import layout
from owlocr.pipeline.document import Page, plain_text
from owlocr.pipeline.parse import parse_raw
from tests.conftest import PAGES, RAW
from tests.scoring import MAX_CER, MIN_ACCENTS, UPRIGHT, score


def pipeline_text(raw: str) -> str:
    blocks = layout.arrange(parse_raw(raw), "cs")
    page = Page(index=0, source="ocr", mode="quality", width_px=0, height_px=0, rotation_applied=0,
                blocks=blocks, raw=raw, warnings=[], seconds=0.0)
    return plain_text(page, keep_furniture=True)


def test_scoring_selftest():
    truth = "Příliš žluťoučký kůň úpěl ďábelské ódy."
    assert score(truth, truth) == {"cer": 0.0, "accents_right": 15, "accents_total": 15}
    s = score(truth, "Prilis žluťoučký kůň úpěl ďábelské ódy.")
    assert (s["accents_right"], s["accents_total"]) == (12, 15)
    assert abs(s["cer"] - 3 / len(truth)) < 1e-9


def test_recorded_quality_output_meets_the_thresholds():
    right = total = 0
    for name in UPRIGHT:
        truth = (PAGES / f"{name}.gt.txt").read_text(encoding="utf-8")
        text = pipeline_text((RAW / f"{name}.gundam.raw.txt").read_text(encoding="utf-8"))
        s = score(truth, text)
        assert s["cer"] <= MAX_CER, (name, s)
        right += s["accents_right"]
        total += s["accents_total"]
    assert right / total >= MIN_ACCENTS, (right, total)


@pytest.mark.parametrize("name, expected_cer", [("01_letter_clean", 0.0038), ("03_small_print_clean", 0.0259)])
def test_same_numbers_as_the_spike(name, expected_cer):
    truth = (PAGES / f"{name}.gt.txt").read_text(encoding="utf-8")
    text = pipeline_text((RAW / f"{name}.gundam.raw.txt").read_text(encoding="utf-8"))
    assert score(truth, text)["cer"] == pytest.approx(expected_cer, abs=0.0005)
