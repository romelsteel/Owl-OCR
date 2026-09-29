import re

import pytest

from tests.owl_helpers import between, static_text, ui_strings
from tests.test_ui_page import scan_page

SCRIPTS = ("owl.js", "review.js", "app.js")
DYNAMIC_PREFIXES = {"state_", "engine_", "mode_", "label_"}


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_element_id_used_exists(name):
    text = static_text(name)
    used = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", text))
    used |= set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", text))
    assert sorted(used - scan_page().ids) == []


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_translation_key_used_exists(name):
    keys = set(ui_strings()["en"])
    used = set(re.findall(r"\bt\(\s*'([a-z0-9_]+)'", static_text(name)))
    dynamic = {k for k in used if k.endswith("_")}
    assert dynamic <= DYNAMIC_PREFIXES
    assert sorted(used - dynamic - keys) == []


@pytest.mark.parametrize("name", [s for s in SCRIPTS if s != "owl.js"])
def test_document_text_never_goes_through_innerHTML(name):
    assert "innerHTML" not in static_text(name)


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_are_strict_and_balanced(name):
    text = static_text(name)
    assert text.startswith("'use strict';")
    for opening, closing in ("()", "[]", "{}"):
        assert text.count(opening) == text.count(closing), (name, opening)


def test_review_export_waits_for_the_pending_block_save():
    # The click on "Save again" is what blurs (and saves) the block: the export must wait for
    # that save and must not run when it failed, or the files miss the user's last edit.
    text = static_text("review.js")
    blur = between(text, "addEventListener('blur'", "\n    });")
    assert "saving = saving" in blur
    # a throw outside save()'s own try must not leave the chain rejected for good
    assert ".catch(function () { return false; })" in blur
    export = between(text, "async function exportAgain()", "\n  }\n")
    assert "await saving" in export
    assert export.index("await saving") < export.index("if (!saved && waitedOn) return;") < export.index("/export")


def test_review_old_save_failure_does_not_kill_save_again():
    # Only a save this press started (mousedown comes before the blur) or one still running may
    # stop the export; a new job starts with a clean chain.
    text = static_text("review.js")
    assert "addEventListener('mousedown', function () { pressMark = saveCount; })" in text
    export = between(text, "async function exportAgain()", "\n  }\n")
    assert "const waitedOn = (pressMark !== null && saveCount > pressMark) || inFlight > 0;" in export
    assert export.index("const waitedOn") < export.index("await saving")
    open_body = between(text, "async function open(", "\n  }\n")
    assert "saving = Promise.resolve(true);" in open_body


def test_review_queued_save_keeps_the_job_it_was_made_for():
    # Job id, read-only state and text are taken at blur time, not when the queued save runs.
    text = static_text("review.js")
    blur = between(text, "addEventListener('blur'", "\n    });")
    assert "const edit = { id: jobId, readOnly: readOnly, text: body.innerText" in blur
    save = between(text, "async function save(edit,", "\n  }\n")
    assert "if (edit.readOnly) return true;" in save
    assert "jobId" not in save and "body.innerText" not in save
    assert "if (readOnly)" not in save


def test_review_open_drops_a_late_answer_for_an_older_job():
    text = static_text("review.js")
    body = between(text, "async function open(", "\n  }\n")
    assert "const my = ++seq;" in body
    assert body.count("if (my !== seq) return;") == 2
    assert body.index("if (my !== seq) return;\n    doc = loaded;") > body.index("await deps.api(")


def test_review_repaired_tooltip_never_shows_undefined():
    assert "original: f.original || ''" in static_text("review.js")


def test_queue_list_is_not_rebuilt_for_token_progress():
    # The token count changes every second while a page is read; rebuilding the rows that often
    # loses clicks (Cancel on the running job). Only the running row's meta text is updated.
    text = static_text("app.js")
    refresh = between(text, "async function refresh()", "\n  }\n")
    key_line = between(refresh, "const key =", ";")
    assert "current_page_tokens" not in key_line
    assert "updateCurrentMeta()" in refresh
    update = between(text, "function updateCurrentMeta()", "\n  }\n")
    assert "metaText(job)" in update and "textContent" in update


def test_drag_ending_outside_the_list_restores_the_real_order():
    text = static_text("app.js")
    dragend = between(text, "addEventListener('dragend'", "\n    });")
    assert "S.jobsKey = ''" in dragend and "refresh()" in dragend


def test_internal_error_has_its_own_notice():
    notice = between(static_text("app.js"), "function renderNotice(error)", "\n  }\n")
    assert "error.code === 'internal'" in notice and "t('notice_internal')" in notice


def test_settings_save_error_is_translated():
    """M-3: a dropped server must not show the raw "network: Failed to fetch"."""
    submit = between(static_text("app.js"), "async function submitSettings(event)", "\n  }\n")
    catch = submit[submit.index("catch (err)"):]
    assert "$('settingsError').textContent = err.message;" not in catch
    assert "window.OwlWizard.errorText(err)" in catch and "t('t_unavailable')" in catch
