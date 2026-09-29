import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from owlocr import hardware
from owlocr.engine import bootstrap
from tests.owl_helpers import ui_strings

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "owlocr" / "web" / "static"
PY_SOURCES = [REPO / "owlocr" / "engine" / n for n in ("bootstrap.py", "stages.py", "relocate.py")] + \
             [REPO / "owlocr" / "web" / n for n in ("wizard_api.py", "dictionaries_api.py")]

STEPS = ("welcome", "hardware", "location", "install", "selftest", "dicts", "done")
STATES = ("pending", "start", "progress", "done", "skipped", "failed", "paused")
TIERS = ("gpu_full", "gpu_reduced", "cpu", "unsupported")
REASONS = ("driver_too_old", "gpu_too_old", "vram_too_small", "no_nvidia_gpu", "ram_too_small")


def wizard_strings() -> dict:
    text = (STATIC / "wizard_i18n.js").read_text(encoding="utf-8")
    begin, end = "/*WIZARD-STRINGS-BEGIN*/", "/*WIZARD-STRINGS-END*/"
    start = text.index(begin) + len(begin)
    return json.loads(text[start:text.index(end, start)])


STRINGS = wizard_strings()


def placeholders(text):
    return set(re.findall(r"\{(\w+)\}", text))


def test_both_languages_have_the_same_non_empty_keys():
    assert set(STRINGS) == {"cs", "en"}
    assert set(STRINGS["cs"]) == set(STRINGS["en"])
    for table in STRINGS.values():
        for key, value in table.items():
            assert key.startswith("wz_") and value.strip(), key


def test_placeholders_match_between_languages():
    for key in STRINGS["cs"]:
        assert placeholders(STRINGS["cs"][key]) == placeholders(STRINGS["en"][key]), key


def test_reason_codes_cover_choose_tier():
    assert set(hardware._REASON_RANK) | {"ram_too_small"} == set(REASONS)


def test_every_error_code_raised_by_python_has_a_message():
    pattern = re.compile(r'(?:(?:BootstrapError|LocationError|_error)\(\s*|\["error"\]\s*=\s*)f?"([a-z_]+)[:"]')
    constant = re.compile(r'^[A-Z_]+ = "([a-z_]+):\s', re.MULTILINE)
    codes = set()
    for source in PY_SOURCES:
        text = source.read_text(encoding="utf-8")
        codes |= set(pattern.findall(text))
        codes |= set(constant.findall(text))
    assert {"cancelled", "not_enough_space", "checksum_mismatch", "queue_running", "nested",
            "dictionary_failed", "dictionary_running", "busy", "install_running"} <= codes
    assert sorted(c for c in codes if f"wz_error_{c}" not in STRINGS["en"]) == []


def test_every_dynamic_key_family_is_complete():
    families = [("wz_step_", STEPS), ("wz_stage_", bootstrap.STAGES), ("wz_state_", STATES),
                ("wz_tier_", TIERS), ("wz_tier_desc_", TIERS), ("wz_speed_", TIERS), ("wz_reason_", REASONS),
                ("wz_dict_lang_", ("cs", "en"))]
    for prefix, names in families:
        for name in names:
            assert prefix + name in STRINGS["en"], prefix + name


INFORMAL = re.compile(r"\b(?:\w+(?:eš|ěš|íš|áš)|tvůj|tvoje|tvého|tebe|tobě|přetáhni|zkus|klikni|vlož|"
                      r"použij|zavři|přepni|oprav|vyber|zadej|počkej|zkontroluj|otevři)\b", re.IGNORECASE)
FORMAL_OK = {"váš"}


def test_czech_ui_speaks_formally():
    tables = {f"i18n.js:{k}": v for k, v in ui_strings()["cs"].items()}
    tables.update({f"wizard_i18n.js:{k}": v for k, v in STRINGS["cs"].items()})
    found = sorted(f"{key}: {m.group(0)}" for key, text in tables.items()
                   for m in INFORMAL.finditer(text) if m.group(0).lower() not in FORMAL_OK)
    assert found == []


# ---- wizard.js (task 22) ----------------------------------------------------------------
JS = (STATIC / "wizard.js").read_text(encoding="utf-8")


def test_every_static_key_in_wizard_js_exists():
    used = set(re.findall(r"\bt\('(wz_[a-z_]*[a-z])'", JS))
    assert len(used) > 30
    assert sorted(used - set(STRINGS["en"])) == []


def test_wizard_js_uses_the_same_step_and_stage_lists():
    assert "const STEPS = ['welcome', 'hardware', 'location', 'install', 'selftest', 'dicts', 'done'];" in JS
    stages = ", ".join(f"'{s}'" for s in bootstrap.STAGES)
    assert f"const STAGES = [{stages}];" in JS


def test_no_html_injection_in_wizard_js():
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("name", ["wizard.js", "wizard_i18n.js"])
def test_scripts_parse(name):
    done = subprocess.run(["node", "--check", str(STATIC / name)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_both_dictionaries_start_ticked():
    assert "dictChoice: { cs: true, en: true }" in JS


def test_reduced_tier_speed_matches_the_readme():
    """I-3: the wizard says what the README says, never the unmeasured 30-70 s."""
    assert STRINGS["en"]["wz_speed_gpu_reduced"] == \
        "about the same as Quality on a graphics card (not measured separately)"
    assert STRINGS["cs"]["wz_speed_gpu_reduced"] == "na grafické kartě zhruba stejně jako Kvalita (zvlášť neměřeno)"


def test_privacy_mentions_redirect_servers():
    """M-5: same wording as the README."""
    assert "and the servers these redirect to" in STRINGS["en"]["wz_welcome_privacy"]
    assert "a servery, na které tyto adresy přesměrují" in STRINGS["cs"]["wz_welcome_privacy"]
