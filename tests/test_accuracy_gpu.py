"""Design 1.3 on the real engine: Quality mode on the upright fixture pages.

    py -3.11 -m pytest -m gpu tests/test_accuracy_gpu.py -v

USES THE GRAPHICS CARD. Excluded from normal runs (pyproject addopts: -m "not gpu").
Skipped when less than 9500 MiB of VRAM is free or when the development engine is not set up
(py -3.11 scripts\\dev_engine.py). Data root: OWLOCR_TEST_DATA_ROOT, else <repo>\\engine.
"""
import os

import pytest

from owlocr.engine.client import default_engine
from owlocr.engine.protocol import EngineError
from owlocr.hardware import REQUIRED_FREE_VRAM_MIB, free_vram_mib
from owlocr.pipeline.document import plain_text
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, process_page
from tests.conftest import PAGES, REPO
from tests.scoring import MAX_CER, MIN_ACCENTS, UPRIGHT, score

pytestmark = [pytest.mark.gpu, pytest.mark.slow]


@pytest.fixture
def real_engine(monkeypatch):
    free = free_vram_mib()
    need = REQUIRED_FREE_VRAM_MIB["quality"]
    if free is None or free < need:
        pytest.skip(f"needs {need} MiB of free VRAM, {free} MiB free")
    monkeypatch.setenv("OWLOCR_HOME", os.environ.get("OWLOCR_TEST_DATA_ROOT") or str(REPO / "engine"))
    try:
        engine = default_engine()
    except EngineError as e:
        pytest.skip(f"development engine not set up ({e}); run scripts\\dev_engine.py")
    yield engine
    engine.stop()


def test_quality_mode_meets_the_design_thresholds(real_engine, tmp_path):
    real_engine.load()
    right = total = 0
    report = []
    for name in UPRIGHT:
        page = process_page(PAGES / f"{name}.png", PageSource(index=0, kind="image", text_layer=None),
                            real_engine, ProcessOptions(mode="quality"), tmp_path / name)
        assert page.mode == "quality" and page.warnings == [], (name, page.warnings)
        truth = (PAGES / f"{name}.gt.txt").read_text(encoding="utf-8")
        s = score(truth, plain_text(page, keep_furniture=True))
        report.append(f"{name}: CER {s['cer']:.2%}, accents {s['accents_right']}/{s['accents_total']}, "
                      f"{page.seconds:.0f} s")
        right += s["accents_right"]
        total += s["accents_total"]
        assert s["cer"] <= MAX_CER, "\n".join(report)
    print("\n".join(report))
    assert right / total >= MIN_ACCENTS, "\n".join(report)
