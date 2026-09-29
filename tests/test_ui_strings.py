import re

from owlocr.jobs.queue import STATES
from tests.owl_helpers import static_text, ui_strings

ENGINE_STATES = ("not_installed", "stopped", "loading", "ready", "busy")
LABELS = ("title", "header", "text", "image", "figure", "image_caption", "table",
          "table_caption", "list", "formula", "page_number", "footer")


def test_czech_and_english_have_the_same_keys():
    table = ui_strings()
    assert set(table) == {"cs", "en"}
    assert sorted(set(table["cs"]) ^ set(table["en"])) == []
    for lang in table.values():
        for key, value in lang.items():
            assert isinstance(value, str) and value.strip(), key


def test_placeholders_match_between_languages():
    table = ui_strings()
    for key, cs_text in table["cs"].items():
        cs_vars = set(re.findall(r"\{(\w+)\}", cs_text))
        en_vars = set(re.findall(r"\{(\w+)\}", table["en"][key]))
        assert cs_vars == en_vars, key


def test_key_families_used_with_dynamic_names_are_complete():
    keys = set(ui_strings()["en"])
    wanted = {f"state_{s}" for s in STATES} | {f"engine_{s}" for s in ENGINE_STATES}
    wanted |= {"mode_quality", "mode_fast"} | {f"fmt_{f}" for f in ("md", "txt", "docx", "pdf")}
    wanted |= {f"label_{label}" for label in LABELS}
    assert sorted(wanted - keys) == []


def test_honest_mode_explanation_and_stop_engine_text():
    table = ui_strings()
    assert "9,5 GB" in table["cs"]["mode_tip"] and "9.5 GB" in table["en"]["mode_tip"]
    assert "procesoru" in table["cs"]["mode_tip"] and "processor" in table["en"]["mode_tip"]
    assert "znovu" in table["cs"]["stop_engine_confirm"]
    assert "again" in table["en"]["stop_engine_confirm"]


def test_i18n_script_exposes_translator():
    text = static_text("i18n.js")
    for name in ("window.OwlI18n", "setLang", "translateDom", "data-i18n-title",
                 "data-i18n-placeholder", "data-i18n-aria"):
        assert name in text
