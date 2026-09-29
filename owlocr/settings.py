"""settings.json in the config dir (design section 10.3)."""
import ctypes
import json

from owlocr import paths


class SettingsError(ValueError):
    pass


def _system_language() -> str:
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return "cs" if langid & 0x3FF == 0x05 else "en"   # 0x05 = LANG_CZECH


DEFAULTS: dict = {
    "language_ui": _system_language(),
    "mode_default": "quality",
    "output_location": "next_to_source",
    "output_folder": "",
    "formats": ["md"],
    "use_text_layer": "born_digital",
    "document_language": "auto",
    "repairs_enabled": True,
    "append_suspicious_list": False,
    "keep_page_furniture": False,
    "idle_stop_minutes": 10,
    "time_limit_s": 300,
    "pdf_dpi": 200,
    "personal_words": [],
    "image_links": "markdown",
}

_CHOICES = {
    "language_ui": ("cs", "en"),
    "mode_default": ("quality", "fast"),
    "output_location": ("next_to_source", "folder"),
    "use_text_layer": ("born_digital", "never", "always"),
    "document_language": ("auto", "cs", "en"),
    "image_links": ("markdown", "obsidian"),
}
_BOOLS = ("repairs_enabled", "append_suspicious_list", "keep_page_furniture")
_RANGES = {"idle_stop_minutes": (0, 120), "time_limit_s": (60, 1800), "pdf_dpi": (150, 300)}
_FORMATS = ("md", "txt", "docx", "pdf")


def _check(key: str, value) -> None:
    if key not in DEFAULTS:
        raise SettingsError(f"unknown setting: {key}")
    if key in _CHOICES:
        if value not in _CHOICES[key]:
            raise SettingsError(f"{key} must be one of {_CHOICES[key]}, not {value!r}")
    elif key in _BOOLS:
        if not isinstance(value, bool):
            raise SettingsError(f"{key} must be true or false")
    elif key in _RANGES:
        low, high = _RANGES[key]
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_number or not low <= value <= high:
            raise SettingsError(f"{key} must be a number from {low} to {high}")
        if key != "time_limit_s" and not isinstance(value, int):
            raise SettingsError(f"{key} must be a whole number")
    elif key == "output_folder":
        if not isinstance(value, str):
            raise SettingsError("output_folder must be text")
    elif key == "formats":
        if (not isinstance(value, list) or not value or len(set(value)) != len(value)
                or any(v not in _FORMATS for v in value)):
            raise SettingsError(f"formats must be a non-empty list of {_FORMATS} without repeats")
    elif key == "personal_words":
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise SettingsError("personal_words must be a list of words")


def load() -> dict:
    values = json.loads(json.dumps(DEFAULTS))   # deep copy
    try:
        stored = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return values
    if not isinstance(stored, dict):
        return values
    for key, value in stored.items():
        try:
            _check(key, value)
        except SettingsError:
            continue            # unknown key or damaged value: keep the default
        values[key] = value
    return values


def save(values: dict) -> None:
    for key, value in values.items():
        _check(key, value)
    full = load()
    full.update(values)
    paths.atomic_write_text(paths.settings_file(), json.dumps(full, ensure_ascii=False, indent=1) + "\n")


def get(key: str):
    values = load()
    if key not in values:
        raise KeyError(key)
    return values[key]


def update(changes: dict) -> dict:
    save(changes)
    return load()
