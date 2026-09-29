"""The wizard is wired into plan B's page: markup, script order, app.js hooks, no placeholder left."""
import json
import re

from tests.conftest import REPO
from tests.owl_helpers import between

STATIC = REPO / "owlocr" / "web" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
I18N = (STATIC / "i18n.js").read_text(encoding="utf-8")
WIZARD = (STATIC / "wizard.js").read_text(encoding="utf-8")


def test_wizard_view_and_dictionary_panel_are_empty_containers():
    assert '<section id="viewWizard" class="view" hidden></section>' in INDEX
    assert '<div id="dictSettings" class="wz-dicts-panel"></div>' in INDEX
    assert INDEX.index('id="btnRemoveEngine"') < INDEX.index('id="dictSettings"')


def test_scripts_and_stylesheet_are_loaded_in_order():
    order = ["static/i18n.js", "static/owl.js", "static/review.js", "static/wizard_i18n.js",
             "static/wizard.js", "static/app.js"]
    positions = [INDEX.index(f'<script src="{name}"></script>') for name in order]
    assert positions == sorted(positions)
    assert '<link rel="stylesheet" href="static/wizard.css">' in INDEX
    assert INDEX.rstrip().endswith("</script></body></html>")


def test_app_js_hands_its_helpers_to_the_wizard():
    assert "window.OwlWizard.init({ api: api, toast: toast, confirmDialog: confirmDialog, showView: showView });" in APP
    assert "if (name === 'wizard') window.OwlWizard.show();" in APP
    assert "window.OwlWizard.reinstall();" in APP and "window.OwlWizard.move();" in APP
    assert "window.OwlWizard.remove();" in APP     # fix round 1: Remove shares the busy state
    assert "if (name === 'settings') window.OwlWizard.renderDictionaries($('dictSettings'));" in APP


def test_placeholder_is_gone():
    for text in (INDEX, APP):
        assert "wizardToSettings" not in text and "wizardToQueue" not in text
    begin, end = "/*STRINGS-BEGIN*/", "/*STRINGS-END*/"
    table = json.loads(I18N[I18N.index(begin) + len(begin):I18N.index(end)])
    for lang in ("cs", "en"):
        assert not {"wizard_title", "wizard_text", "wizard_to_settings", "wizard_to_queue"} & set(table[lang])


def test_not_installed_notice_offers_to_finish_the_setup():
    line = '<button id="noticeWizard" type="button" class="link-btn" data-i18n="notice_finish_setup" hidden></button>'
    assert line in INDEX
    assert INDEX.index('id="noticeText"') < INDEX.index('id="noticeWizard"') < INDEX.index('id="noticeClose"')
    assert "$('noticeWizard').addEventListener('click', function () { showView('wizard'); });" in APP
    notice = between(APP, "function renderNotice(error)", "\n  }\n")
    assert "$('noticeWizard').hidden = error.code !== 'not_installed';" in notice
    assert "s.installed === false && S.view !== 'wizard'" in APP
    begin, end = "/*STRINGS-BEGIN*/", "/*STRINGS-END*/"
    table = json.loads(I18N[I18N.index(begin) + len(begin):I18N.index(end)])
    assert table["cs"]["notice_finish_setup"] == "Dokončit nastavení"
    assert table["en"]["notice_finish_setup"] == "Finish setup"


# ---- adaptations to the real backend (fixes after the plan was written) -----------------
def test_the_effective_data_folder_and_move_leftovers_are_shown():
    # a drive root or a non-empty foreign folder becomes <folder>\OwlOCR: show what the server says
    assert WIZARD.count("data.data_root") >= 2
    assert "data.leftovers" in WIZARD and "t('wz_eng_leftovers')" in WIZARD


def test_verify_runs_in_the_wizard_with_the_engine_buttons_disabled():
    assert "$('btnVerify').addEventListener('click', function () { window.OwlWizard.verify(); });" in APP
    verify = between(WIZARD, "function verify()", "\n  }\n")
    assert "engineBusy(" in verify and "'/api/engine/verify'" in verify
    busy = between(WIZARD, "function engineBusy(", "\n  }\n")
    for name in ("btnVerify", "btnReinstall", "btnMove", "btnRemoveEngine"):
        assert name in WIZARD
    assert ".disabled = true" in busy or "setEngineButtons(true" in busy


def test_engine_errors_are_translated_in_settings():
    # busy / install_running / queue_running answer 409 with a code the wizard strings translate;
    # every engine action (Remove too) runs in the wizard under the shared busy state
    assert re.search(r"errorText: errorText", WIZARD)
    assert "engineAction" not in APP
    remove = between(WIZARD, "function remove()", "\n  }\n")
    assert "engineBusy('btnRemoveEngine'" in remove and "'/api/engine/remove'" in remove
    assert "t('confirm_remove_engine')" in remove


def test_only_a_failed_fetch_counts_as_network_error():
    # api() marks a fetch that never reached the server; a programming TypeError is "unknown"
    api = between(APP, "async function api(method, path, body)", "\n  }\n")
    assert "new Error('network: '" in api
    assert "instanceof TypeError" not in WIZARD


def test_failed_install_start_restores_a_usable_screen():
    # a refused POST /api/wizard/install (busy, queue_running, unsupported) must not leave the
    # fake "running" screen: previous events are kept and Continue / Try again come back
    start = between(WIZARD, "function startInstall()", "\n  }\n")
    assert "const before = W.progress;" in start
    catch = start[start.index(".catch("):]
    assert "running: false" in catch and "before" in catch


def test_install_polling_pauses_while_the_wizard_is_hidden():
    poll = between(WIZARD, "function poll()", "\n  }\n")
    assert poll.count("visible()") >= 2
    assert "if (W.progress.running) poll();" in between(WIZARD, "function show()", "\n  }\n")


def test_dictionary_downloads_cannot_be_started_twice():
    install = between(WIZARD, "function installDicts(languages)", "\n  }\n")
    assert "if (W.dictStarting) return" in install and "W.dictStarting = true" in install
    assert WIZARD.count("W.dictStarting") >= 5


def test_settings_dictionary_panel_does_not_point_to_settings():
    panel = between(WIZARD, "function renderDictPanel()", "\n  }\n")
    assert "wz_dict_source" not in panel and "t('wz_dict_settings_source')" in panel


def test_probe_error_is_shown():
    assert "probe_error" in WIZARD
