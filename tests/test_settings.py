import json

import pytest

from owlocr import paths, settings

EXPECTED_KEYS = {
    "language_ui", "mode_default", "output_location", "output_folder", "formats",
    "use_text_layer", "document_language", "repairs_enabled", "append_suspicious_list",
    "keep_page_furniture", "idle_stop_minutes", "time_limit_s", "pdf_dpi", "personal_words",
    "image_links",
}


def test_defaults_have_exactly_the_design_keys():
    assert set(settings.DEFAULTS) == EXPECTED_KEYS
    d = settings.DEFAULTS
    assert d["language_ui"] in ("cs", "en")
    assert d["mode_default"] == "quality"
    assert d["output_location"] == "next_to_source"
    assert d["output_folder"] == ""
    assert d["formats"] == ["md"]
    assert d["use_text_layer"] == "born_digital"
    assert d["document_language"] == "auto"
    assert d["repairs_enabled"] is True
    assert d["append_suspicious_list"] is False
    assert d["keep_page_furniture"] is False
    assert d["idle_stop_minutes"] == 10
    assert d["time_limit_s"] == 300
    assert d["pdf_dpi"] == 200
    assert d["personal_words"] == []


def test_load_without_file_returns_defaults():
    assert settings.load() == settings.DEFAULTS


def test_load_returns_a_copy():
    settings.load()["formats"].append("txt")
    assert settings.DEFAULTS["formats"] == ["md"]


def test_update_persists_and_returns_full_settings():
    new = settings.update({"formats": ["md", "txt"], "pdf_dpi": 300})
    assert new["formats"] == ["md", "txt"] and new["pdf_dpi"] == 300
    assert new["mode_default"] == "quality"
    stored = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    assert stored["pdf_dpi"] == 300
    assert settings.get("pdf_dpi") == 300


def test_unknown_keys_in_file_are_dropped_and_bad_values_replaced():
    paths.settings_file().write_text(json.dumps({"pdf_dpi": 9999, "bogus": 1, "mode_default": "fast"}), encoding="utf-8")
    values = settings.load()
    assert "bogus" not in values
    assert values["pdf_dpi"] == 200
    assert values["mode_default"] == "fast"


def test_damaged_file_gives_defaults():
    paths.settings_file().write_text("{not json", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS


@pytest.mark.parametrize("changes", [
    {"bogus": 1},
    {"mode_default": "turbo"},
    {"formats": []},
    {"formats": ["md", "md"]},
    {"formats": ["html"]},
    {"repairs_enabled": "yes"},
    {"idle_stop_minutes": 121},
    {"idle_stop_minutes": True},
    {"pdf_dpi": 200.5},
    {"time_limit_s": 59},
    {"personal_words": ["ok", 3]},
    {"output_folder": 5},
    {"image_links": "wiki"},
])
def test_invalid_changes_raise(changes):
    with pytest.raises(settings.SettingsError):
        settings.update(changes)
    assert not paths.settings_file().exists()


def test_settings_error_is_value_error():
    assert issubclass(settings.SettingsError, ValueError)


def test_get_unknown_key():
    with pytest.raises(KeyError):
        settings.get("bogus")


def test_image_links_setting():
    assert settings.DEFAULTS["image_links"] == "markdown"
    assert settings.update({"image_links": "obsidian"})["image_links"] == "obsidian"
    assert settings.get("image_links") == "obsidian"
