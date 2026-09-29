"""CPU acceptance test (design 6.4 and 16). Run MANUALLY on the owner's PC, never in the normal
test run. It reads one generated page with the processor only and applies the decision rule:

    CER <= 3 %  and  seconds per page <= 300   ->  the CPU tier ships in v1
    otherwise                                  ->  v1 ships GPU-only (plan D, task 30, step 3)

    $env:OWLOCR_CPU_ACCEPTANCE = "1"
    py -3.11 -m pytest -m slow tests\\acceptance\\test_cpu_acceptance.py -s

The test points OWLOCR_HOME and OWLOCR_CONFIG at engine\\cpu-acceptance by itself (made by
prepare_cpu_root.py), so nothing else needs to be set in the shell. It hides the GPU itself with
CUDA_VISIBLE_DEVICES=-1 before the worker starts (an empty value does not hide it on this PC,
plan A task 16). The CPU engine root also has the cpu-only torch build, and the test
asserts that the engine reports no CUDA, so the GPU cannot be used even by mistake.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CPU_ROOT = REPO / "engine" / "cpu-acceptance"        # made by prepare_cpu_root.py
PAGE = REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.png"
TRUTH = REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.gt.txt"
MAX_CER = 0.03
MAX_SECONDS = 300.0

manual = pytest.mark.skipif(os.environ.get("OWLOCR_CPU_ACCEPTANCE") != "1",
                            reason="manual test: set OWLOCR_CPU_ACCEPTANCE=1 (see the module docstring)")

TAGS = re.compile(r"<\|ref\|>.*?<\|/ref\|>|<\|det\|>.*?<\|/det\|>", re.S)
SPECIAL = re.compile(r"<\|[^|>]*\|>|<PAGE>")
HTML = re.compile(r"</?(table|thead|tbody|tr|td|th)[^>]*>", re.I)
MARKDOWN = re.compile(r"^\s{0,3}#{1,6}\s+|\*\*|__", re.M)


def clean_ocr(raw: str) -> str:
    """Same cleaning as the spike's score.py, so the numbers are comparable."""
    text = TAGS.sub(" ", raw)
    text = SPECIAL.sub(" ", text)
    text = HTML.sub(" ", text)
    return MARKDOWN.sub("", text)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(truth: str, hypothesis: str) -> float:
    return edit_distance(truth, hypothesis) / max(len(truth), 1)


def test_helpers():
    assert edit_distance("kůň", "kun") == 2
    assert cer("abc", "abc") == 0.0
    assert normalize(clean_ocr("<|det|>text [1, 2, 3, 4]<|/det|>Ahoj\n  světe")) == "Ahoj světe"


def cpu_name() -> str:
    import platform
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor()


def write_record(report: dict) -> Path:
    """docs/research/2026-09-28-cpu-acceptance.md: the numbers and the decision, no local paths."""
    decision = ("the CPU tier ships in 0.1.0" if report["ships"]
                else "0.1.0 ships GPU-only (hardware.CPU_TIER_ENABLED = False)")
    text = f"""# CPU acceptance test

Date: {time.strftime("%Y-%m-%d")}. Machine: {report["cpu"]}, {report["ram_gb"]} GB RAM, GPU hidden with
`CUDA_VISIBLE_DEVICES=-1`, torch {report["torch"]}, float32, separate engine root created with the cpu index.
Page: `tests/fixtures/pages/01_letter_clean.png`, Fast mode.

| Measure | Value |
|---|---|
| Model load | {report["load_seconds"]} s |
| Seconds per page (wall clock) | {report["seconds_per_page"]} s |
| Output tokens | {report["output_tokens"]} |
| Character error rate | {report["cer"] * 100:.2f} % |
| Timed out | {"yes" if report["timed_out"] else "no"} |

Decision rule (plan D, task 30): CER at most 3 % and at most 300 s per page, then the CPU tier ships;
otherwise 0.1.0 ships GPU-only.

Result: **{decision}**.
"""
    out = REPO / "docs" / "research" / "2026-09-28-cpu-acceptance.md"
    out.write_text(text, encoding="utf-8")
    return out


@pytest.mark.slow
@manual
def test_cpu_reads_the_letter_page(monkeypatch):
    # conftest's autouse owl_env points OWLOCR_HOME/OWLOCR_CONFIG at empty temp folders, so the
    # test points them at the CPU engine root itself (values set in the shell would be overridden).
    monkeypatch.setenv("OWLOCR_HOME", str(CPU_ROOT / "data"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(CPU_ROOT / "config"))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    from owlocr import hardware, paths
    from owlocr.engine import bootstrap
    from owlocr.engine.client import default_engine

    record = bootstrap.read_install()
    assert record and record["tier"] == "cpu", "run tests\\acceptance\\prepare_cpu_root.py first"
    engine = default_engine()
    try:
        info = engine.start()
        assert info.cuda_available is False
        load_s = engine.load()
        started = time.monotonic()
        result = engine.ocr_page(PAGE, "fast", max_new_tokens=6000, time_limit_s=1800.0)
        wall_s = time.monotonic() - started
    finally:
        engine.stop()
    truth = TRUTH.read_text(encoding="utf-8")
    score = cer(normalize(truth), normalize(clean_ocr(result.text)))
    report = {"page": PAGE.name, "mode": "fast", "device": "cpu", "dtype": "float32", "torch": info.torch,
              "cpu": cpu_name(), "ram_gb": round(hardware.ram_total_mib() / 1024),
              "load_seconds": round(load_s, 1), "seconds_per_page": round(wall_s, 1),
              "engine_seconds": round(result.seconds, 1), "output_tokens": result.output_tokens,
              "cer": round(score, 4), "timed_out": result.timed_out,
              "ships": score <= MAX_CER and wall_s <= MAX_SECONDS}
    (paths.data_root().parent / "result.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nCPU ACCEPTANCE:", json.dumps(report, ensure_ascii=False))
    print("record written to", write_record(report))
    assert result.text.strip(), "the engine returned no text"
    assert score <= MAX_CER, f"CER {score:.2%} is above {MAX_CER:.0%}"
    assert wall_s <= MAX_SECONDS, f"{wall_s:.0f} s per page is above {MAX_SECONDS:.0f} s"
