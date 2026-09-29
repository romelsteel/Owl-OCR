# Owl OCR Plan C: Correction and Exports — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dictionary-based correction (spell check, rule repairs, orientation and tall-image guards, caption and hyphen layout rules) and the Word and searchable-PDF exports to the plan-A foundation of Owl OCR.
**Architecture:** Pure-Python pipeline stages behind the functions of the interface contract, built on plan A's code: `spellcheck` (spylls + Hunspell dictionaries downloaded on demand), `repair` (rules R1–R5 and dictionary-gated letter fixes, every change a `Flag`), `layout_rules` (called by `layout.arrange`), orientation helpers in `guards`, strip cutting in `pages`, and a `process.process_page` that adds the sideways turn, the post-OCR orientation probe and tall-image strips around plan A's reading logic. Exporters write Word with python-docx and a searchable PDF by stamping an invisible reportlab text layer (DejaVu Sans, render mode 3) onto the untouched original page with pikepdf.
**Tech Stack:** Python 3.11 (Windows), spylls 0.1.7, pikepdf 10.14.0, reportlab 5.0.1, python-docx 1.2.0, numpy (<3), Pillow, pypdfium2 (tests read text back with it), pytest; Hunspell `cs_CZ`/`en_US` from the LibreOffice dictionaries repository; DejaVu Sans 2.37.
**Spec:** docs/superpowers/specs/2026-09-28-owl-ocr-design.md and docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md

## Global Constraints

- Never use PyMuPDF (`fitz`), it is AGPL: read and render PDFs with pypdfium2, write them with pikepdf + reportlab.
- A word repair is applied only when the result is a dictionary word and the original is not (design 9.1 point 1); without an installed dictionary no word is repaired.
- Every repair is recorded as a `Flag` (kind `'repaired'`, `original` = text before the change, offsets into `Block.text`); `Block.raw_text` is never changed; repairs can be switched off (`ProcessOptions.repairs_enabled`).
- A word that starts with a capital letter inside a sentence, or is in the personal word list, is never flagged or repaired (design 9.1 point 3); tokens touching digits are never words.
- AppData redirect trap (design 4.1): anything started from a Claude session sets `OWLOCR_HOME` and `OWLOCR_CONFIG` to real folders; every test here does it through the `tiny_dicts` / `no_dicts` fixtures or plan A's autouse fixture.
- Windows only, Python 3.11; run tests with `py -3.11 -m pytest ...` from the repository root (plan A's `pyproject.toml` deselects `gpu` tests by default).
- Plan A (`docs/superpowers/plans/2026-09-28-plan-a-foundation.md`) must be finished first; this plan edits exactly its code. Before Task 1 run `git switch -c plan-c-correction` from the branch that holds plan A (plan C does not need plan B). Never push.
- Never run GPU tests with less than 9500 MiB free VRAM; this plan needs no GPU at all: do not load the model and do not run `spike/run_ocr.py`.
- Never commit anything from `samples/` nor text copied from it; every test sentence in this plan is invented.
- Dictionaries are never bundled in v1: they are downloaded on demand from pinned commits into `spellcheck.dictionaries_dir()` and verified by size and sha256.
- The network is used only by the two one-off scripts of tasks 1 and 15 and by tests gated with `OWLOCR_NETWORK_TESTS=1`.
- Names and signatures of `docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md` are used verbatim; additions are listed in "Contract notes" at the end.
- Where a task says "rename plan A's function", keep plan A's body unchanged; where it says "add below plan A's imports", add the lines after the last import at the top of the file and do not duplicate an import that is already there; "replace the function X" means the whole `def X` (or `class X`) up to the next top-level definition.
- `process_page` never catches `EngineError` (plan A contract note 1: out-of-memory and dead-worker retries live in the caller) and passes `on_progress` and `cancel` to every engine call, the orientation probes included.
- Only two plan A tests change, both in task 19, because Word and PDF export stop raising `NotImplementedError`; every other plan A test must keep passing after every task.
- Subagents run on Opus 5.5 or Sonnet.
- Commit message trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (given as a second `-m` in every commit command below).
- Never run `.bat` files.

## File Structure

| File | Responsibility |
|---|---|
| `owlocr/pipeline/dictionaries.json` | create: pinned source, commit, licence, size and sha256 of the Czech and English Hunspell files |
| `owlocr/pipeline/dictionaries.py` | create: download on demand, verify, remove the dictionaries |
| `owlocr/pipeline/spellcheck.py` | replace plan A stub: spylls look-ups with cache, tokeniser, protection rules, suspicious flags, language detection |
| `owlocr/pipeline/edits.py` | create: apply text replacements and keep `Flag` offsets right |
| `owlocr/pipeline/repair.py` | replace plan A stub: rules R1–R5, plain d/t → ď/ť, foreign look-alike letters |
| `owlocr/pipeline/layout_rules.py` | create: furniture to page edges, caption move, dictionary-aware de-hyphenation |
| `owlocr/pipeline/layout.py` | modify: plan A's `arrange` becomes `_arrange_basic` (used without a dictionary); new `arrange` adds the plan C rules |
| `owlocr/pipeline/guards.py` | modify: `rotate_image`, `looks_sideways`, `dictionary_hit_rate`, `best_rotation` |
| `owlocr/pipeline/pages.py` | modify: `cut_strips` for tall images |
| `owlocr/pipeline/process.py` | modify: plan A's reading logic moves unchanged into `_read_once`; `process_page` adds the sideways turn, the orientation probe and strips |
| `owlocr/export/fonts/DejaVuSans.ttf`, `owlocr/export/fonts/DejaVuSans-LICENSE.txt` | create: embedded font for the invisible text layer and its licence |
| `owlocr/export/searchable_pdf.py` | create: invisible text layer on the original PDF page, or image + text for image inputs |
| `owlocr/export/docx.py` | create: Word export |
| `owlocr/export/markdown.py` | modify: image crops of turned pages, foreign letters in the appendix |
| `owlocr/export/__init__.py` | modify: `export_all` writes md, txt, docx, pdf; `FORMATS_AVAILABLE` |
| `requirements.txt` | modify: spylls, pikepdf, reportlab, python-docx, numpy |
| `tests/conftest.py` | modify: append the `tiny_dicts` and `no_dicts` fixtures (tiny offline Hunspell dictionaries) |
| `tests/test_dictionaries.py` | create: manifest, download, verify, remove (network part gated) |
| `tests/test_spellcheck_dictionary.py` | create: spellcheck |
| `tests/test_edits.py` | create: edit helper |
| `tests/test_repair_rules.py` | create: repair rules with the spike's error examples |
| `tests/test_layout_rules.py` | create: caption move, furniture, de-hyphenation |
| `tests/test_real_dictionaries.py` | create: real dictionaries against the spike examples (network, gated) |
| `tests/test_orientation.py` | create: sideways check, rotation helper, hit rate, best rotation |
| `tests/test_strips.py` | create: strip cutting |
| `tests/test_process_orientation.py` | create: orientation, dictionaries and strips inside `process_page` |
| `tests/test_rotation_fake_worker.py` | create: rotated fixture page through `SubprocessEngine` + `tests/fake_worker.py` |
| `tests/test_font.py` | create: font file pin and Czech coverage |
| `tests/test_searchable_pdf.py` | create: searchable PDF, text checked with pypdfium2 |
| `tests/test_docx_export.py` | create: Word export |
| `tests/test_markdown_plan_c.py` | create: Markdown additions |
| `tests/test_export_all_formats.py` | create: `export_all` with all four formats |
| `tests/test_export_all.py`, `tests/test_cli.py` | modify (task 19): one plan A test each that expected `NotImplementedError` for Word/PDF |

---

### Task 1: Dictionary licence check and pinned manifest

**Files:**
- Create: `owlocr/pipeline/dictionaries.json`
- Test: `tests/test_dictionaries.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `owlocr/pipeline/dictionaries.json` with keys `url_template` and `languages.{cs,en}.{name, source, commit, licence, decision, files[{name, path, size, sha256}]}`; the licence file is listed first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dictionaries.py`:

```python
"""Plan C: dictionary manifest, on-demand download and verification (design 9.3)."""
import json
import re
from pathlib import Path

MANIFEST = Path(__file__).parent.parent / "owlocr" / "pipeline" / "dictionaries.json"


def test_manifest_pins_both_languages():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "{commit}" in data["url_template"] and "{path}" in data["url_template"]
    for language in ("cs", "en"):
        entry = data["languages"][language]
        assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"])
        assert entry["licence"] and entry["decision"]
        names = [f["name"] for f in entry["files"]]
        assert names[0].endswith(".LICENSE.txt")                 # licence arrives first
        assert names[1:] == [f"{entry['name']}.aff", f"{entry['name']}.dic"]
        for f in entry["files"]:
            assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) and f["size"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_dictionaries.py -v
```

Expected: `FAILED tests/test_dictionaries.py::test_manifest_pins_both_languages - FileNotFoundError` (the manifest does not exist yet).

- [ ] **Step 3: Write minimal implementation**

3a. Check the licences and the pinned files. Save this script as `%TEMP%\owl_dict_check.py` (outside the repository) and run `py -3.11 %TEMP%\owl_dict_check.py`:

```python
"""One-off licence and checksum check for the Hunspell dictionaries (plan C, task 1).
Run from a temporary folder; writes nothing into the repository."""
import hashlib
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
URL = "https://raw.githubusercontent.com/LibreOffice/dictionaries/{commit}/{path}"
API = "https://api.github.com/repos/LibreOffice/dictionaries/commits?path={folder}&per_page=1"
PINS = {
    "cs": ("b3a1c0be50d1ad0b404070124463fb4af90bbe39", "cs_CZ",
           ["cs_CZ/README_en.txt", "cs_CZ/cs_CZ.aff", "cs_CZ/cs_CZ.dic"]),
    "en": ("e7f163feb2beaf526135132d8716e68e19d2716e", "en",
           ["en/README_en_US.txt", "en/en_US.aff", "en/en_US.dic"]),
}

for language, (commit, folder, files) in PINS.items():
    with urllib.request.urlopen(API.format(folder=folder), timeout=60) as r:
        latest = re.search(r'"sha":\s*"([0-9a-f]{40})"', r.read().decode()).group(1)
    print(f"== {language}: pinned {commit}, latest commit touching {folder}/: {latest}")
    for path in files:
        with urllib.request.urlopen(URL.format(commit=commit, path=path), timeout=60) as r:
            data = r.read()
        print(f"{path}: size {len(data)} sha256 {hashlib.sha256(data).hexdigest()}")
        if path.endswith(".txt"):
            text = data.decode("utf-8", "replace")
            for line in text.splitlines():
                if re.search(r"licen[cs]e|GPL|copyright|permission", line, re.I):
                    print("   ", line.strip()[:110])
```

3b. Apply the decision rule and write it down. The rule is:

> If the licence permits redistribution alongside an MIT-licensed app as a separate data file (for example GPL, LGPL or MPL data shipped unmodified as a separate file together with its licence text), the dictionary is **downloaded by the app on demand** into `spellcheck.dictionaries_dir()` and is **not bundled in the installer in v1**, which keeps the installer licence-clean in every case. Record source URL, exact commit, sha256 and licence name in `owlocr/pipeline/dictionaries.json`. If the licence forbids redistribution altogether, stop and report to the owner; do not write the manifest.

What the check found when this plan was written (2026-09-28): the Czech dictionary (`cs_CZ/README_en.txt`) says "licensed under the GNU/GPL license" (no version given); the English `en_US` dictionary (`en/README_en_US.txt`) is under the SCOWL licence, a permissive BSD/MIT-style licence. Both allow redistribution as separate, unmodified data files, so both are downloaded on demand. The latest commits touching `cs_CZ/` and `en/` were `b3a1c0be50d1ad0b404070124463fb4af90bbe39` and `e7f163feb2beaf526135132d8716e68e19d2716e`.

Compare the script output with the values below. Every size and sha256 must match exactly. If the script shows a newer "latest commit", keep the pins below anyway (they are immutable); if any pinned value does not match, stop and report.

3c. Create `owlocr/pipeline/dictionaries.json`:

```json
{
  "url_template": "https://raw.githubusercontent.com/LibreOffice/dictionaries/{commit}/{path}",
  "languages": {
    "cs": {
      "name": "cs_CZ",
      "source": "https://github.com/LibreOffice/dictionaries/tree/b3a1c0be50d1ad0b404070124463fb4af90bbe39/cs_CZ",
      "commit": "b3a1c0be50d1ad0b404070124463fb4af90bbe39",
      "licence": "GNU GPL (version not stated in README_en.txt)",
      "decision": "download on demand into dictionaries_dir(), unmodified, with its licence text; never bundled in v1",
      "files": [
        {"name": "cs_CZ.LICENSE.txt", "path": "cs_CZ/README_en.txt", "size": 13105,
         "sha256": "0fe6d017aa91ffb58146d19160f8207900cc0c49d5fffef0b1a7d3a364cb29bd"},
        {"name": "cs_CZ.aff", "path": "cs_CZ/cs_CZ.aff", "size": 111575,
         "sha256": "7ecb20620ecd46ebd9c36f3f33e69dd4eda385cba5b2bb4e6bc396d910e297f7"},
        {"name": "cs_CZ.dic", "path": "cs_CZ/cs_CZ.dic", "size": 3656362,
         "sha256": "d8e8c88c006fdae72dac8c85df11b0c99a773e05a4ab0fcbe92244876668ca74"}
      ]
    },
    "en": {
      "name": "en_US",
      "source": "https://github.com/LibreOffice/dictionaries/tree/e7f163feb2beaf526135132d8716e68e19d2716e/en",
      "commit": "e7f163feb2beaf526135132d8716e68e19d2716e",
      "licence": "SCOWL licence (permissive, BSD/MIT-like; see README_en_US.txt)",
      "decision": "download on demand into dictionaries_dir(), unmodified, with its licence text; never bundled in v1",
      "files": [
        {"name": "en_US.LICENSE.txt", "path": "en/README_en_US.txt", "size": 15732,
         "sha256": "168b4c01cb841f766a72f310b065c04d09cff46376c37a81d799593ce751c371"},
        {"name": "en_US.aff", "path": "en/en_US.aff", "size": 3205,
         "sha256": "e746c882dd6f303c2c46e7452804b9201115a6942cfeb15f18f8edf774d2e24e"},
        {"name": "en_US.dic", "path": "en/en_US.dic", "size": 551762,
         "sha256": "f0b1a234bd178bdd01875b2a392a9647f888b8fe879f79c52aae62c2759b3647"}
      ]
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_dictionaries.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/dictionaries.json tests/test_dictionaries.py
git commit -m "Pin Czech and English Hunspell dictionaries after licence check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Plan C dependencies, tiny test dictionaries, dictionary look-ups

**Files:**
- Modify: `owlocr/pipeline/spellcheck.py` (replace the plan A stub file), `tests/conftest.py` (append), the app's dependency list (see step 3a)
- Test: `tests/test_spellcheck_dictionary.py`

**Interfaces:**
- Consumes: `owlocr.paths.data_root() -> Path`; `owlocr.pipeline.document.Block`.
- Produces: `spellcheck.dictionaries_dir() -> Path`, `spellcheck.available(language: str) -> bool`, `spellcheck.known(word: str, language: str) -> bool` (True when no dictionary), private `spellcheck._reset_cache() -> None`, `spellcheck._dictionary(language) -> spylls Dictionary | None`, constant `DICTIONARY_NAMES = {"cs": "cs_CZ", "en": "en_US"}`; fixtures `tiny_dicts` (returns the dictionaries folder) and `no_dicts`.

- [ ] **Step 1: Write the failing test**

Append this block to the end of `tests/conftest.py` (keep plan A's content above it):

```python
# ---- plan C: tiny offline Hunspell dictionaries --------------------------------------------
import pytest  # noqa: E402  (repeated on purpose: this block must work on its own)

TINY_CS_WORDS = """
a i v ve k s z o u na je to se byl byla buď nebo také takže list listy listu rostlina
rostliny kapraď kapradí pojišťovnou uhrazen účet kaktusovitých čeleď rod druh bylinný
stonek květ dřevitý dnes pacient lékař zpráva řapík řapíku ťukat dub buk strom roste
mají jsou pro velký malý dopis česko slovenský stránka text obrázek viz dole nahoře
Praha Brno
""".split()

TINY_EN_WORDS = """
a the and is of to in this page text house water tree green leaf leaves letter doctor
report it was on for with
""".split()

TINY_AFF = "SET UTF-8\nTRY aeiouyáéíóúůýěčďňřšťžbcdfghjklmnpqrstvwxz\n"


def _write_tiny_dictionary(folder, name, words):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.aff").write_text(TINY_AFF, encoding="utf-8")
    unique = sorted(set(words))
    (folder / f"{name}.dic").write_text(f"{len(unique)}\n" + "\n".join(unique) + "\n",
                                        encoding="utf-8")


@pytest.fixture
def tiny_dicts(tmp_path, monkeypatch):
    """OWLOCR_HOME with a tiny Czech and English dictionary; returns the dictionaries folder."""
    from owlocr.pipeline import spellcheck
    home = tmp_path / "owl_home_dicts"
    monkeypatch.setenv("OWLOCR_HOME", str(home))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "owl_config_dicts"))
    folder = home / "dictionaries"
    _write_tiny_dictionary(folder, "cs_CZ", TINY_CS_WORDS)
    _write_tiny_dictionary(folder, "en_US", TINY_EN_WORDS)
    spellcheck._reset_cache()
    yield folder
    spellcheck._reset_cache()


@pytest.fixture
def no_dicts(tmp_path, monkeypatch):
    """OWLOCR_HOME without any dictionary."""
    from owlocr.pipeline import spellcheck
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "owl_home_empty"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "owl_config_empty"))
    spellcheck._reset_cache()
    yield
    spellcheck._reset_cache()
```

Create `tests/test_spellcheck_dictionary.py`:

```python
"""Plan C: dictionary look-ups and suspicious-word flags (design 9)."""
import pytest

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import Block, Flag


def _block(text, label="text", flags=None):
    return Block(label=label, box=(100, 100, 900, 200), text=text, raw_text=text, flags=flags or [])


def _flagged(block):
    return [(f.kind, f.original, block.text[f.start:f.end]) for f in block.flags]


def test_dictionaries_dir_is_under_the_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "root"))
    assert spellcheck.dictionaries_dir() == tmp_path / "root" / "dictionaries"


def test_available(tiny_dicts):
    assert spellcheck.available("cs") and spellcheck.available("en")
    assert not spellcheck.available("de")


def test_nothing_available_without_files(no_dicts):
    assert not spellcheck.available("cs") and not spellcheck.available("en")


def test_known_words_and_case(tiny_dicts):
    for word in ("buď", "Buď", "BUĎ", "pojišťovnou", "Praha", "česko-slovenský"):
        assert spellcheck.known(word, "cs"), word
    for word in ("bud", "praha", "bylinny", "także", "kaktu-sovitých"):
        assert not spellcheck.known(word, "cs"), word


def test_typographic_apostrophe_is_looked_up_as_straight(tiny_dicts):
    assert spellcheck.known("doctor’s", "en") == spellcheck.known("doctor's", "en")


def test_known_is_true_without_dictionary(no_dicts):
    assert spellcheck.known("xqzt", "cs") is True


def test_lookups_are_cached(tiny_dicts, monkeypatch):
    assert spellcheck.known("strom", "cs")
    dictionary = spellcheck._dictionary("cs")
    monkeypatch.setattr(dictionary, "lookup", lambda word: pytest.fail("not cached"))
    assert spellcheck.known("strom", "cs")
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_spellcheck_dictionary.py -v
```

Expected: errors at fixture setup, `AttributeError: module 'owlocr.pipeline.spellcheck' has no attribute '_reset_cache'` (6 errors, `test_dictionaries_dir_is_under_the_data_root` passes because plan A already has `dictionaries_dir`).

- [ ] **Step 3: Write minimal implementation**

3a. Install the libraries and record them:

```
py -3.11 -m pip install spylls==0.1.7 pikepdf==10.14.0 reportlab==5.0.1 python-docx==1.2.0 "numpy<3"
```

Append these five lines to `requirements.txt` (plan A's runtime dependency list; it already holds Pillow and pypdfium2):

```
spylls==0.1.7
pikepdf==10.14.0
reportlab==5.0.1
python-docx==1.2.0
numpy<3
```

3b. Replace the whole content of `owlocr/pipeline/spellcheck.py` (plan A's pass-through stub) with:

```python
"""Hunspell dictionary look-ups through spylls and flags for suspicious words (design 9).

Without a dictionary every function degrades gracefully: known() says True, nothing is flagged.
"""
from __future__ import annotations

import threading
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Block

DICTIONARY_NAMES = {"cs": "cs_CZ", "en": "en_US"}

_lock = threading.RLock()
_dictionaries: dict[tuple[str, str], object] = {}
_lookups: dict[tuple[str, str, str], bool] = {}


def dictionaries_dir() -> Path:
    return paths.data_root() / "dictionaries"


def _files(language: str) -> tuple[Path, Path] | None:
    name = DICTIONARY_NAMES.get(language)
    if name is None:
        return None
    folder = dictionaries_dir()
    return folder / f"{name}.aff", folder / f"{name}.dic"


def available(language: str) -> bool:
    files = _files(language)
    return files is not None and files[0].is_file() and files[1].is_file()


def _reset_cache() -> None:
    """Forget loaded dictionaries and cached look-ups (after a download, and in tests)."""
    with _lock:
        _dictionaries.clear()
        _lookups.clear()


def _dictionary(language: str):
    """The loaded spylls Dictionary, or None when it is not installed or cannot be read."""
    if not available(language):
        return None
    aff, _dic = _files(language)
    key = (str(aff.parent), language)
    with _lock:
        if key not in _dictionaries:
            from spylls.hunspell import Dictionary
            try:
                _dictionaries[key] = Dictionary.from_files(str(aff.with_suffix("")))
            except Exception:  # a damaged file must not stop OCR: behave as "no dictionary"
                _dictionaries[key] = None
        return _dictionaries[key]


def known(word: str, language: str) -> bool:
    word = word.replace("’", "'").strip()
    if not word:
        return True
    dictionary = _dictionary(language)
    if dictionary is None:
        return True
    key = (str(dictionaries_dir()), language, word)
    with _lock:
        hit = _lookups.get(key)
        if hit is None:
            try:
                hit = bool(dictionary.lookup(word))
            except Exception:
                hit = True
            _lookups[key] = hit
        return hit


def flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block:
    return block                      # task 3 of plan C gives this its real body


def detect_language(text: str) -> str:
    return "cs"                       # task 3 of plan C gives this its real body
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_spellcheck_dictionary.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/spellcheck.py tests/conftest.py tests/test_spellcheck_dictionary.py requirements.txt
git commit -m "Look words up in Hunspell dictionaries with spylls and a cache" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: Tokeniser, protection rules, suspicious words, language detection

**Files:**
- Modify: `owlocr/pipeline/spellcheck.py` (whole file shown)
- Test: `tests/test_spellcheck_dictionary.py` (append)

**Interfaces:**
- Consumes: `Block`, `Flag` from `owlocr.pipeline.document`.
- Produces: `spellcheck.flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block`, `spellcheck.detect_language(text: str) -> str` (`'cs'` or `'en'`); private helpers used by later tasks: `_mask_tags(text) -> str`, `_words(text) -> list[tuple[int, int, str]]`, `_at_sentence_start(text, start) -> bool`, `_personal_lower(personal_words) -> set[str]`, `_protected(word, text, start, personal_lower) -> bool`, `_hit_rate(text, language) -> float | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_spellcheck_dictionary.py`:

```python
def test_words_keep_czech_letters_and_skip_numbers():
    words = [w for _s, _e, w in spellcheck._words("Žluťoučký kůň, H2O, 1968, 5x, e-mail a bud'")]
    assert words == ["Žluťoučký", "kůň", "e-mail", "a", "bud"]


def test_words_ignore_html_tags():
    words = [w for _s, _e, w in spellcheck._words("<table><tr><td>Dub</td></tr></table>")]
    assert words == ["Dub"]


def test_unknown_words_are_flagged_with_offsets(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Rostlina je bylinny a sporořyly strom."), "cs", set())
    assert _flagged(out) == [("suspicious", "bylinny", "bylinny"),
                             ("suspicious", "sporořyly", "sporořyly")]
    assert out.text == "Rostlina je bylinny a sporořyly strom."


def test_capitalised_word_inside_a_sentence_is_protected(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Rod Opuntia roste. Opuntia je strom."), "cs", set())
    assert _flagged(out) == [("suspicious", "Opuntia", "Opuntia")]   # only the sentence start
    assert out.flags[0].start == 19


def test_personal_words_are_protected(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Je to bylinny strom."), "cs", {"Bylinny"})
    assert out.flags == []


def test_numbers_and_single_letters_are_not_flagged(tiny_dicts):
    out = spellcheck.flag_suspicious(_block("Strom 1968 x 25 H2O q."), "cs", set())
    assert out.flags == []


def test_foreign_letter_flag_is_not_duplicated(tiny_dicts):
    flag = Flag("foreign_letter", 6, 12, "piękný", "letter does not exist in Czech")
    out = spellcheck.flag_suspicious(_block("Je to piękný strom.", flags=[flag]), "cs", set())
    assert [f.kind for f in out.flags] == ["foreign_letter"]


def test_formula_and_image_blocks_are_skipped(tiny_dicts):
    for label in ("formula", "image", "figure"):
        block = _block("xqzt wvpl", label=label)
        assert spellcheck.flag_suspicious(block, "cs", set()) is block


def test_no_flags_without_dictionary(no_dicts):
    block = _block("xqzt wvpl")
    assert spellcheck.flag_suspicious(block, "cs", set()) is block


def test_detect_language(tiny_dicts):
    assert spellcheck.detect_language("The tree is green and the leaf is green.") == "en"
    assert spellcheck.detect_language("Rostlina je velký strom a list je malý.") == "cs"


def test_detect_language_defaults_to_czech_without_dictionaries(no_dicts):
    assert spellcheck.detect_language("The tree is green.") == "cs"


def test_detect_language_with_only_english_installed(tiny_dicts):
    (tiny_dicts / "cs_CZ.dic").unlink()
    spellcheck._reset_cache()
    assert spellcheck.detect_language("The tree is green and the leaf is green.") == "en"
    assert spellcheck.detect_language("Rostlina je velký strom a list je malý.") == "cs"
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_spellcheck_dictionary.py -v
```

Expected: `6 failed, 13 passed`; the first failure is `AttributeError: module 'owlocr.pipeline.spellcheck' has no attribute '_words'`.

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `owlocr/pipeline/spellcheck.py` with:

```python
"""Hunspell dictionary look-ups through spylls and flags for suspicious words (design 9).

Without a dictionary every function degrades gracefully: known() says True, nothing is flagged.
"""
from __future__ import annotations

import dataclasses
import re
import threading
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Block, Flag

DICTIONARY_NAMES = {"cs": "cs_CZ", "en": "en_US"}

# A word: letters of any alphabet (Czech included), optionally joined by a hyphen or an
# apostrophe. A letter run that touches a digit or an underscore is not a word ("H2O", "5x").
_WORD = re.compile(r"(?<![\w'’-])[^\W\d_]+(?:[-'’][^\W\d_]+)*(?!\w)")
_TAG = re.compile(r"<[^>]*>")
_SENTENCE_END = ".!?…"
_OPENERS = "\"'„“”‚‘’«»([{–—-*•"
_SKIP_LABELS = ("formula", "image", "figure")
_MIN_WORD = 2
_RATE_WORDS = 300

_lock = threading.RLock()
_dictionaries: dict[tuple[str, str], object] = {}
_lookups: dict[tuple[str, str, str], bool] = {}


def dictionaries_dir() -> Path:
    return paths.data_root() / "dictionaries"


def _files(language: str) -> tuple[Path, Path] | None:
    name = DICTIONARY_NAMES.get(language)
    if name is None:
        return None
    folder = dictionaries_dir()
    return folder / f"{name}.aff", folder / f"{name}.dic"


def available(language: str) -> bool:
    files = _files(language)
    return files is not None and files[0].is_file() and files[1].is_file()


def _reset_cache() -> None:
    """Forget loaded dictionaries and cached look-ups (after a download, and in tests)."""
    with _lock:
        _dictionaries.clear()
        _lookups.clear()


def _dictionary(language: str):
    """The loaded spylls Dictionary, or None when it is not installed or cannot be read."""
    if not available(language):
        return None
    aff, _dic = _files(language)
    key = (str(aff.parent), language)
    with _lock:
        if key not in _dictionaries:
            from spylls.hunspell import Dictionary
            try:
                _dictionaries[key] = Dictionary.from_files(str(aff.with_suffix("")))
            except Exception:  # a damaged file must not stop OCR: behave as "no dictionary"
                _dictionaries[key] = None
        return _dictionaries[key]


def known(word: str, language: str) -> bool:
    word = word.replace("’", "'").strip()
    if not word:
        return True
    dictionary = _dictionary(language)
    if dictionary is None:
        return True
    key = (str(dictionaries_dir()), language, word)
    with _lock:
        hit = _lookups.get(key)
        if hit is None:
            try:
                hit = bool(dictionary.lookup(word))
            except Exception:
                hit = True
            _lookups[key] = hit
        return hit


def _mask_tags(text: str) -> str:
    """Replace HTML and model tags by spaces of the same length, so offsets stay valid."""
    return _TAG.sub(lambda m: " " * len(m.group()), text)


def _words(text: str) -> list[tuple[int, int, str]]:
    """(start, end, word) for every word of the text; tags are ignored."""
    return [(m.start(), m.end(), m.group()) for m in _WORD.finditer(_mask_tags(text))]


def _at_sentence_start(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and (text[i].isspace() or text[i] in _OPENERS):
        i -= 1
    return i < 0 or text[i] in _SENTENCE_END


def _personal_lower(personal_words) -> set[str]:
    return {w.lower() for w in personal_words}


def _protected(word: str, text: str, start: int, personal_lower: set[str]) -> bool:
    """Design 9.1 point 3: capitalised inside a sentence, or in the personal word list."""
    if word.lower() in personal_lower:
        return True
    return word[:1].isupper() and not _at_sentence_start(text, start)


def _hit_rate(text: str, language: str) -> float | None:
    """Share of words (2+ letters) the dictionary knows.

    None without a dictionary, 0.0 when the text has no words."""
    if not available(language):
        return None
    words = [w for _s, _e, w in _words(text) if len(w) >= _MIN_WORD][:_RATE_WORDS]
    if not words:
        return 0.0
    return sum(known(w, language) for w in words) / len(words)


def flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block:
    if block.label in _SKIP_LABELS or not available(language):
        return block
    personal_lower = _personal_lower(personal_words)
    taken = [(f.start, f.end) for f in block.flags if f.kind in ("foreign_letter", "suspicious")]
    new = []
    for start, end, word in _words(block.text):
        if len(word) < _MIN_WORD or _protected(word, block.text, start, personal_lower):
            continue
        if any(s < end and start < e for s, e in taken):
            continue
        if not known(word, language):
            new.append(Flag("suspicious", start, end, word, "not in the dictionary"))
    if not new:
        return block
    flags = sorted(block.flags + new, key=lambda f: (f.start, f.end))
    return dataclasses.replace(block, flags=flags)


def detect_language(text: str) -> str:
    cs, en = _hit_rate(text, "cs"), _hit_rate(text, "en")
    if cs is None and en is None:
        return "cs"
    if cs is not None and en is not None:
        return "en" if en > cs else "cs"
    if en is not None:
        return "en" if en >= 0.5 else "cs"
    return "cs" if cs >= 0.5 else "en"
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_spellcheck_dictionary.py -v
```

Expected: `19 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/spellcheck.py tests/test_spellcheck_dictionary.py
git commit -m "Flag unknown words with protection for names and personal words" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Download and verify dictionaries on demand

**Files:**
- Create: `owlocr/pipeline/dictionaries.py`
- Test: `tests/test_dictionaries.py` (whole file shown)

**Interfaces:**
- Consumes: `owlocr/pipeline/dictionaries.json`; `spellcheck.dictionaries_dir()`, `spellcheck._reset_cache()`.
- Produces: `dictionaries.LANGUAGES`, `dictionaries.DictionaryError(RuntimeError)`, `dictionaries.manifest() -> dict`, `dictionaries.download(language: str, on_progress: Callable[[int, int], None] | None = None, cancel: threading.Event | None = None, entry: dict | None = None) -> Path`, `dictionaries.verify(language: str, entry: dict | None = None) -> dict[str, str]`, `dictionaries.remove(language: str) -> None`; test seam `dictionaries._open(url)`.

- [ ] **Step 1: Write the failing test**

Replace the whole content of `tests/test_dictionaries.py` with:

```python
"""Plan C: dictionary manifest, on-demand download and verification (design 9.3)."""
import hashlib
import io
import json
import os
import re
import threading
from pathlib import Path

import pytest

from owlocr.pipeline import dictionaries, spellcheck

MANIFEST = Path(__file__).parent.parent / "owlocr" / "pipeline" / "dictionaries.json"


def test_manifest_pins_both_languages():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "{commit}" in data["url_template"] and "{path}" in data["url_template"]
    for language in ("cs", "en"):
        entry = data["languages"][language]
        assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"])
        assert entry["licence"] and entry["decision"]
        names = [f["name"] for f in entry["files"]]
        assert names[0].endswith(".LICENSE.txt")                 # licence arrives first
        assert names[1:] == [f"{entry['name']}.aff", f"{entry['name']}.dic"]
        for f in entry["files"]:
            assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) and f["size"] > 0


def test_module_reads_the_manifest():
    assert dictionaries.manifest() == json.loads(MANIFEST.read_text(encoding="utf-8"))




def _fake_entry(files: dict[str, bytes]) -> dict:
    return {"name": "cs_CZ", "commit": "0" * 40, "licence": "test",
            "files": [{"name": name, "path": f"cs_CZ/{name}", "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]}


FILES = {
    "cs_CZ.LICENSE.txt": b"licence text",
    "cs_CZ.aff": "SET UTF-8\n".encode("utf-8"),
    "cs_CZ.dic": "2\nbuď\nstrom\n".encode("utf-8"),
}


def _serve(monkeypatch, files, calls=None):
    def fake_open(url):
        if calls is not None:
            calls.append(url)
        return io.BytesIO(files[url.rsplit("/", 1)[1]])
    monkeypatch.setattr(dictionaries, "_open", fake_open)


def test_download_verifies_and_makes_dictionary_available(no_dicts, monkeypatch):
    calls, progress = [], []
    _serve(monkeypatch, FILES, calls)
    assert not spellcheck.available("cs")
    folder = dictionaries.download("cs", on_progress=lambda d, t: progress.append((d, t)),
                                   entry=_fake_entry(FILES))
    assert folder == spellcheck.dictionaries_dir()
    assert spellcheck.available("cs")
    assert spellcheck.known("buď", "cs") and not spellcheck.known("bud", "cs")
    assert calls[0].endswith("/" + "0" * 40 + "/cs_CZ/cs_CZ.LICENSE.txt")
    assert progress[-1] == (sum(len(v) for v in FILES.values()),) * 2
    assert dictionaries.verify("cs", _fake_entry(FILES)) == {}


def test_second_download_fetches_nothing(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    calls = []
    _serve(monkeypatch, FILES, calls)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    assert calls == []


def test_wrong_checksum_is_rejected_and_nothing_is_installed(no_dicts, monkeypatch):
    served = dict(FILES, **{"cs_CZ.dic": "2\nbuď\nstrom\nX\n".encode("utf-8")})
    _serve(monkeypatch, served)
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.download("cs", entry=_fake_entry(FILES))
    assert not spellcheck.available("cs")
    assert not list(spellcheck.dictionaries_dir().glob("*.part"))


def test_cancel_stops_the_download(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(dictionaries.DictionaryError, match="cancelled"):
        dictionaries.download("cs", cancel=cancel, entry=_fake_entry(FILES))
    assert not spellcheck.available("cs")


def test_verify_reports_problems(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    (spellcheck.dictionaries_dir() / "cs_CZ.aff").write_bytes(b"SET UTF-8\r\n")
    (spellcheck.dictionaries_dir() / "cs_CZ.dic").unlink()
    assert dictionaries.verify("cs", _fake_entry(FILES)) == {"cs_CZ.aff": "wrong size",
                                                             "cs_CZ.dic": "missing"}


def test_remove_deletes_the_files(no_dicts, monkeypatch):
    _serve(monkeypatch, FILES)
    dictionaries.download("cs", entry=_fake_entry(FILES))
    dictionaries.remove("cs")
    assert not spellcheck.available("cs")


def test_unknown_language_is_an_error():
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.download("de")


@pytest.mark.skipif(os.environ.get("OWLOCR_NETWORK_TESTS") != "1",
                    reason="set OWLOCR_NETWORK_TESTS=1 to download the real dictionaries")
@pytest.mark.parametrize("language", ["cs", "en"])
def test_real_download_matches_the_pins(no_dicts, language):
    dictionaries.download(language)
    assert dictionaries.verify(language) == {}
    word = {"cs": "pojišťovnou", "en": "house"}[language]
    assert spellcheck.known(word, language)
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_dictionaries.py -v
```

Expected: collection error `ImportError: cannot import name 'dictionaries' from 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/dictionaries.py`:

```python
"""Download and verify the Hunspell dictionaries (design 9.3).

The dictionaries are not bundled in v1: the app downloads them on demand from the pinned
LibreOffice commits in dictionaries.json into spellcheck.dictionaries_dir(), unmodified and
together with their licence text. A file is moved into place only after its size and sha256
match, so a present .aff/.dic pair is always a verified one.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from owlocr.pipeline import spellcheck

LANGUAGES = ("cs", "en")
_CHUNK = 1 << 16
_TIMEOUT_S = 60


class DictionaryError(RuntimeError):
    pass


def manifest() -> dict:
    return json.loads(Path(__file__).with_name("dictionaries.json").read_text(encoding="utf-8"))


def _entry(language: str) -> dict:
    languages = manifest()["languages"]
    if language not in languages:
        raise DictionaryError(f"no dictionary is known for language {language!r}")
    return languages[language]


def _open(url: str):
    """Seam for tests: returns a readable binary response."""
    return urllib.request.urlopen(url, timeout=_TIMEOUT_S)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(language: str, entry: dict | None = None) -> dict[str, str]:
    """name -> problem for every file of the language; an empty dict means all files are good."""
    entry = entry or _entry(language)
    folder = spellcheck.dictionaries_dir()
    problems = {}
    for f in entry["files"]:
        path = folder / f["name"]
        if not path.is_file():
            problems[f["name"]] = "missing"
        elif path.stat().st_size != f["size"]:
            problems[f["name"]] = "wrong size"
        elif _sha256(path) != f["sha256"]:
            problems[f["name"]] = "wrong sha256"
    return problems


def download(language: str, on_progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None, entry: dict | None = None) -> Path:
    """Download the language's files (licence first), verify each, return the folder."""
    entry = entry or _entry(language)
    template = manifest()["url_template"]
    folder = spellcheck.dictionaries_dir()
    folder.mkdir(parents=True, exist_ok=True)
    total = sum(f["size"] for f in entry["files"])
    done = 0
    for f in entry["files"]:
        dest = folder / f["name"]
        if dest.is_file() and dest.stat().st_size == f["size"] and _sha256(dest) == f["sha256"]:
            done += f["size"]
            if on_progress:
                on_progress(done, total)
            continue
        part = dest.with_name(dest.name + ".part")
        digest = hashlib.sha256()
        try:
            with _open(template.format(commit=entry["commit"], path=f["path"])) as response, \
                    open(part, "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DictionaryError("cancelled")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
        except DictionaryError:
            part.unlink(missing_ok=True)
            raise
        except OSError as error:
            part.unlink(missing_ok=True)
            raise DictionaryError(f"{f['name']}: download failed: {error}") from error
        if part.stat().st_size != f["size"] or digest.hexdigest() != f["sha256"]:
            part.unlink(missing_ok=True)
            raise DictionaryError(f"{f['name']}: size or sha256 does not match the pinned value")
        os.replace(part, dest)
    spellcheck._reset_cache()
    return folder


def remove(language: str) -> None:
    entry = _entry(language)
    folder = spellcheck.dictionaries_dir()
    for f in entry["files"]:
        (folder / f["name"]).unlink(missing_ok=True)
    spellcheck._reset_cache()
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_dictionaries.py -v
```

Expected: `9 passed, 2 skipped` (the two real downloads are skipped without `OWLOCR_NETWORK_TESTS=1`). Then run the real download once (this reaches raw.githubusercontent.com):

```
$env:OWLOCR_NETWORK_TESTS = "1"; py -3.11 -m pytest tests/test_dictionaries.py -v; Remove-Item Env:OWLOCR_NETWORK_TESTS
```

Expected: `11 passed`. (In Git Bash: `OWLOCR_NETWORK_TESTS=1 py -3.11 -m pytest tests/test_dictionaries.py -v`.)

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/dictionaries.py tests/test_dictionaries.py
git commit -m "Download pinned dictionaries on demand and verify them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Edit helper that keeps flag offsets right

**Files:**
- Create: `owlocr/pipeline/edits.py`
- Test: `tests/test_edits.py`

**Interfaces:**
- Consumes: `Flag` from `owlocr.pipeline.document`.
- Produces: `edits.Edit(start: int, end: int, new: str, kind: str, note: str)` (frozen dataclass), `edits.apply_edits(text: str, flags: list[Flag], edits: list[Edit]) -> tuple[str, list[Flag]]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_edits.py`:

```python
"""Plan C: text edits that keep Flag offsets right."""
from owlocr.pipeline.document import Flag
from owlocr.pipeline.edits import Edit, apply_edits


def test_single_edit_records_a_flag_with_the_original():
    text, flags = apply_edits("je to bud' tak", [], [Edit(6, 10, "buď", "repaired", "R1")])
    assert text == "je to buď tak"
    assert flags == [Flag("repaired", 6, 9, "bud'", "R1")]


def test_later_flags_shift_by_the_length_change():
    old = [Flag("suspicious", 10, 15, "slovo", "x")]
    text, flags = apply_edits("ab ,, cd  slovo", old, [Edit(3, 5, "„", "repaired", "R4")])
    assert text == "ab „ cd  slovo"
    moved = [f for f in flags if f.kind == "suspicious"][0]
    assert text[moved.start:moved.end] == "slovo"


def test_several_edits_of_different_lengths():
    edits = [Edit(0, 1, "fi", "repaired", "R5"), Edit(4, 7, " – ", "repaired", "R3"),
             Edit(10, 12, "„", "repaired", "R4")]
    text, flags = apply_edits("ﬁ ab - cd ,,x", [], edits)
    assert text == "fi ab – cd „x"
    assert [(f.original, text[f.start:f.end]) for f in flags] == [
        ("ﬁ", "fi"), (" - ", " – "), (",,", "„")]


def test_flag_containing_an_edit_grows_with_it():
    old = [Flag("repaired", 0, 8, "abcdefgh", "outer")]
    text, flags = apply_edits("abcdefgh", old, [Edit(2, 4, "XYZW", "repaired", "inner")])
    outer = [f for f in flags if f.note == "outer"][0]
    assert text == "abXYZWefgh" and (outer.start, outer.end) == (0, 10)


def test_overlapping_edit_is_dropped():
    text, flags = apply_edits("abcdef", [], [Edit(0, 3, "X", "repaired", "a"),
                                             Edit(2, 4, "Y", "repaired", "b")])
    assert text == "Xdef" and [f.note for f in flags] == ["a"]


def test_no_edits_returns_the_same_text():
    old = [Flag("suspicious", 0, 3, "abc", "x")]
    assert apply_edits("abc", old, []) == ("abc", old)
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_edits.py -v
```

Expected: collection error `ModuleNotFoundError: No module named 'owlocr.pipeline.edits'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/edits.py`:

```python
"""Apply text replacements and keep every Flag's character offsets correct."""
from __future__ import annotations

from dataclasses import dataclass

from owlocr.pipeline.document import Flag


@dataclass(frozen=True)
class Edit:
    start: int          # offsets in the text before the edit
    end: int
    new: str            # replacement text
    kind: str           # Flag kind recorded for this edit ('repaired')
    note: str


def apply_edits(text: str, flags: list[Flag], edits: list[Edit]) -> tuple[str, list[Flag]]:
    """Apply non-overlapping edits (an edit overlapping an earlier one is dropped).

    Returns the new text and the flags: the old ones with shifted offsets plus one new Flag per
    edit whose `original` is the replaced text. The result is sorted by (start, end).
    """
    chosen: list[Edit] = []
    for edit in sorted(edits, key=lambda e: (e.start, e.end)):
        if chosen and edit.start < chosen[-1].end:
            continue
        chosen.append(edit)
    if not chosen:
        return text, list(flags)

    pieces: list[str] = []
    spans: list[tuple[int, int, int, int]] = []   # old start, old end, new start, new end
    pos = 0
    length = 0
    for edit in chosen:
        pieces.append(text[pos:edit.start])
        length += edit.start - pos
        spans.append((edit.start, edit.end, length, length + len(edit.new)))
        pieces.append(edit.new)
        length += len(edit.new)
        pos = edit.end
    pieces.append(text[pos:])
    new_text = "".join(pieces)

    def move(p: int, is_end: bool) -> int:
        shift = 0
        for old_s, old_e, new_s, new_e in spans:
            if p <= old_s:                  # before this edit
                break
            if p < old_e:                   # strictly inside the replaced text
                return new_e if is_end else new_s
            shift = new_e - old_e           # at or after the end of this edit
        return p + shift

    moved = [Flag(f.kind, move(f.start, False), move(f.end, True), f.original, f.note)
             for f in flags]
    added = [Flag(edit.kind, new_s, new_e, text[edit.start:edit.end], edit.note)
             for edit, (_os, _oe, new_s, new_e) in zip(chosen, spans)]
    return new_text, sorted(moved + added, key=lambda f: (f.start, f.end))
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_edits.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/edits.py tests/test_edits.py
git commit -m "Add text edit helper that keeps flag offsets right" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Character rules R3, R4, R5

**Files:**
- Modify: `owlocr/pipeline/repair.py` (replace the plan A stub file)
- Test: `tests/test_repair_rules.py`

**Interfaces:**
- Consumes: `spellcheck._mask_tags`, `edits.Edit`, `edits.apply_edits`, `Block`.
- Produces: `repair.repair_block(block: Block, language: str, personal_words: set[str]) -> Block` with R3 (` - ` between word characters → ` – `), R4 (`,,` → `„`), R5 (ligatures → letters); constant `LIGATURES`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_repair_rules.py`:

```python
"""Plan C: rule-based repairs (design 9.2), cases taken from the spike's measured errors."""
from owlocr.pipeline.document import Block
from owlocr.pipeline.repair import repair_block


def _block(text, label="text"):
    return Block(label=label, box=(100, 100, 900, 200), text=text, raw_text=text, flags=[])


def _repaired(block):
    return [(f.original, block.text[f.start:f.end]) for f in block.flags if f.kind == "repaired"]


def test_r3_hyphen_between_spaces_becomes_en_dash(no_dicts):
    out = repair_block(_block("Dub - strom, 4 - 19 září, a-b"), "cs", set())
    assert out.text == "Dub – strom, 4 – 19 září, a-b"
    assert [f.original for f in out.flags] == [" - ", " - "]


def test_r4_double_comma_becomes_low_quote(no_dicts):
    out = repair_block(_block("Řekl: ,,Dnes ne.“"), "cs", set())
    assert out.text == "Řekl: „Dnes ne.“"
    flag = out.flags[0]
    assert (flag.original, out.text[flag.start:flag.end]) == (",,", "„")


def test_r5_ligatures_become_plain_letters(no_dicts):
    out = repair_block(_block("proﬁl a ﬂóra, eﬀekt"), "en", set())
    assert out.text == "profil a flóra, effekt"
    assert [f.original for f in out.flags] == ["ﬁ", "ﬂ", "ﬀ"]


def test_formula_block_is_never_changed(tiny_dicts):
    block = _block("a - b = c", label="formula")
    assert repair_block(block, "cs", set()) is block
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_repair_rules.py -v
```

Expected: `3 failed, 1 passed`; for example `AssertionError: assert 'Dub - strom,... 19 září, a-b' == 'Dub – strom,... 19 září, a-b'` (the stub changes nothing; the formula test already passes).

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `owlocr/pipeline/repair.py` with:

```python
"""Rule-based corrections of known OCR error types (design 9.2 and the table of section 9).

Character rules R3, R4, R5 always run. Every change becomes a Flag of kind 'repaired' whose
`original` is the text before the change.
"""
from __future__ import annotations

import dataclasses
import re

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import Block
from owlocr.pipeline.edits import Edit, apply_edits

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}

_LIGATURE = re.compile("[" + "".join(LIGATURES) + "]")
_LOW_QUOTE = re.compile(",,")
_DASH = re.compile(r"(?<=\w) - (?=\w)")
_SKIP_LABELS = ("formula", "image", "figure")


def _char_rules(text: str) -> list[Edit]:
    """R5 ligatures, R4 low quote, R3 dash. Offsets refer to `text`; tags are never touched."""
    masked = spellcheck._mask_tags(text)
    edits = [Edit(m.start(), m.end(), LIGATURES[m.group()], "repaired", "R5: ligature")
             for m in _LIGATURE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), "„", "repaired", "R4: ,, is a low quotation mark")
              for m in _LOW_QUOTE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), " – ", "repaired", "R3: hyphen between spaces is a dash")
              for m in _DASH.finditer(masked)]
    return edits


def repair_block(block: Block, language: str, personal_words: set[str]) -> Block:
    if block.label in _SKIP_LABELS or not block.text:
        return block
    text, flags = apply_edits(block.text, list(block.flags), _char_rules(block.text))
    if text == block.text and flags == block.flags:
        return block
    return dataclasses.replace(block, text=text, flags=flags)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_repair_rules.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/repair.py tests/test_repair_rules.py
git commit -m "Repair dashes, low quotes and ligatures, each recorded as a flag" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: Word repairs R1, plain ď/ť, foreign look-alike letters (R2)

**Files:**
- Modify: `owlocr/pipeline/repair.py` (whole file shown)
- Test: `tests/test_repair_rules.py` (append)

**Interfaces:**
- Consumes: `spellcheck.available`, `spellcheck.known`, `spellcheck._words`, `spellcheck._protected`, `spellcheck._personal_lower`, `spellcheck._mask_tags`; `edits`.
- Produces: `repair.repair_block` (complete), constants `CZECH_LETTERS`, `LOOK_ALIKE`, `LIGATURES`.

Rules implemented (design 9 table and 9.2), Czech only for the word rules:
- R1: `d'`, `d’`, `t'`, `t’` inside or at the end of a word → `ď`, `ť` when the result is a dictionary word (`bud'` → `buď`, `pojišt’ovnou` → `pojišťovnou`).
- Plain letter: an unknown word whose variant with `ď`/`ť` is known is repaired (`kaprad` → `kapraď`).
- R2: a word with a letter outside the Czech alphabet and basic Latin is repaired through `LOOK_ALIKE` when that gives a dictionary word (`także` → `takže`), otherwise flagged `'foreign_letter'` (flagging works without a dictionary too).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repair_rules.py`:

```python
def test_r1_straight_apostrophe_becomes_d_caron(tiny_dicts):
    out = repair_block(_block("Rostlina je bud' velký strom, nebo malý stonek."), "cs", set())
    assert out.text == "Rostlina je buď velký strom, nebo malý stonek."
    assert _repaired(out) == [("bud'", "buď")]
    assert out.raw_text == "Rostlina je bud' velký strom, nebo malý stonek."


def test_r1_typographic_apostrophe_inside_word(tiny_dicts):
    out = repair_block(_block("Účet byl uhrazen pojišt’ovnou."), "cs", set())
    assert out.text == "Účet byl uhrazen pojišťovnou."
    assert _repaired(out) == [("pojišt’ovnou", "pojišťovnou")]


def test_r1_capital_at_sentence_start_is_repaired(tiny_dicts):
    out = repair_block(_block("Bud' strom, nebo keř."), "cs", set())
    assert out.text.startswith("Buď strom")


def test_r1_not_applied_when_result_unknown(tiny_dicts):
    out = repair_block(_block("Řekl 'jdeme spát' a odešel."), "cs", set())
    assert out.text == "Řekl 'jdeme spát' a odešel."
    assert _repaired(out) == []


def test_word_repairs_skipped_without_dictionary(no_dicts):
    out = repair_block(_block("Je to bud' strom a kaprad."), "cs", set())
    assert out.text == "Je to bud' strom a kaprad."
    assert out.flags == []


def test_plain_d_becomes_d_caron_when_only_that_is_a_word(tiny_dicts):
    out = repair_block(_block("Druh kaprad roste dole."), "cs", set())
    assert out.text == "Druh kapraď roste dole."
    assert _repaired(out) == [("kaprad", "kapraď")]


def test_known_word_with_d_is_left_alone(tiny_dicts):
    out = repair_block(_block("Roste tam dub a buk."), "cs", set())
    assert out.text == "Roste tam dub a buk."


def test_r2_foreign_letter_repaired_to_known_look_alike(tiny_dicts):
    out = repair_block(_block("Je to także velký strom."), "cs", set())
    assert out.text == "Je to takže velký strom."
    assert _repaired(out) == [("także", "takže")]


def test_r2_foreign_letter_flagged_when_no_look_alike_is_known(tiny_dicts):
    out = repair_block(_block("Je to piękný strom."), "cs", set())
    assert out.text == "Je to piękný strom."
    assert [(f.kind, f.original) for f in out.flags] == [("foreign_letter", "piękný")]
    flag = out.flags[0]
    assert out.text[flag.start:flag.end] == "piękný"


def test_r2_flags_even_without_dictionary(no_dicts):
    out = repair_block(_block("Je to także strom."), "cs", set())
    assert out.text == "Je to także strom."
    assert [(f.kind, f.original) for f in out.flags] == [("foreign_letter", "także")]


def test_r2_capitalised_name_inside_sentence_is_protected(tiny_dicts):
    out = repair_block(_block("Dopis pro pana Wałęsu je dole."), "cs", set())
    assert out.flags == []


def test_personal_word_list_protects(tiny_dicts):
    out = repair_block(_block("Je to także strom."), "cs", {"Także"})
    assert out.text == "Je to także strom."
    assert out.flags == []


def test_offsets_stay_right_after_several_length_changes(tiny_dicts):
    text = "Řekl: ,,Je to bud' ﬁkus - nebo kaprad."
    out = repair_block(_block(text), "cs", set())
    assert out.text == "Řekl: „Je to buď fikus – nebo kapraď."
    pairs = [(f.original, out.text[f.start:f.end]) for f in out.flags]
    assert pairs == [(",,", "„"), ("bud'", "buď"), ("ﬁ", "fi"), (" - ", " – "), ("kaprad", "kapraď")]


def test_english_gets_no_czech_word_rules(tiny_dicts):
    out = repair_block(_block("that’s the doctor’s letter"), "en", set())
    assert out.text == "that’s the doctor’s letter"


def test_table_html_is_not_touched_but_cells_are(tiny_dicts):
    html = "<table><tr><td>bud'</td><td>a - b</td></tr></table>"
    out = repair_block(_block(html, label="table"), "cs", set())
    assert out.text == "<table><tr><td>buď</td><td>a – b</td></tr></table>"
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_repair_rules.py -v
```

Expected: `9 failed, 10 passed`; the first failure is in `test_r1_straight_apostrophe_becomes_d_caron` (`bud'` is still there).

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `owlocr/pipeline/repair.py` with:

```python
"""Rule-based corrections of known OCR error types (design 9.2 and the table of section 9).

Character rules R3, R4, R5 always run. Word repairs (R1, plain d/t -> ď/ť, R2 look-alikes) run
only for Czech with the dictionary installed, and only when the result is a dictionary word and
the original is not (design 9.1 point 1). R2 flags foreign letters even without a dictionary.
Every change becomes a Flag of kind 'repaired' whose `original` is the text before the change.
"""
from __future__ import annotations

import dataclasses
import itertools
import re

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import Block, Flag
from owlocr.pipeline.edits import Edit, apply_edits

CZECH_LETTERS = frozenset("áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ")

# Letters from other alphabets -> Czech (or plain) letters that look alike, most likely first.
LOOK_ALIKE: dict[str, tuple[str, ...]] = {
    "ż": ("ž", "z"), "ź": ("ž", "z"), "Ż": ("Ž", "Z"), "Ź": ("Ž", "Z"),
    "ł": ("l",), "Ł": ("L",), "ľ": ("l", "ť"), "Ľ": ("L", "Ť"), "ĺ": ("l",),
    "ą": ("a", "á"), "ę": ("ě", "e", "é"), "ė": ("ě", "e"), "ć": ("č", "c"), "ś": ("š", "s"),
    "ń": ("ň", "n"), "ñ": ("ň", "n"), "ŕ": ("ř", "r"), "Ś": ("Š", "S"), "Ć": ("Č", "C"),
    "ő": ("ó", "o"), "ű": ("ů", "ú"), "ö": ("ó", "o"), "ü": ("ů", "ú"), "ä": ("á", "a"),
    "ë": ("é", "ě"), "à": ("á", "a"), "è": ("é", "ě"), "ì": ("í", "i"), "ò": ("ó", "o"),
    "ù": ("ú", "ů"), "â": ("á", "a"), "ê": ("ě", "é"), "î": ("í", "i"), "ô": ("ó", "o"),
    "û": ("ů", "ú"), "ÿ": ("ý", "y"), "ã": ("á", "a"), "õ": ("ó", "o"), "ç": ("č", "c"),
    "ğ": ("g",), "ş": ("š", "s"), "ı": ("i",), "ŭ": ("ů", "u"),
}
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_SOFTEN = {"d": "ď", "t": "ť", "D": "Ď", "T": "Ť"}

_LIGATURE = re.compile("[" + "".join(LIGATURES) + "]")
_LOW_QUOTE = re.compile(",,")
_DASH = re.compile(r"(?<=\w) - (?=\w)")
# a word containing d' or t' (straight or typographic apostrophe), e.g. bud' or pojišt’ovnou
_APOSTROPHE_WORD = re.compile(r"(?<![\w'’])[^\W\d_]*[dDtT]['’][^\W\d_]*(?![\w'’])")
_SKIP_LABELS = ("formula", "image", "figure")
_MAX_CANDIDATES = 64


def _is_foreign(ch: str) -> bool:
    return ch.isalpha() and not (ch.isascii() or ch in CZECH_LETTERS)


def _char_rules(text: str) -> list[Edit]:
    """R5 ligatures, R4 low quote, R3 dash. Offsets refer to `text`; tags are never touched."""
    masked = spellcheck._mask_tags(text)
    edits = [Edit(m.start(), m.end(), LIGATURES[m.group()], "repaired", "R5: ligature")
             for m in _LIGATURE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), "„", "repaired", "R4: ,, is a low quotation mark")
              for m in _LOW_QUOTE.finditer(masked)]
    edits += [Edit(m.start(), m.end(), " – ", "repaired", "R3: hyphen between spaces is a dash")
              for m in _DASH.finditer(masked)]
    return edits


def _first_known(candidates, original: str, language: str) -> str | None:
    for candidate in itertools.islice(candidates, _MAX_CANDIDATES):
        if candidate != original and spellcheck.known(candidate, language):
            return candidate
    return None


def _apostrophe_candidates(word: str):
    """R1: every d'/t' (straight or typographic apostrophe) becomes ď/ť."""
    yield re.sub(r"([dDtT])['’]", lambda m: _SOFTEN[m.group(1)], word)


def _soft_candidates(word: str):
    """Variants with one or more d/t replaced by ď/ť; single replacements first."""
    positions = [i for i, ch in enumerate(word) if ch in _SOFTEN][:4]
    for size in range(1, len(positions) + 1):
        for chosen in itertools.combinations(positions, size):
            letters = list(word)
            for i in chosen:
                letters[i] = _SOFTEN[letters[i]]
            yield "".join(letters)


def _look_alike_candidates(word: str):
    options = [LOOK_ALIKE.get(ch, (ch,)) if _is_foreign(ch) else (ch,) for ch in word]
    for letters in itertools.product(*options):
        yield "".join(letters)


def _word_rules(text: str, language: str,
                personal_lower: set[str]) -> tuple[list[Edit], list[Flag]]:
    """R1, plain d/t, R2. Returns edits and the 'foreign_letter' flags (offsets in `text`)."""
    masked = spellcheck._mask_tags(text)
    have_dictionary = spellcheck.available(language)
    edits: list[Edit] = []
    foreign: list[Flag] = []
    covered: list[tuple[int, int]] = []

    if have_dictionary:
        for m in _APOSTROPHE_WORD.finditer(masked):
            word = m.group()
            if spellcheck._protected(word, text, m.start(), personal_lower):
                continue
            fixed = _first_known(_apostrophe_candidates(word), word, language)
            if fixed:
                edits.append(Edit(m.start(), m.end(), fixed, "repaired",
                                  "R1: letter + apostrophe is ď/ť"))
                covered.append((m.start(), m.end()))

    for start, end, word in spellcheck._words(text):
        if any(s < end and start < e for s, e in covered):
            continue
        if spellcheck._protected(word, text, start, personal_lower):
            continue
        if any(_is_foreign(ch) for ch in word):
            fixed = None
            if have_dictionary and not spellcheck.known(word, language):
                fixed = _first_known(_look_alike_candidates(word), word, language)
            if fixed:
                edits.append(Edit(start, end, fixed, "repaired",
                                  "R2: foreign letter replaced by its Czech look-alike"))
            elif not (have_dictionary and spellcheck.known(word, language)):
                foreign.append(Flag("foreign_letter", start, end, word,
                                    "letter does not exist in Czech"))
            continue
        if (have_dictionary and any(ch in _SOFTEN for ch in word)
                and not spellcheck.known(word, language)):
            fixed = _first_known(_soft_candidates(word), word, language)
            if fixed:
                edits.append(Edit(start, end, fixed, "repaired", "d/t without its háček"))
    return edits, foreign


def repair_block(block: Block, language: str, personal_words: set[str]) -> Block:
    if block.label in _SKIP_LABELS or not block.text:
        return block
    text, flags = apply_edits(block.text, list(block.flags), _char_rules(block.text))
    if language == "cs":
        personal_lower = spellcheck._personal_lower(personal_words)
        edits, foreign = _word_rules(text, language, personal_lower)
        text, flags = apply_edits(text, flags + foreign, edits)
    if text == block.text and flags == block.flags:
        return block
    return dataclasses.replace(block, text=text, flags=flags)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_repair_rules.py -v
```

Expected: `19 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/repair.py tests/test_repair_rules.py
git commit -m "Repair d/t apostrophes, missing hacek and foreign letters when the dictionary agrees" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Layout rules: page furniture to the edges, captions out of sentences

**Files:**
- Create: `owlocr/pipeline/layout_rules.py`
- Modify: `owlocr/pipeline/layout.py`
- Test: `tests/test_layout_rules.py`

**Interfaces:**
- Consumes: `FURNITURE_LABELS`, `Block`; plan A's `layout.arrange` (renamed `_arrange_basic`).
- Produces: `layout.arrange(blocks: list[Block], language: str = "cs") -> list[Block]`; `layout_rules.furniture_to_edges(blocks) -> list[Block]`, `layout_rules.move_captions(blocks) -> list[Block]`, `layout_rules.ends_sentence(text) -> bool`, `layout_rules.starts_lower(text) -> bool`, constants `CAPTION_LABELS`, `FIGURE_RUN_LABELS`, `FLOW_LABELS`, `SENTENCE_PUNCTUATION`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_layout_rules.py`:

```python
"""Plan C: caption move, furniture order and dictionary-aware de-hyphenation (design 7.5)."""
from owlocr.pipeline.document import Block
from owlocr.pipeline.layout import arrange


def _b(label, text, box=(100, 100, 900, 200)):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def _texts(blocks):
    return [(b.label, b.text) for b in blocks]


def test_caption_in_mid_sentence_moves_after_the_paragraph(no_dicts):
    blocks = [
        _b("text", "Listy rostou na stonku a jsou", (100, 100, 900, 200)),
        _b("image", "", (100, 210, 900, 400)),
        _b("image_caption", "Obr. 3 List kapradí", (100, 410, 900, 440)),
        _b("text", "střídavé nebo vstřícné.", (100, 450, 900, 550)),
        _b("text", "Další odstavec.", (100, 560, 900, 650)),
    ]
    out = arrange(blocks, "cs")
    assert _texts(out) == [
        ("text", "Listy rostou na stonku a jsou"),
        ("text", "střídavé nebo vstřícné."),
        ("image", ""),
        ("image_caption", "Obr. 3 List kapradí"),
        ("text", "Další odstavec."),
    ]


def test_caption_after_finished_sentence_stays(no_dicts):
    blocks = [
        _b("text", "Listy jsou střídavé.", (100, 100, 900, 200)),
        _b("image_caption", "Obr. 3 List", (100, 210, 900, 240)),
        _b("text", "dále platí, že ...", (100, 250, 900, 350)),
    ]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_caption_before_capitalised_sentence_stays(no_dicts):
    blocks = [
        _b("text", "Listy jsou střídavé a", (100, 100, 900, 200)),
        _b("image_caption", "Obr. 3 List", (100, 210, 900, 240)),
        _b("text", "Další věta začíná velkým písmenem.", (100, 250, 900, 350)),
    ]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_image_without_caption_is_not_moved(no_dicts):
    blocks = [_b("text", "Listy jsou", (100, 100, 900, 200)), _b("image", "", (100, 210, 900, 400)),
              _b("text", "střídavé.", (100, 410, 900, 500))]
    assert _texts(arrange(blocks, "cs")) == _texts(blocks)


def test_furniture_goes_to_the_edges(no_dicts):
    blocks = [
        _b("text", "První odstavec."),
        _b("page_number", "12", (480, 950, 520, 970)),
        _b("header", "Kapitola 2", (100, 20, 900, 40)),
        _b("text", "Druhý odstavec."),
        _b("footer", "Učebnice botaniky", (100, 960, 900, 980)),
    ]
    out = arrange(blocks, "cs")
    assert [b.label for b in out] == ["header", "text", "text", "page_number", "footer"]


def test_page_number_at_the_top_stays_at_the_top(no_dicts):
    blocks = [_b("page_number", "7", (480, 20, 520, 40)), _b("text", "Text.")]
    assert [b.label for b in arrange(blocks, "cs")] == ["page_number", "text"]
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_layout_rules.py -v
```

Expected: `2 failed, 4 passed` (`test_caption_in_mid_sentence_moves_after_the_paragraph` and `test_furniture_goes_to_the_edges` fail with `AssertionError`; plan A's `arrange` keeps the model's order).

- [ ] **Step 3: Write minimal implementation**

3a. Create `owlocr/pipeline/layout_rules.py`:

```python
"""Plan C layout rules used by layout.arrange (design 7.5): page furniture to the page edges,
captions out of the middle of a sentence."""
from __future__ import annotations

from owlocr.pipeline.document import FURNITURE_LABELS, Block

CAPTION_LABELS = ("image_caption", "table_caption")
FIGURE_RUN_LABELS = ("image", "figure") + CAPTION_LABELS
FLOW_LABELS = ("text", "list")
SENTENCE_PUNCTUATION = ".!?…:"
_CLOSERS = "\"'“”’»)]"
_OPENERS = "\"'„“‚‘«(["


def furniture_to_edges(blocks: list[Block]) -> list[Block]:
    """Headers (and page numbers in the upper half of the page) first, footers and the other page
    numbers last, so page furniture never splits a paragraph in exports that keep it."""
    top, middle, bottom = [], [], []
    for block in blocks:
        upper_page_number = (block.label == "page_number" and block.box is not None
                             and block.box[1] < 500)
        if block.label == "header" or upper_page_number:
            top.append(block)
        elif block.label in FURNITURE_LABELS:
            bottom.append(block)
        else:
            middle.append(block)
    return top + middle + bottom


def ends_sentence(text: str) -> bool:
    stripped = text.rstrip().rstrip(_CLOSERS).rstrip()
    return not stripped or stripped[-1] in SENTENCE_PUNCTUATION


def starts_lower(text: str) -> bool:
    stripped = text.lstrip().lstrip(_OPENERS)
    return bool(stripped) and stripped[0].islower()


def move_captions(blocks: list[Block]) -> list[Block]:
    """A run of figure/caption blocks placed in the middle of a sentence (the text block before it
    ends without sentence punctuation and the text block after it starts in lower case) is moved
    after the block that continues the sentence."""
    result = list(blocks)
    i = 0
    while i < len(result):
        if result[i].label not in FIGURE_RUN_LABELS:
            i += 1
            continue
        j = i
        while j < len(result) and result[j].label in FIGURE_RUN_LABELS:
            j += 1
        run = result[i:j]
        before, after = i - 1, j
        if (any(b.label in CAPTION_LABELS for b in run)
                and before >= 0 and after < len(result)
                and result[before].label in FLOW_LABELS and result[after].label in FLOW_LABELS
                and not ends_sentence(result[before].text) and starts_lower(result[after].text)):
            result[i:after + 1] = [result[after]] + run
            i = after + 1
        else:
            i = j
    return result
```

3b. In `owlocr/pipeline/layout.py`: rename plan A's `def arrange(` to `def _arrange_basic(` (body unchanged; plan A's private `_join` and `_dehyphenate` stay as they are), add below plan A's imports:

```python
from owlocr.pipeline import layout_rules
```

and append at the end of the file:

```python
def arrange(blocks: list[Block], language: str = "cs") -> list[Block]:
    """Plan A's reading order, then the plan C rules of design 7.5."""
    blocks = _arrange_basic(blocks, language)
    blocks = layout_rules.furniture_to_edges(blocks)
    return layout_rules.move_captions(blocks)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_layout_rules.py -v
py -3.11 -m pytest -q
```

Expected: `6 passed` for the new file, and the whole suite passes (plan A's `tests/test_layout_and_stubs.py` still passes through `_arrange_basic`).

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/layout_rules.py owlocr/pipeline/layout.py tests/test_layout_rules.py
git commit -m "Move mid-sentence captions after the paragraph and furniture to page edges" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: Dictionary-aware joining of hyphenated words

**Files:**
- Modify: `owlocr/pipeline/layout_rules.py` (whole file shown), `owlocr/pipeline/layout.py` (function `arrange`)
- Test: `tests/test_layout_rules.py` (append), `tests/test_real_dictionaries.py` (create; needs the network, gated)

**Interfaces:**
- Consumes: `spellcheck.available`, `spellcheck.known`, `edits.Edit`, `edits.apply_edits`.
- Produces: `layout_rules.dehyphenate(block: Block, language: str) -> Block`; `layout.arrange` now joins `kaktu-sovitých` and `kaktu-` + line break + `sovitých` into `kaktusovitých` when the joined word is known and the hyphenated form is not (a `'repaired'` Flag records it). With a dictionary installed, plan A's unconditional line-break join is no longer used (it would turn `česko-` + line break + `slovenský` into `československý`); without a dictionary `arrange` still calls plan A's `_arrange_basic`, so plan A's behaviour and tests are unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_layout_rules.py`:

```python
def test_hyphen_inside_line_joined_when_joined_word_is_known(tiny_dicts):
    out = arrange([_b("text", "Čeleď kaktu-sovitých je velká.")], "cs")
    assert out[0].text == "Čeleď kaktusovitých je velká."
    flag = out[0].flags[0]
    assert (flag.kind, flag.original, out[0].text[flag.start:flag.end]) == (
        "repaired", "kaktu-sovitých", "kaktusovitých")


def test_hyphen_at_line_break_joined(tiny_dicts):
    out = arrange([_b("text", "Čeleď kaktu-\nsovitých je velká.")], "cs")
    assert out[0].text == "Čeleď kaktusovitých je velká."


def test_real_compound_keeps_its_hyphen(tiny_dicts):
    out = arrange([_b("text", "Je to česko-slovenský text.")], "cs")
    assert out[0].text == "Je to česko-slovenský text."
    assert out[0].flags == []


def test_no_joining_without_dictionary(no_dicts):
    out = arrange([_b("text", "Čeleď kaktu-sovitých.")], "cs")
    assert out[0].text == "Čeleď kaktu-sovitých."


def test_raw_text_is_kept(tiny_dicts):
    out = arrange([_b("text", "kaktu-sovitých")], "cs")
    assert out[0].raw_text == "kaktu-sovitých"


def test_with_a_dictionary_a_line_break_join_needs_the_dictionary(tiny_dicts):
    # plan A alone would join this into "československý"; the dictionary knows the hyphenated form
    out = arrange([_b("text", "Je to česko-\nslovenský text.")], "cs")
    assert out[0].text == "Je to česko-\nslovenský text."
```

Create `tests/test_real_dictionaries.py` (all rules of tasks 3–9 against the real pinned Czech dictionary and the spike's error examples):

```python
"""Plan C: the real dictionaries against the error examples measured in the spike.

Needs the network: run with OWLOCR_NETWORK_TESTS=1 (skipped otherwise)."""
import os

import pytest

from owlocr.pipeline import dictionaries, spellcheck


@pytest.mark.skipif(os.environ.get("OWLOCR_NETWORK_TESTS") != "1",
                    reason="set OWLOCR_NETWORK_TESTS=1 to download the real dictionaries")
def test_real_czech_dictionary_handles_the_spike_examples(no_dicts):
    from owlocr.pipeline import layout, repair
    from owlocr.pipeline.document import Block

    dictionaries.download("cs")
    cases = {
        "Je to bud' pravda, nebo lež.": "Je to buď pravda, nebo lež.",
        "Účet byl uhrazen pojišt’ovnou.": "Účet byl uhrazen pojišťovnou.",
        "Druh kaprad roste v lese.": "Druh kapraď roste v lese.",
        "Je to także dobré.": "Je to takže dobré.",
        "Čeleď kaktu-sovitých roste v poušti.": "Čeleď kaktusovitých roste v poušti.",
    }
    for raw, expected in cases.items():
        block = layout.arrange([Block("text", (0, 0, 999, 999), raw, raw, [])], "cs")[0]
        assert repair.repair_block(block, "cs", set()).text == expected, raw
    text = "Rod Opuntia patří mezi bylinny druh."
    flagged = spellcheck.flag_suspicious(Block("text", None, text, text, []), "cs", set())
    assert [(f.kind, f.original) for f in flagged.flags] == [("suspicious", "bylinny")]
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_layout_rules.py -v
```

Expected: `2 failed, 10 passed`: `test_hyphen_inside_line_joined_when_joined_word_is_known` (`AssertionError: assert 'Čeleď kaktu-...ých je velká.' == 'Čeleď kaktus...ých je velká.'`) and `test_with_a_dictionary_a_line_break_join_needs_the_dictionary` (plan A joined the compound); `test_hyphen_at_line_break_joined` already passes through plan A's rule. With the network:

```
$env:OWLOCR_NETWORK_TESTS = "1"; py -3.11 -m pytest tests/test_real_dictionaries.py -v; Remove-Item Env:OWLOCR_NETWORK_TESTS
```

Expected: `1 failed`, `AssertionError: Čeleď kaktu-sovitých roste v poušti.` (without the variable the test is skipped).

- [ ] **Step 3: Write minimal implementation**

3a. Replace the whole content of `owlocr/pipeline/layout_rules.py` with:

```python
"""Plan C layout rules used by layout.arrange (design 7.5): page furniture to the page edges,
captions out of the middle of a sentence, dictionary-aware joining of hyphenated words."""
from __future__ import annotations

import dataclasses
import re

from owlocr.pipeline import spellcheck
from owlocr.pipeline.document import FURNITURE_LABELS, Block
from owlocr.pipeline.edits import Edit, apply_edits

CAPTION_LABELS = ("image_caption", "table_caption")
FIGURE_RUN_LABELS = ("image", "figure") + CAPTION_LABELS
FLOW_LABELS = ("text", "list")
SENTENCE_PUNCTUATION = ".!?…:"
_CLOSERS = "\"'“”’»)]"
_OPENERS = "\"'„“‚‘«(["
# word, hyphen, optional line break, word: "kaktu-sovitých" or "kaktu-\nsovitých"
_SPLIT_WORD = re.compile(r"(?<![\w-])([^\W\d_]+)-(?:[ \t]*\n[ \t]*)?([^\W\d_]+)(?![\w-])")
_DEHYPHENATE_LABELS = FLOW_LABELS + CAPTION_LABELS + ("title",)


def furniture_to_edges(blocks: list[Block]) -> list[Block]:
    """Headers (and page numbers in the upper half of the page) first, footers and the other page
    numbers last, so page furniture never splits a paragraph in exports that keep it."""
    top, middle, bottom = [], [], []
    for block in blocks:
        upper_page_number = (block.label == "page_number" and block.box is not None
                             and block.box[1] < 500)
        if block.label == "header" or upper_page_number:
            top.append(block)
        elif block.label in FURNITURE_LABELS:
            bottom.append(block)
        else:
            middle.append(block)
    return top + middle + bottom


def ends_sentence(text: str) -> bool:
    stripped = text.rstrip().rstrip(_CLOSERS).rstrip()
    return not stripped or stripped[-1] in SENTENCE_PUNCTUATION


def starts_lower(text: str) -> bool:
    stripped = text.lstrip().lstrip(_OPENERS)
    return bool(stripped) and stripped[0].islower()


def move_captions(blocks: list[Block]) -> list[Block]:
    """A run of figure/caption blocks placed in the middle of a sentence (the text block before it
    ends without sentence punctuation and the text block after it starts in lower case) is moved
    after the block that continues the sentence."""
    result = list(blocks)
    i = 0
    while i < len(result):
        if result[i].label not in FIGURE_RUN_LABELS:
            i += 1
            continue
        j = i
        while j < len(result) and result[j].label in FIGURE_RUN_LABELS:
            j += 1
        run = result[i:j]
        before, after = i - 1, j
        if (any(b.label in CAPTION_LABELS for b in run)
                and before >= 0 and after < len(result)
                and result[before].label in FLOW_LABELS and result[after].label in FLOW_LABELS
                and not ends_sentence(result[before].text) and starts_lower(result[after].text)):
            result[i:after + 1] = [result[after]] + run
            i = after + 1
        else:
            i = j
    return result


def dehyphenate(block: Block, language: str) -> Block:
    """Join a word split by a line-break hyphen when the joined word is in the dictionary and the
    hyphenated form is not. Without a dictionary nothing is joined. Each join is a Flag."""
    if block.label not in _DEHYPHENATE_LABELS or "-" not in block.text:
        return block
    if not spellcheck.available(language):
        return block
    edits = []
    for m in _SPLIT_WORD.finditer(block.text):
        joined = m.group(1) + m.group(2)
        hyphenated = f"{m.group(1)}-{m.group(2)}"
        if spellcheck.known(joined, language) and not spellcheck.known(hyphenated, language):
            edits.append(Edit(m.start(), m.end(), joined, "repaired",
                              "word split by a line-break hyphen joined"))
    if not edits:
        return block
    text, flags = apply_edits(block.text, list(block.flags), edits)
    return dataclasses.replace(block, text=text, flags=flags)
```

3b. In `owlocr/pipeline/layout.py` add below plan A's imports:

```python
from owlocr.pipeline import spellcheck
```

and replace the function `arrange` with:

```python
def arrange(blocks: list[Block], language: str = "cs") -> list[Block]:
    """Design 7.5. Without a dictionary plan A's rule joins a line-break hyphen when a lower-case
    letter follows; with a dictionary layout_rules.dehyphenate decides for both forms
    (kaktu- at the end of a line and kaktu-sovitých in one line) and records each join as a Flag."""
    if not spellcheck.available(language):
        blocks = _arrange_basic(blocks, language)
    blocks = layout_rules.furniture_to_edges(blocks)
    blocks = layout_rules.move_captions(blocks)
    return [layout_rules.dehyphenate(block, language) for block in blocks]
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_layout_rules.py -v
```

Expected: `12 passed`. Then:

```
$env:OWLOCR_NETWORK_TESTS = "1"; py -3.11 -m pytest tests/test_real_dictionaries.py -v; Remove-Item Env:OWLOCR_NETWORK_TESTS
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/layout_rules.py owlocr/pipeline/layout.py tests/test_layout_rules.py tests/test_real_dictionaries.py
git commit -m "Join line-break hyphens only when the dictionary knows the joined word" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Sideways check and rotation helper

**Files:**
- Modify: `owlocr/pipeline/guards.py` (one import + appended section)
- Test: `tests/test_orientation.py`

**Interfaces:**
- Consumes: Pillow (plan A already imports `Image`, `ImageFilter` and `Path` in `guards.py`), numpy; `tests/fixtures/pages/*.png` (plan A task 2).
- Produces: `guards.looks_sideways(image: Path) -> bool`; `guards.rotate_image(image: Path, degrees: int, out: Path) -> Path`, which turns the image **clockwise** (the saved image equals `Image.rotate(-degrees, expand=True)` of the input: the convention of `Page.rotation_applied` that plan B uses to reproduce the read image); constants `ROTATIONS = (0, 90, 180, 270)`, `SIDEWAYS_RATIO = 3.0`, `INK_BELOW_BACKGROUND = 0.25`.

Like plan A's `is_blank`, the check measures darkness against the page itself, not against a fixed grey level: the page is normalised between its 1st percentile (ink) and its median (paper), so a grey, low-contrast scan behaves like a clean one. Calibration on the ten generated pages and ten real book pages of the spike: the ratio "column-profile variation / row-profile variation" is at most 1.4 on every upright page (the phone photo is the highest, the poor scans are 0.1) and 20 on the rotated letter, also after the contrast was squeezed to grey levels 150–213; the threshold 3.0 leaves a wide margin on both sides.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orientation.py`:

```python
"""Plan C: orientation guards (design 7.2 and 7.3)."""
import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from owlocr.engine.protocol import PageResult
from owlocr.pipeline import guards

PAGES = Path(__file__).parent / "fixtures" / "pages"
GOOD = "<|det|>text [100, 100, 900, 200]<|/det|>Rostlina je velký strom a list je malý."
BAD = "<|det|>text [100, 100, 900, 200]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam."


def _lines_image(path: Path, sideways: bool) -> Path:
    """Lines of 'words' (black bars of random width) like a page of text."""
    rng = random.Random(7)
    img = Image.new("L", (800, 1100), 255)
    draw = ImageDraw.Draw(img)
    for top in range(100, 1000, 40):
        left = 80
        while True:
            width = rng.randint(20, 110)
            if left + width > 720:
                break
            draw.rectangle((left, top, left + width, top + 14), fill=0)
            left += width + rng.randint(10, 18)
    if sideways:
        img = img.rotate(90, expand=True)
    img.save(path)
    return path


def test_upright_fixture_is_not_sideways():
    assert guards.looks_sideways(PAGES / "01_letter_clean.png") is False


def test_rotated_fixture_is_sideways():
    assert guards.looks_sideways(PAGES / "09_letter_rotated_90.png") is True


def test_other_fixtures_are_not_sideways():
    for name in ("02_textbook_clean", "03_small_print_clean", "04_table_clean",
                 "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo",
                 "08_screenshot", "10_blank_page"):
        assert guards.looks_sideways(PAGES / f"{name}.png") is False, name


def test_grey_low_contrast_scans_work_too(tmp_path):
    """Normalised against the page's own brightness: grey paper, grey ink."""
    for name, sideways in (("01_letter_clean", False), ("05_letter_poor_scan", False),
                           ("09_letter_rotated_90", True)):
        with Image.open(PAGES / f"{name}.png") as img:
            low = Image.eval(img.convert("L"), lambda v: int(v * 0.25 + 150))   # 150..213
        path = tmp_path / f"{name}_grey.png"
        low.save(path)
        assert guards.looks_sideways(path) is sideways, name


def test_drawn_lines(tmp_path):
    assert guards.looks_sideways(_lines_image(tmp_path / "up.png", False)) is False
    assert guards.looks_sideways(_lines_image(tmp_path / "side.png", True)) is True


def test_rotate_image_turns_clockwise(tmp_path):
    src = tmp_path / "src.png"
    img = Image.new("RGB", (40, 20), "white")
    img.putpixel((39, 0), (255, 0, 0))              # red dot in the top-right corner
    img.save(src)
    out = guards.rotate_image(src, 90, tmp_path / "out.png")
    with Image.open(out) as rotated:
        assert rotated.size == (20, 40)
        assert rotated.getpixel((19, 39)) == (255, 0, 0)  # top-right went to bottom-right
    with Image.open(src) as original, Image.open(out) as rotated:
        # plan B reproduces the read image exactly like this
        assert rotated.tobytes() == original.rotate(-90, expand=True).tobytes()
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_orientation.py -v
```

Expected: `6 failed`: `AttributeError: module 'owlocr.pipeline.guards' has no attribute 'looks_sideways'` (and `rotate_image`).

- [ ] **Step 3: Write minimal implementation**

3a. Add below plan A's imports in `owlocr/pipeline/guards.py`:

```python
import numpy as np
```

3b. Append at the end of `owlocr/pipeline/guards.py`:

```python
# ---- plan C: orientation ---------------------------------------------------------------------

ROTATIONS = (0, 90, 180, 270)   # clockwise, as Page.rotation_applied (agreed with plan B)
SIDEWAYS_RATIO = 3.0            # the column profile is this many times more varied than the rows
INK_BELOW_BACKGROUND = 0.25     # ink = a quarter of the ink-to-paper range darker than around it
_MIN_CONTRAST = 8               # grey levels between ink and paper; less = an even, empty page
_MIN_INK = 0.001


def rotate_image(image: Path, degrees: int, out: Path) -> Path:
    """Save `image` turned CLOCKWISE by `degrees` (0, 90, 180, 270) to `out`.

    Same convention as Page.rotation_applied: plan B reproduces the read image with
    Image.rotate(-rotation_applied, expand=True)."""
    with Image.open(image) as img:
        img.load()
        rotated = img if degrees % 360 == 0 else img.rotate(-degrees, expand=True)
        rotated.save(out)
    return out


def _profile_variation(values: np.ndarray) -> float:
    mean = float(values.mean())
    return 0.0 if mean == 0 else float(values.var()) / (mean * mean)


def looks_sideways(image: Path) -> bool:
    """True when the text lines seem to run vertically (design 7.2).

    The page is first normalised against its own brightness (1st percentile = ink, median =
    paper), so grey, low-contrast scans behave like clean ones. Ink = pixels clearly darker than
    their neighbourhood, so a dark background around a photo of a page does not count. Upright
    text makes the row profile of ink vary strongly (lines and gaps) and the column profile flat;
    sideways text does the opposite.
    """
    with Image.open(image) as img:
        grey = img.convert("L")
    grey.thumbnail((1000, 1000))
    pixels = np.asarray(grey, dtype=np.float64)
    ink_level, paper = np.percentile(pixels, 1), np.percentile(pixels, 50)
    if paper - ink_level < _MIN_CONTRAST:
        return False
    norm = np.clip((pixels - ink_level) / (paper - ink_level), 0.0, 1.5)
    as_image = Image.fromarray(np.uint8(np.round(norm / 1.5 * 255)))
    background = np.asarray(as_image.filter(ImageFilter.BoxBlur(15)), dtype=np.float64) / 255 * 1.5
    ink = (norm < background - INK_BELOW_BACKGROUND).astype(np.float64)
    if ink.mean() < _MIN_INK:
        return False
    rows = _profile_variation(ink.mean(axis=1))
    cols = _profile_variation(ink.mean(axis=0))
    return cols > SIDEWAYS_RATIO * max(rows, 1e-9)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_orientation.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/guards.py tests/test_orientation.py
git commit -m "Detect sideways pages from brightness-normalised ink profiles" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Dictionary hit rate and best rotation probe

**Files:**
- Modify: `owlocr/pipeline/guards.py` (one import + appended section)
- Test: `tests/test_orientation.py` (append)

**Interfaces:**
- Consumes: `spellcheck.available`, `spellcheck._hit_rate`; `parse.parse_raw(raw) -> list[Block]` (imported inside the function); any engine with `ocr_page(image, mode, max_new_tokens=..., time_limit_s=...) -> PageResult` (duck-typed, like `SubprocessEngine`).
- Produces: `guards.dictionary_hit_rate(text: str, language: str) -> float` (1.0 without dictionary, 0.0 when the text has no words), `guards.best_rotation(image: Path, engine, language: str) -> int` (0, 90, 180 or 270, clockwise, relative to `image`; probes named `<image stem>_probe<degrees>.png` next to the image, Fast mode, 120 tokens, deleted afterwards; a cancelled probe ends the probing and returns 0; `EngineError` is not caught); constants `PROBE_TOKENS = 120`, `PROBE_TIME_LIMIT_S = 60.0`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orientation.py`:

```python
class CannedEngine:
    """Answers with GOOD for one orientation of the probe and BAD for the others."""

    def __init__(self, good_degrees: int):
        self.good = good_degrees
        self.calls = []
        self.cancel_after = None          # answer "cancelled" from this call on (1-based)

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        self.calls.append((Path(image).name, mode, max_new_tokens))
        text = GOOD if Path(image).stem.endswith(f"_probe{self.good}") else BAD
        cancelled = self.cancel_after is not None and len(self.calls) >= self.cancel_after
        return PageResult(text="" if cancelled else text, seconds=0.1, prefix_tokens=1,
                          output_tokens=10, hit_token_cap=False, cancelled=cancelled,
                          timed_out=False, peak_vram_mib=0)


def test_hit_rate_with_dictionary(tiny_dicts):
    assert guards.dictionary_hit_rate("Rostlina je velký strom.", "cs") == 1.0
    assert guards.dictionary_hit_rate("Rostlina je xqzt wvpl.", "cs") == 0.5
    assert guards.dictionary_hit_rate("123 456", "cs") == 0.0


def test_hit_rate_without_dictionary_is_one(no_dicts):
    assert guards.dictionary_hit_rate("xqzt wvpl", "cs") == 1.0


@pytest.mark.parametrize("good", [0, 90, 180, 270])
def test_best_rotation_picks_the_readable_orientation(tiny_dicts, tmp_path, good):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(good)
    assert guards.best_rotation(image, engine, "cs") == good
    assert [c[1:] for c in engine.calls] == [("fast", 120)] * 4
    assert not list(tmp_path.glob("*_probe*.png"))            # probes are cleaned up


def test_best_rotation_without_dictionary_makes_no_probe(no_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(90)
    assert guards.best_rotation(image, engine, "cs") == 0
    assert engine.calls == []


def test_best_rotation_stops_at_a_cancelled_probe(tiny_dicts, tmp_path):
    image = tmp_path / "page.png"
    Image.new("L", (300, 400), 255).save(image)
    engine = CannedEngine(180)
    engine.cancel_after = 2
    assert guards.best_rotation(image, engine, "cs") == 0
    assert len(engine.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_orientation.py -v
```

Expected: `8 failed, 6 passed`: `AttributeError: module 'owlocr.pipeline.guards' has no attribute 'dictionary_hit_rate'` (and `best_rotation`).

- [ ] **Step 3: Write minimal implementation**

3a. Add below plan A's imports in `owlocr/pipeline/guards.py`:

```python
from owlocr.pipeline import spellcheck
```

3b. Append at the end of `owlocr/pipeline/guards.py`:

```python
PROBE_TOKENS = 120              # design 7.3: probes read only the start of the page
PROBE_TIME_LIMIT_S = 60.0


def dictionary_hit_rate(text: str, language: str) -> float:
    """Share of the words the dictionary knows; 1.0 without a dictionary, 0.0 without words."""
    rate = spellcheck._hit_rate(text, language)
    return 1.0 if rate is None else rate


def best_rotation(image: Path, engine, language: str) -> int:
    """Read the image in all four orientations with a short Fast-mode probe and return the
    clockwise rotation (0, 90, 180, 270) whose text the dictionary knows best.
    Without a dictionary no probe is made and 0 is returned. A cancelled probe ends the probing
    and returns 0 ("keep the page as it is"); EngineError is not caught."""
    from owlocr.pipeline.parse import parse_raw   # local: parse may import guards

    if not spellcheck.available(language):
        return 0
    best, best_rate = 0, -1.0
    for degrees in ROTATIONS:
        probe = rotate_image(image, degrees, image.with_name(f"{image.stem}_probe{degrees}.png"))
        try:
            result = engine.ocr_page(probe, "fast", max_new_tokens=PROBE_TOKENS,
                                     time_limit_s=PROBE_TIME_LIMIT_S)
        finally:
            probe.unlink(missing_ok=True)
        if result.cancelled:
            return 0
        text = "\n".join(block.text for block in parse_raw(result.text))
        rate = dictionary_hit_rate(text, language)
        if rate > best_rate:
            best, best_rate = degrees, rate
    return best
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_orientation.py -v
```

Expected: `14 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/guards.py tests/test_orientation.py
git commit -m "Probe four rotations with short fast reads and pick the most readable" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 12: Cut tall images into overlapping strips

**Files:**
- Modify: `owlocr/pipeline/pages.py` (appended section; plan A already imports `Path` and `Image`)
- Test: `tests/test_strips.py`

**Interfaces:**
- Consumes: Pillow.
- Produces: `pages.cut_strips(image: Path, out_dir: Path) -> list[tuple[Path, int, int]]` (strip file `<image stem>_strip<N>.png`, top px, bottom px); strip height = 2 × width, overlap = max(80 px, 0.25 × width) and at most half a strip; constants `STRIP_HEIGHT_RATIO`, `STRIP_OVERLAP_RATIO`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_strips.py`:

```python
"""Plan C: cutting tall images into overlapping strips (design 7.1)."""
from PIL import Image

from owlocr.pipeline.pages import cut_strips


def test_tall_image_is_cut_into_overlapping_strips(tmp_path):
    image = tmp_path / "chat.png"
    Image.new("RGB", (400, 2000), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert [(top, bottom) for _p, top, bottom in strips] == [(0, 800), (700, 1500), (1400, 2000)]
    for path, top, bottom in strips:
        with Image.open(path) as strip:
            assert strip.size == (400, bottom - top)
    assert strips[0][0].name == "chat_strip1.png"


def test_image_that_fits_one_strip_gives_one_strip(tmp_path):
    image = tmp_path / "short.png"
    Image.new("RGB", (400, 700), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert [(top, bottom) for _p, top, bottom in strips] == [(0, 700)]


def test_overlap_has_a_minimum_for_narrow_images(tmp_path):
    image = tmp_path / "narrow.png"
    Image.new("RGB", (100, 1000), "white").save(image)
    strips = cut_strips(image, tmp_path / "strips")
    assert strips[1][1] == strips[0][2] - 80
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_strips.py -v
```

Expected: collection error `ImportError: cannot import name 'cut_strips' from 'owlocr.pipeline.pages'`.

- [ ] **Step 3: Write minimal implementation**

Append at the end of `owlocr/pipeline/pages.py`:

```python
# ---- plan C: tall images (design 7.1) -------------------------------------------------------

STRIP_HEIGHT_RATIO = 2.0       # each strip is at most twice as tall as it is wide
STRIP_OVERLAP_RATIO = 0.25     # neighbouring strips share a quarter of the width in height
_MIN_OVERLAP_PX = 80


def cut_strips(image: Path, out_dir: Path) -> list[tuple[Path, int, int]]:
    """Cut a tall image into overlapping horizontal strips.

    Returns (strip png, top px, bottom px) from top to bottom; the last strip ends at the bottom
    of the image. Strips are saved into `out_dir` as <image stem>_strip<N>.png.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image) as img:
        img.load()
        width, height = img.size
        strip = max(1, round(width * STRIP_HEIGHT_RATIO))
        overlap = min(strip // 2, max(_MIN_OVERLAP_PX, round(width * STRIP_OVERLAP_RATIO)))
        result = []
        top = 0
        while True:
            bottom = min(top + strip, height)
            path = out_dir / f"{image.stem}_strip{len(result) + 1}.png"
            img.crop((0, top, width, bottom)).save(path)
            result.append((path, top, bottom))
            if bottom >= height:
                return result
            top = bottom - overlap
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_strips.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/pages.py tests/test_strips.py
git commit -m "Cut tall images into overlapping strips" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 13: Orientation check inside process_page

**Files:**
- Modify: `owlocr/pipeline/process.py` (one import, new helpers above `process_page`, `process_page` replaced)
- Test: `tests/test_process_orientation.py`, `tests/test_rotation_fake_worker.py`

**Interfaces:**
- Consumes: plan A's `process.py` helpers `_use_text_layer`, `_text_layer_blocks`, `_has_text`, `_read`, `cleanup`, `ProcessOptions` and its imports (`is_blank`, `is_runaway`, `trim_runaway`, `parse_raw`, `render_page`, `layout`, `repair`, `spellcheck`); `guards.looks_sideways`, `guards.rotate_image`, `guards.best_rotation`, `guards.dictionary_hit_rate`; for the second test `SubprocessEngine(python, worker_script, model_dir, device, dtype, log_file, env=None)` with `load()` and `stop()`, and `tests.conftest.FAKE_WORKER`, `PAGES`.
- Produces: `process.process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path, on_progress: Callable[[int], None] | None = None, cancel: threading.Event | None = None) -> Page` (contract signature unchanged); warning `process.W_ROTATED = "rotated"` added to plan A's `empty_retried`, `empty`, `runaway`, `time_limit`, `cancelled`; private `_Reading`, `_read_once` (plan A's reading logic, moved unchanged), `_read_image`, `_Relay`, `_language`, `_rate`, `_wrong_orientation`; constants `ORIENTATION_MIN_WORDS = 10`, `ORIENTATION_MIN_RATE = 0.5`.

Behaviour (design 7.2 and 7.3): a page that `looks_sideways` is turned 90° clockwise before OCR. After reading, when a dictionary is installed, the page has at least 10 words and fewer than 50 % of them are known, `best_rotation` probes the four orientations of the read image; if another one wins, the page (as rendered) is turned by the total and read again, and that reading is kept when the dictionary knows more of its words. `Page.rotation_applied` is the number of degrees **clockwise** applied to the rendered page image before reading (plan B reproduces the read image with `Image.rotate(-rotation_applied, expand=True)`); block boxes refer to that image and `Page.width_px`/`height_px` are its size. The probes get the page's `on_progress` and `cancel` through `_Relay`, so Cancel and "Stop engine" stop them too; a cancelled probe means "keep the page as it is", never "empty page"; `EngineError` from any call reaches the caller unchanged (plan A contract note 1). Scratch file names: `page_<index:04d>.png` (plan A), `page_<index:04d>_r<degrees>.png`, probes `..._probe<degrees>.png`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_process_orientation.py`:

```python
"""Plan C: orientation, dictionaries and (task 14) strips inside process_page (design 7.1-7.3)."""
import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from owlocr.engine.protocol import EngineError, PageResult
from owlocr.pipeline import pages, process
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, process_page
from tests.conftest import PAGES

IMAGE_PAGE = PageSource(index=0, kind="image", text_layer=None)
GOOD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je velký strom a list je malý. "
        "Dub a buk jsou dřevitý druh.")
BAD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam. "
       "Bdu a kbu uojs tývěřd hurd.")


def _result(text, **changes):
    values = dict(text=text, seconds=0.1, prefix_tokens=1, output_tokens=10, hit_token_cap=False,
                  cancelled=False, timed_out=False, peak_vram_mib=0)
    values.update(changes)
    return PageResult(**values)


class ScriptedEngine:
    """Answers like tests/fake_worker.py: the content of '<image path>.raw.txt' when it exists.
    `answer(path, mode)` may override it (return a PageResult or text, or raise)."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls = []

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        image = Path(image)
        self.calls.append({"name": image.name, "mode": mode, "max_new_tokens": max_new_tokens,
                           "on_progress": on_progress, "cancel": cancel})
        if self.answer is not None:
            answer = self.answer(image, mode)
            if answer is not None:
                return answer if isinstance(answer, PageResult) else _result(answer)
        canned = Path(str(image) + ".raw.txt")
        if canned.exists():
            return _result(canned.read_text(encoding="utf-8"))
        return _result(f"<|det|>text [100, 100, 900, 200]<|/det|>fake text for {image.name}")


def _text_image(path: Path, size=(800, 1000)) -> Path:
    img = Image.new("L", size, 255)
    draw = ImageDraw.Draw(img)
    for top in range(80, size[1] - 80, 40):
        draw.rectangle((60, top, size[0] - 60, top + 12), fill=0)
    img.save(path)
    return path


def _upside_down_after_turn(tmp_path) -> tuple[Path, Path]:
    """The rotated letter turned another 180°: the first 90° turn leaves it upside down."""
    source = tmp_path / "turned_the_other_way.png"
    with Image.open(PAGES / "09_letter_rotated_90.png") as img:
        img.rotate(180, expand=True).save(source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "page_0000_r90.png.raw.txt").write_text(BAD, encoding="utf-8")
    for degrees in (0, 90, 180, 270):
        (scratch / f"page_0000_r90_probe{degrees}.png.raw.txt").write_text(
            GOOD if degrees == 180 else BAD, encoding="utf-8")
    (scratch / "page_0000_r270.png.raw.txt").write_text(GOOD, encoding="utf-8")
    return source, scratch


def test_rotated_letter_is_turned_upright(tiny_dicts, tmp_path):
    # the fixture is an upright letter turned 90° counter-clockwise; one clockwise turn fixes it
    source = tmp_path / "09_letter_rotated_90.png"
    shutil.copy(PAGES / "09_letter_rotated_90.png", source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "page_0000_r90.png.raw.txt").write_text(GOOD, encoding="utf-8")
    engine = ScriptedEngine()
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert page.rotation_applied == 90
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png"]      # no probes needed
    with Image.open(source) as original:
        assert (page.width_px, page.height_px) == (original.height, original.width)


def test_upside_down_after_the_turn_is_found_by_probing(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)
    engine = ScriptedEngine()
    progress, cancel = [].append, threading.Event()
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch,
                        on_progress=progress, cancel=cancel)
    assert page.rotation_applied == 270
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert process.W_ROTATED in page.warnings
    probes = [c for c in engine.calls if "_probe" in c["name"]]
    assert [(c["mode"], c["max_new_tokens"]) for c in probes] == [("fast", 120)] * 4
    assert all(c["on_progress"] is progress and c["cancel"] is cancel for c in engine.calls)
    with (Image.open(scratch / "page_0000.png") as rendered,
          Image.open(scratch / "page_0000_r270.png") as read):
        # plan B reproduces the read image from the page image with rotate(-rotation_applied)
        assert read.tobytes() == rendered.rotate(-270, expand=True).tobytes()


def test_a_cancelled_probe_is_not_taken_for_a_page(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if "_probe" in image.name:
            return _result("", cancelled=True)
        return None

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"), scratch)
    assert [c["name"] for c in engine.calls] == ["page_0000_r90.png", "page_0000_r90_probe0.png"]
    assert page.rotation_applied == 90 and process.W_ROTATED not in page.warnings
    assert page.blocks[0].text.startswith("Rtsnl")                 # the first reading is kept


def test_engine_errors_in_a_probe_reach_the_caller(tiny_dicts, tmp_path):
    source, scratch = _upside_down_after_turn(tmp_path)

    def answer(image, mode):
        if "_probe" in image.name:
            raise EngineError("died", "worker gone")
        return None

    with pytest.raises(EngineError) as error:
        process_page(source, IMAGE_PAGE, ScriptedEngine(answer), ProcessOptions(language="cs"),
                     scratch)
    assert error.value.kind == "died"


def test_no_probes_without_a_dictionary(no_dicts, tmp_path):
    source = _text_image(tmp_path / "upright.png")
    engine = ScriptedEngine(lambda image, mode: BAD)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == 1 and page.rotation_applied == 0


def test_upright_page_with_known_words_is_not_probed(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "upright.png")
    engine = ScriptedEngine(lambda image, mode: GOOD)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == 1 and page.rotation_applied == 0


def test_repairs_and_flags_are_applied(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "page.png")
    text = "<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je bud' strom, nebo bylinny list."
    page = process_page(source, IMAGE_PAGE, ScriptedEngine(lambda image, mode: text),
                        ProcessOptions(language="cs"), tmp_path / "scratch")
    block = page.blocks[0]
    assert block.text == "Rostlina je buď strom, nebo bylinny list."
    assert block.raw_text == "Rostlina je bud' strom, nebo bylinny list."
    assert [(f.kind, f.original) for f in block.flags] == [("repaired", "bud'"),
                                                           ("suspicious", "bylinny")]


def test_auto_language_picks_english(tiny_dicts, tmp_path):
    source = _text_image(tmp_path / "page.png")
    text = ("<|det|>text [100, 100, 900, 300]<|/det|>This is the doctor and the report "
            "of the green tree.")
    page = process_page(source, IMAGE_PAGE, ScriptedEngine(lambda image, mode: text),
                        ProcessOptions(language="auto"), tmp_path / "scratch")
    assert page.blocks[0].flags == []
```

Create `tests/test_rotation_fake_worker.py` (the rotation test through the real client and the fake worker, which answers with the content of `<image path>.raw.txt`):

```python
"""Plan C: the rotated fixture page through the real engine client and tests/fake_worker.py.

The fake worker answers an `ocr` request with the content of '<image path>.raw.txt' when that
file exists, so the canned text of every rotation is written next to the image names that
process_page and guards.best_rotation create in the scratch folder. The fixture is turned by
another 180° first, so that the first 90° turn leaves it upside down and the probes through the
real client have to find the remaining 180°.
"""
import sys

from PIL import Image

from owlocr.engine.client import SubprocessEngine
from owlocr.pipeline import process
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, process_page
from tests.conftest import FAKE_WORKER, PAGES

GOOD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rostlina je velký strom a list je malý. "
        "Dub a buk jsou dřevitý druh.")
BAD = ("<|det|>text [100, 100, 900, 300]<|/det|>Rtsnl ej kýlev mrots a tsil ej ýlam. "
       "Bdu a kbu uojs tývěřd hurd.")


def test_rotated_letter_through_the_fake_worker(tiny_dicts, tmp_path):
    source = tmp_path / "turned_the_other_way.png"
    with Image.open(PAGES / "09_letter_rotated_90.png") as img:
        img.rotate(180, expand=True).save(source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "page_0000_r90.png.raw.txt").write_text(BAD, encoding="utf-8")
    for degrees in (0, 90, 180, 270):
        (scratch / f"page_0000_r90_probe{degrees}.png.raw.txt").write_text(
            GOOD if degrees == 180 else BAD, encoding="utf-8")
    (scratch / "page_0000_r270.png.raw.txt").write_text(GOOD, encoding="utf-8")
    engine = SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER,
                              model_dir=tmp_path / "model", device="cpu", dtype="float32",
                              log_file=tmp_path / "logs" / "engine.log")
    try:
        engine.load()                                   # starts the fake worker, then loads
        page = process_page(source, PageSource(0, "image", None), engine,
                            ProcessOptions(language="cs"), scratch)
    finally:
        engine.stop()
    assert page.rotation_applied == 270
    assert page.blocks[0].text.startswith("Rostlina je velký strom")
    assert process.W_ROTATED in page.warnings
    with Image.open(source) as original:
        assert (page.width_px, page.height_px) == (original.height, original.width)
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_process_orientation.py tests/test_rotation_fake_worker.py -v
```

Expected: `5 failed, 4 passed`: `test_rotated_letter_is_turned_upright` (`AssertionError: assert 0 == 90`), `test_upside_down_after_the_turn_is_found_by_probing` and `test_rotated_letter_through_the_fake_worker` (`assert 0 == 270`), `test_a_cancelled_probe_is_not_taken_for_a_page` (`AssertionError` on the list of engine calls) and `test_engine_errors_in_a_probe_reach_the_caller` (`Failed: DID NOT RAISE`): plan A never turns a page.

- [ ] **Step 3: Write minimal implementation**

3a. Add below plan A's imports in `owlocr/pipeline/process.py`:

```python
from owlocr.pipeline import guards
```

3b. Add these definitions directly above `def process_page(` in `owlocr/pipeline/process.py` (below plan A's `_read`):

```python
ORIENTATION_MIN_WORDS = 10       # fewer words say nothing about the orientation
ORIENTATION_MIN_RATE = 0.5       # design 7.3: under 50 % known words -> probe the other rotations
W_ROTATED = "rotated"            # warning: the post-OCR check turned the page and read it again


@dataclass
class _Reading:
    blocks: list[Block]
    raw: str
    mode: str
    warnings: list[str]
    cancelled: bool
    timed_out: bool

    @property
    def stopped(self) -> bool:
        return self.cancelled or self.timed_out


def _read_once(engine, image: Path, options: ProcessOptions, on_progress, cancel) -> _Reading:
    """Plan A's reading of one image, unchanged: no text -> once more in the other mode (not after
    cancel or time limit); warnings empty_retried, empty, time_limit, cancelled, runaway."""
    mode = options.mode
    warnings: list[str] = []
    result = _read(engine, image, mode, options, on_progress, cancel)
    stopped = result.cancelled or result.timed_out
    if not stopped and not _has_text(parse_raw(result.text)):
        warnings.append("empty_retried")
        mode = "fast" if mode == "quality" else "quality"
        result = _read(engine, image, mode, options, on_progress, cancel)
        stopped = result.cancelled or result.timed_out
        if not stopped and not _has_text(parse_raw(result.text)):
            warnings.append("empty")
    if result.timed_out:
        warnings.append("time_limit")
    if result.cancelled:
        warnings.append("cancelled")
    raw = text = result.text
    if is_runaway(text, result.hit_token_cap):
        text = trim_runaway(text)
        warnings.append("runaway")
    return _Reading(parse_raw(text), raw, mode, warnings, result.cancelled, result.timed_out)


def _read_image(engine, image: Path, options: ProcessOptions, scratch: Path,
                on_progress, cancel) -> _Reading:
    return _read_once(engine, image, options, on_progress, cancel)


class _Relay:
    """Gives every probe of guards.best_rotation the page's on_progress and cancel, so Cancel and
    "Stop engine" also stop the probes. EngineError is not caught."""

    def __init__(self, engine, on_progress, cancel) -> None:
        self._engine = engine
        self._on_progress = on_progress
        self._cancel = cancel

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0,
                 on_progress=None, cancel=None):
        return self._engine.ocr_page(image, mode, max_new_tokens=max_new_tokens,
                                     time_limit_s=time_limit_s,
                                     on_progress=on_progress or self._on_progress,
                                     cancel=cancel or self._cancel)


def _language(options: ProcessOptions, blocks: list[Block]) -> str:
    if options.language in ("cs", "en"):
        return options.language
    return spellcheck.detect_language("\n".join(b.text for b in blocks))


def _rate(blocks: list[Block], language: str) -> float:
    return guards.dictionary_hit_rate("\n".join(b.text for b in blocks), language)


def _wrong_orientation(blocks: list[Block], language: str) -> bool:
    """Design 7.3: under 50 % of the words are in the dictionary. Needs a dictionary and at
    least ORIENTATION_MIN_WORDS words to judge."""
    words = sum(len(b.text.split()) for b in blocks)
    return (spellcheck.available(language) and words >= ORIENTATION_MIN_WORDS
            and _rate(blocks, language) < ORIENTATION_MIN_RATE)
```

3c. Replace the function `process_page` with:

```python
def process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> Page:
    t0 = time.perf_counter()
    png = Path(scratch) / f"page_{page.index:04d}.png"
    width, height = render_page(Path(source), page.index, options.dpi, png)
    mode: str | None = None
    rotation = 0                      # degrees clockwise applied to png before reading

    if _use_text_layer(page, options):
        kind, raw, warnings = "text_layer", page.text_layer, []
        blocks = _text_layer_blocks(raw)
        language = _language(options, blocks)
    elif is_blank(png):
        blank = Page(index=page.index, source="blank", mode=None, width_px=width, height_px=height,
                     rotation_applied=0, blocks=[], raw="", warnings=[],
                     seconds=round(time.perf_counter() - t0, 3))
        return cleanup(blank, options)
    else:
        kind, image = "ocr", png
        if guards.looks_sideways(png):             # design 7.2: turn now, 90 vs 270 decided below
            rotation = 90
            image = guards.rotate_image(png, 90, png.with_name(f"{png.stem}_r90.png"))
        reading = _read_image(engine, image, options, Path(scratch), on_progress, cancel)
        language = _language(options, reading.blocks)
        if not reading.stopped and _wrong_orientation(reading.blocks, language):
            turn = guards.best_rotation(image, _Relay(engine, on_progress, cancel), language)
            if turn and not (cancel is not None and cancel.is_set()):
                total = (rotation + turn) % 360
                turned = guards.rotate_image(png, total, png.with_name(f"{png.stem}_r{total}.png"))
                second = _read_image(engine, turned, options, Path(scratch), on_progress, cancel)
                if not second.cancelled and _rate(second.blocks, language) > _rate(reading.blocks,
                                                                                  language):
                    reading, rotation = second, total
                    reading.warnings.append(W_ROTATED)
                    language = _language(options, reading.blocks)
        mode, raw, warnings, blocks = reading.mode, reading.raw, reading.warnings, reading.blocks

    personal = set(options.personal_words)
    blocks = layout.arrange(blocks, language)
    if options.repairs_enabled:
        blocks = [repair.repair_block(b, language, personal) for b in blocks]
    blocks = [spellcheck.flag_suspicious(b, language, personal) for b in blocks]
    if rotation in (90, 270):
        width, height = height, width             # boxes refer to the turned image
    result_page = Page(index=page.index, source=kind, mode=mode, width_px=width, height_px=height,
                       rotation_applied=rotation, blocks=blocks, raw=raw, warnings=warnings,
                       seconds=round(time.perf_counter() - t0, 3))
    return cleanup(result_page, options)
```

Plan A's docstring at the top of `process.py` lists the warnings; add the line `"rotated"             the orientation check turned the page and read it again` to that list.

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_process_orientation.py tests/test_rotation_fake_worker.py -v
py -3.11 -m pytest -q
```

Expected: `9 passed`; the whole suite passes, including all of plan A's `tests/test_process.py` (same warnings, same engine arguments, `EngineError` still reaches the caller).

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/process.py tests/test_process_orientation.py tests/test_rotation_fake_worker.py
git commit -m "Turn sideways pages and fix wrong orientation after OCR" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 14: Read tall images in strips

**Files:**
- Modify: `owlocr/pipeline/process.py` (imports, two new functions and a constant, `_read_image` replaced)
- Test: `tests/test_process_orientation.py` (append)

**Interfaces:**
- Consumes: `pages.cut_strips`, `guards.is_blank`, `_read_once`, `_Reading`.
- Produces: `_read_image` sends images taller than 3.5 × their width (design 7.1) to `_read_strips`; strip boxes are mapped back to 0..999 of the whole image; a block belongs to the strip whose own zone (overlaps split in the middle) holds its centre, so text in an overlap is kept once; blank strips are not read; constant `TALL_RATIO = 3.5`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_process_orientation.py`:

```python
def test_tall_image_is_read_in_strips(no_dicts, tmp_path):
    source = _text_image(tmp_path / "tall.png", size=(400, 2000))
    strips = pages.cut_strips(source, tmp_path / "precut")      # same cut as process_page makes
    lines = [(k * 100 + 20, k * 100 + 50) for k in range(20)]   # image px of 20 text lines

    def answer(image, mode):
        n = int(image.stem.rsplit("strip", 1)[1])
        _path, top, bottom = strips[n - 1]
        out = []
        for k, (y1, y2) in enumerate(lines):
            if top <= y1 and y2 <= bottom:                      # the model sees the whole line
                s1 = round((y1 - top) / (bottom - top) * 999)
                s2 = round((y2 - top) / (bottom - top) * 999)
                out.append(f"<|det|>text [10, {s1}, 990, {s2}]<|/det|>line {k}")
        return "\n".join(out)

    engine = ScriptedEngine(answer)
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert len(engine.calls) == len(strips) == 3
    assert [b.text for b in page.blocks] == [f"line {k}" for k in range(20)]
    for block, (y1, _y2) in zip(page.blocks, lines):
        assert abs(block.box[1] - y1 / 2000 * 999) <= 2
    assert page.warnings == []


def test_blank_strips_are_not_read(no_dicts, tmp_path):
    source = tmp_path / "tall.png"
    img = Image.new("L", (400, 2000), 255)
    ImageDraw.Draw(img).rectangle((40, 60, 360, 90), fill=0)    # text only at the very top
    img.save(source)
    engine = ScriptedEngine(lambda image, mode: "<|det|>text [10, 10, 990, 60]<|/det|>nahoře")
    page = process_page(source, IMAGE_PAGE, engine, ProcessOptions(language="cs"),
                        tmp_path / "scratch")
    assert [c["name"] for c in engine.calls] == ["page_0000_strip1.png"]
    assert [b.text for b in page.blocks] == ["nahoře"]
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_process_orientation.py -v
```

Expected: `2 failed, 8 passed`: `test_tall_image_is_read_in_strips` with `IndexError: list index out of range` (the whole image went to the engine; its name has no strip number) and `test_blank_strips_are_not_read` with `AssertionError`.

- [ ] **Step 3: Write minimal implementation**

3a. Add below plan A's imports in `owlocr/pipeline/process.py`:

```python
from PIL import Image

from owlocr.pipeline import pages
```

3b. Add these definitions directly above `def _read_image(`:

```python
TALL_RATIO = 3.5                 # design 7.1: taller than 3.5 x the width -> strips


def _strip_box_to_page(box, top: int, bottom: int, height: int):
    """A 0..999 box of a strip -> a 0..999 box of the whole image (x does not change)."""
    if box is None:
        return None
    x1, y1, x2, y2 = box
    span = bottom - top

    def to_image(y: int) -> int:
        return round((top + y / 999 * span) / height * 999)

    return (x1, to_image(y1), x2, to_image(y2))


def _read_strips(engine, image: Path, options: ProcessOptions, scratch: Path,
                 on_progress, cancel) -> _Reading:
    """Design 7.1: a tall image is read as overlapping strips and the results are joined. A block
    belongs to the strip whose own zone (every overlap is split in the middle) holds the block's
    centre, so text inside an overlap is kept once. Blank strips are not read."""
    with Image.open(image) as img:
        height = img.height
    strips = pages.cut_strips(image, scratch)
    blocks: list[Block] = []
    raws: list[str] = []
    warnings: list[str] = []
    mode = options.mode
    cancelled = timed_out = False
    for n, (path, top, bottom) in enumerate(strips):
        if guards.is_blank(path):
            continue
        own_top = 0 if n == 0 else (top + strips[n - 1][2]) / 2
        own_bottom = height if n == len(strips) - 1 else (bottom + strips[n + 1][1]) / 2
        part = _read_once(engine, path, options, on_progress, cancel)
        raws.append(part.raw)
        mode = "fast" if part.mode == "fast" else mode
        warnings += [w for w in part.warnings if w not in warnings]
        timed_out = timed_out or part.timed_out
        for block in part.blocks:
            box = _strip_box_to_page(block.box, top, bottom, height)
            centre = (top + bottom) / 2 if box is None else (box[1] + box[3]) / 2 / 999 * height
            if not own_top <= centre < own_bottom:
                continue
            if blocks and block.text.strip() and block.text == blocks[-1].text:
                continue
            blocks.append(Block(block.label, box, block.text, block.raw_text, list(block.flags)))
        if part.cancelled:
            cancelled = True
            break
    if _has_text(blocks):
        warnings = [w for w in warnings if w != "empty"]   # an empty strip is not an empty page
    return _Reading(blocks, "\n".join(raws), mode, warnings, cancelled, timed_out)
```

3c. Replace the function `_read_image` with:

```python
def _read_image(engine, image: Path, options: ProcessOptions, scratch: Path,
                on_progress, cancel) -> _Reading:
    with Image.open(image) as img:
        width, height = img.size
    if height > TALL_RATIO * width:
        return _read_strips(engine, image, options, scratch, on_progress, cancel)
    return _read_once(engine, image, options, on_progress, cancel)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_process_orientation.py -v
py -3.11 -m pytest -q
```

Expected: `10 passed`; the whole suite passes.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/process.py tests/test_process_orientation.py
git commit -m "Read tall screenshots in overlapping strips" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 15: Bundle the DejaVu Sans font for the text layer

**Files:**
- Create: `owlocr/export/fonts/DejaVuSans.ttf`, `owlocr/export/fonts/DejaVuSans-LICENSE.txt`
- Test: `tests/test_font.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the font file used by `searchable_pdf.FONT_FILE`. Licence: Bitstream Vera Fonts licence plus public-domain DejaVu changes (and the Arev notice), which allows redistribution and bundling as long as the licence text travels with the font; plan D lists it in `packaging/THIRD_PARTY_NOTICES.md`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_font.py`:

```python
"""Plan C: the bundled font for the invisible text layer."""
import hashlib
from pathlib import Path

from reportlab.pdfbase.ttfonts import TTFont

FONTS = Path(__file__).parent.parent / "owlocr" / "export" / "fonts"
DEJAVU_SHA256 = "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954"


def test_font_file_is_the_pinned_dejavu_sans():
    data = (FONTS / "DejaVuSans.ttf").read_bytes()
    assert hashlib.sha256(data).hexdigest() == DEJAVU_SHA256


def test_font_licence_travels_with_the_font():
    licence = (FONTS / "DejaVuSans-LICENSE.txt").read_text(encoding="utf-8")
    assert "Bitstream Vera" in licence and "public domain" in licence


def test_font_has_every_czech_letter():
    face = TTFont("OwlTestFont", str(FONTS / "DejaVuSans.ttf")).face
    letters = "ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ„“–"
    assert all(ord(ch) in face.charToGlyph for ch in letters)
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_font.py -v
```

Expected: `3 failed`: `FileNotFoundError` for `owlocr\export\fonts\DejaVuSans.ttf`.

- [ ] **Step 3: Write minimal implementation**

Save this script as `%TEMP%\owl_fetch_font.py` (outside the repository) and run it from the repository root with `py -3.11 %TEMP%\owl_fetch_font.py`. It downloads the official DejaVu 2.37 release, checks the sha256 of the zip and of both files, and writes them into `owlocr\export\fonts\`:

```python
"""One-off: fetch DejaVu Sans 2.37, verify it, copy the font and its licence into the repo.
Run from the repository root: py -3.11 %TEMP%\\owl_fetch_font.py"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ZIP_URL = ("https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
           "version_2_37/dejavu-fonts-ttf-2.37.zip")
ZIP_SHA256 = "7576310b219e04159d35ff61dd4a4ec4cdba4f35c00e002a136f00e96a908b0a"
FILES = {
    "dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf":
        ("DejaVuSans.ttf", "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954"),
    "dejavu-fonts-ttf-2.37/LICENSE":
        ("DejaVuSans-LICENSE.txt", "7a083b136e64d064794c3419751e5c7dd10d2f64c108fe5ba161eae5e5958a93"),
}

target = Path("owlocr") / "export" / "fonts"
if not (Path("owlocr") / "__init__.py").is_file():
    sys.exit("run this from the repository root")
with urllib.request.urlopen(ZIP_URL, timeout=120) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != ZIP_SHA256:
    sys.exit("zip sha256 does not match; stop and report")
target.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    for member, (name, sha256) in FILES.items():
        content = archive.read(member)
        if hashlib.sha256(content).hexdigest() != sha256:
            sys.exit(f"{member}: sha256 does not match; stop and report")
        (target / name).write_bytes(content)
        print(f"wrote {target / name} ({len(content)} bytes)")
```

Expected output: `wrote owlocr\export\fonts\DejaVuSans.ttf (757076 bytes)` and `wrote owlocr\export\fonts\DejaVuSans-LICENSE.txt (8816 bytes)`. Any "does not match" message: stop and report.

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_font.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/fonts/DejaVuSans.ttf owlocr/export/fonts/DejaVuSans-LICENSE.txt tests/test_font.py
git commit -m "Bundle DejaVu Sans with its licence for the searchable PDF text layer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 16: Searchable PDF export

**Files:**
- Create: `owlocr/export/searchable_pdf.py`
- Test: `tests/test_searchable_pdf.py`

**Interfaces:**
- Consumes: `owlocr.paths.unique_path`, `Document`, `Page`, `Block`, `pages.render_page`, `parse.html_table_to_rows`, the font of task 15.
- Produces: `searchable_pdf.export_searchable_pdf(doc: Document, source: Path, out: Path) -> Path` (returns the path actually written, after `unique_path`, which keeps the double suffix: `scan_1.ocr.pdf`); constants `FONT_NAME`, `FONT_FILE`, `IMAGE_DPI_DEFAULT = 200`.

How it works (design 11):
- PDF input: pikepdf opens the original; for every page of the document with `source == 'ocr'` a reportlab overlay page as large as the MediaBox is drawn and stamped over the page as a Form XObject (`q … Q` around the original content, so its graphics state cannot leak). Nothing of the original page changes; pages without OCR (text layer, blank, not processed) get no text. pikepdf's `Page.add_overlay` is not used: on a page with `/Rotate` it turned the layer a second time when this plan was tested.
- Each block's `Block.text` (never `raw_text`: review edits change `text` only) is written invisibly (text render mode 3) into its box. Boxes are 0..999 of the read image; that image was the rendered page (crop box, already shown turned clockwise by `/Rotate`) turned clockwise by `Page.rotation_applied`, so one matrix maps the box back onto the original, unrotated page. Lines are estimated from box size and text length, the font size fills the line pitch, the horizontal scale fills the box width. Tables are written row by row.
- Image input: a new PDF with one page per document page: the page image as `render_page` gives it (unrotated, EXIF applied) at the image's DPI (200 when unknown), and the same invisible text.

- [ ] **Step 1: Write the failing test**

Create `tests/test_searchable_pdf.py`:

```python
"""Plan C: searchable PDF export (design 11). Text is checked by extracting it with pypdfium2."""
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
from PIL import Image
from reportlab.pdfgen import canvas as rl_canvas

from owlocr.export.searchable_pdf import export_searchable_pdf
from owlocr.pipeline.document import Block, Document, Page

PAGES = Path(__file__).parent / "fixtures" / "pages"
SENTENCE = "Účet byl uhrazen pojišťovnou v Žďáru, děkujeme."
TABLE = "<table><tr><td>Jméno</td><td>Obec</td></tr><tr><td>Řehoř</td><td>Třebíč</td></tr></table>"


def _block(label, box, text):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def _page(index=0, rotation=0, source="ocr", blocks=None):
    blocks = blocks if blocks is not None else [
        _block("title", (100, 60, 500, 90), "Lékařská zpráva"),
        _block("text", (100, 100, 900, 200), SENTENCE),
        _block("table", (100, 300, 900, 400), TABLE),
        _block("image", (100, 500, 400, 700), ""),
    ]
    return Page(index=index, source=source, mode="quality", width_px=1654, height_px=2339,
                rotation_applied=rotation, blocks=blocks, raw="", warnings=[], seconds=1.0)


def _doc(source: Path, pages):
    return Document(source_path=str(source), engine_id="unlimited_ocr", engine_revision="x",
                    app_version="0.1.0", created="2026-09-28T10:00:00", pages=pages)


def _scan_pdf(path: Path, image: Path, pages: int = 1, rotate: int = 0) -> Path:
    c = rl_canvas.Canvas(str(path), pagesize=(595.28, 841.89))
    for _ in range(pages):
        c.drawImage(str(image), 0, 0, 595.28, 841.89)
        c.showPage()
    c.save()
    if rotate:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for page in pdf.pages:
                page.Rotate = rotate
            pdf.save(path)
    return path


def _text(pdf_path: Path, index: int = 0) -> str:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return pdf[index].get_textpage().get_text_range()
    finally:
        pdf.close()


def _char_centre(pdf_path: Path, needle: str, index: int = 0) -> tuple[float, float, float, float]:
    """(x, y, width, height) of the first character of `needle` and of the MediaBox, all in PDF
    user space (unrotated; get_size() would give the displayed size of a /Rotate page)."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[index]
        textpage = page.get_textpage()
        at = textpage.get_text_range().index(needle)
        left, bottom, right, top = textpage.get_charbox(at)
        x0, y0, x1, y1 = page.get_mediabox()
        return (left + right) / 2, (bottom + top) / 2, x1 - x0, y1 - y0
    finally:
        pdf.close()


def _render(pdf_path: Path, index: int = 0) -> bytes:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return pdf[index].render(scale=0.5).to_pil().convert("L").tobytes()
    finally:
        pdf.close()


def test_czech_words_are_searchable_in_a_scanned_pdf(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert out == tmp_path / "scan.ocr.pdf"
    text = _text(out)
    for word in ("pojišťovnou", "Žďáru", "Lékařská", "Řehoř", "Třebíč"):
        assert word in text, word


def test_original_page_looks_exactly_the_same(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert _render(out) == _render(source)
    assert len(pdfium.PdfDocument(str(out))) == 1


def test_text_sits_inside_the_block_box(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    assert 0.09 * width < x < 0.2 * width             # box starts at x = 100/999
    assert (1 - 0.2) * height < y < (1 - 0.1) * height  # box spans y = 100..200 of 999, from the top


def test_only_processed_pages_get_text_and_all_pages_stay(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png", pages=3)
    out = export_searchable_pdf(_doc(source, [_page(index=1)]), source, tmp_path / "o.pdf")
    assert len(pdfium.PdfDocument(str(out))) == 3
    assert "pojišťovnou" not in _text(out, 0)
    assert "pojišťovnou" in _text(out, 1)


def test_existing_file_is_not_overwritten(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png")
    (tmp_path / "scan.ocr.pdf").write_bytes(b"keep me")
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "scan.ocr.pdf")
    assert out == tmp_path / "scan_1.ocr.pdf"          # plan A keeps the double suffix
    assert (tmp_path / "scan.ocr.pdf").read_bytes() == b"keep me"


def test_page_with_rotate_attribute(tmp_path):
    source = _scan_pdf(tmp_path / "turned.pdf", PAGES / "01_letter_clean.png", rotate=90)
    block = _block("text", (0, 0, 500, 200), SENTENCE)   # top-left of the page as displayed
    out = export_searchable_pdf(_doc(source, [_page(blocks=[block])]), source, tmp_path / "t.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # displayed = user space turned clockwise: the displayed top-left is the user-space bottom-left
    assert x < 0.2 * width and y < 0.5 * height


def test_image_input_becomes_a_pdf_page_with_text(tmp_path):
    source = tmp_path / "letter.png"
    with Image.open(PAGES / "01_letter_clean.png") as img:
        img.save(source, dpi=(200, 200))
    out = export_searchable_pdf(_doc(source, [_page()]), source, tmp_path / "letter.ocr.pdf")
    pdf = pdfium.PdfDocument(str(out))
    width, height = pdf[0].get_size()
    pdf.close()
    with Image.open(source) as img:
        assert abs(width - img.width * 72 / 200) < 1 and abs(height - img.height * 72 / 200) < 1
    assert "pojišťovnou" in _text(out)


def test_image_read_after_rotation_puts_text_in_the_original_orientation(tmp_path):
    source = tmp_path / "sideways.png"
    with Image.open(PAGES / "09_letter_rotated_90.png") as img:
        img.save(source, dpi=(200, 200))
    block = _block("text", (0, 0, 500, 200), SENTENCE)   # top-left of the upright reading
    page = _page(rotation=90, blocks=[block])
    out = export_searchable_pdf(_doc(source, [page]), source, tmp_path / "s.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # the fixture is a letter turned 90° counter-clockwise, so it was read after a 90° clockwise
    # turn (rotation_applied = 90); the letter's top-left is the original's bottom-left corner,
    # which in PDF coordinates (y up) is the left edge, lower half
    assert x < 0.25 * width and y < 0.55 * height
    assert "pojišťovnou" in _text(out)


def test_text_layer_and_blank_pages_get_no_extra_text(tmp_path):
    source = _scan_pdf(tmp_path / "scan.pdf", PAGES / "01_letter_clean.png", pages=2)
    pages = [_page(index=0, source="text_layer"), _page(index=1, source="blank", blocks=[])]
    out = export_searchable_pdf(_doc(source, pages), source, tmp_path / "o.pdf")
    assert _text(out, 0).strip() == "" and _text(out, 1).strip() == ""


def test_rotate_attribute_and_turned_reading_combine(tmp_path):
    source = _scan_pdf(tmp_path / "turned.pdf", PAGES / "01_letter_clean.png", rotate=90)
    block = _block("text", (0, 0, 500, 200), SENTENCE)
    page = _page(rotation=90, blocks=[block])        # displayed page, then turned 90° clockwise
    out = export_searchable_pdf(_doc(source, [page]), source, tmp_path / "t.pdf")
    x, y, width, height = _char_centre(out, "Účet")
    # 90° (/Rotate) + 90° (reading) = the user space turned 180°: upright top-left is the
    # user-space bottom-right corner
    assert x > 0.8 * width and y < 0.5 * height
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_searchable_pdf.py -v
```

Expected: collection error `ModuleNotFoundError: No module named 'owlocr.export.searchable_pdf'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/export/searchable_pdf.py`:

```python
"""Searchable PDF (design 11): the original page stays untouched and every block's text is added
as invisible text (render mode 3) inside the block's box.

Uses pikepdf (MPL-2.0) and reportlab (BSD). Never PyMuPDF (AGPL). The embedded font is
DejaVu Sans (Bitstream Vera licence + public-domain changes, redistribution allowed), so Czech
letters are searchable and copyable.
"""
from __future__ import annotations

import io
import math
import re
import tempfile
from pathlib import Path

import pikepdf
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from owlocr.paths import unique_path
from owlocr.pipeline.document import Block, Document, Page
from owlocr.pipeline.pages import render_page
from owlocr.pipeline.parse import html_table_to_rows

FONT_NAME = "OwlDejaVuSans"
FONT_FILE = Path(__file__).with_name("fonts") / "DejaVuSans.ttf"
IMAGE_DPI_DEFAULT = 200
_CHAR_WIDTH_EM = 0.5          # average glyph width as a share of the font size
_LINE_PITCH_EM = 1.2          # line height as a share of the font size
_TAG = re.compile(r"<[^>]*>")
_SKIP_LABELS = ("image", "figure")


def _register_font() -> None:
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_FILE)))


def _block_lines(block: Block) -> list[str]:
    """The block's text as lines: tables row by row, everything else as written."""
    if block.label == "table":
        rows = html_table_to_rows(block.text)
        if rows is not None:
            return [" ".join(cell for cell in row if cell) for row in rows if any(row)]
        text = _TAG.sub(" ", re.sub(r"</tr>", "\n", block.text, flags=re.I))
    else:
        text = block.text
    return [" ".join(line.split()) for line in text.split("\n") if line.strip()]


def _wrap(line: str, count: int) -> list[str]:
    """Split one line into `count` lines of similar length at spaces."""
    words = line.split()
    if count <= 1 or len(words) <= 1:
        return [line]
    target = len(line) / count
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > target and len(lines) < count - 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def _fit_lines(lines: list[str], width: float, height: float) -> tuple[list[str], float]:
    """Estimate the text lines inside a box and the font size (design 11: one line per estimated
    text line, font size fitted to the box)."""
    if len(lines) == 1:
        chars = max(len(lines[0]), 1)
        size = math.sqrt(width * height / (chars * _CHAR_WIDTH_EM * _LINE_PITCH_EM))
        count = max(1, min(round(height / (size * _LINE_PITCH_EM)), len(lines[0].split())))
        lines = _wrap(lines[0], count)
    size = height / (len(lines) * _LINE_PITCH_EM)
    return lines, max(1.0, min(size, 400.0))


def _frame_matrix(rotation: int, width: float, height: float) -> tuple[float, ...]:
    """Matrix from the upright frame (the image the model read, in points, y up) back to the
    unrotated page frame of `width` x `height` points, when the read image was the page turned
    `rotation` degrees CLOCKWISE (the convention of Page.rotation_applied)."""
    rotation %= 360
    if rotation == 90:
        return (0, 1, -1, 0, width, 0)
    if rotation == 180:
        return (-1, 0, 0, -1, width, height)
    if rotation == 270:
        return (0, -1, 1, 0, 0, height)
    return (1, 0, 0, 1, 0, 0)


def _draw_page_text(c, page: Page, rotation: int, width: float, height: float,
                    offset: tuple[float, float] = (0.0, 0.0)) -> None:
    """Draw every block of `page` as invisible text onto canvas `c` whose page is width x height
    points; the read image was that page turned `rotation` degrees clockwise."""
    upright_w, upright_h = (height, width) if rotation % 180 == 90 else (width, height)
    c.saveState()
    c.translate(*offset)
    c.transform(*_frame_matrix(rotation, width, height))
    for block in page.blocks:
        if block.box is None or block.label in _SKIP_LABELS:
            continue
        lines = _block_lines(block)
        if not lines:
            continue
        x1, y1, x2, y2 = block.box
        left = x1 / 999 * upright_w
        right = x2 / 999 * upright_w
        top = upright_h - y1 / 999 * upright_h
        bottom = upright_h - y2 / 999 * upright_h
        box_w, box_h = max(right - left, 1.0), max(top - bottom, 1.0)
        lines, size = _fit_lines(lines, box_w, box_h)
        pitch = box_h / len(lines)
        for n, line in enumerate(lines):
            natural = pdfmetrics.stringWidth(line, FONT_NAME, size)
            text = c.beginText()
            text.setTextRenderMode(3)
            text.setFont(FONT_NAME, size)
            if natural > 0:
                text.setHorizScale(max(1.0, min(1000.0, 100.0 * box_w / natural)))
            text.setTextOrigin(left, top - (n + 1) * pitch + 0.2 * pitch)
            text.textOut(line)
            c.drawText(text)
    c.restoreState()


def _overlay_for_pdf(doc: Document, pdf: pikepdf.Pdf) -> tuple[bytes, list[int]]:
    """One overlay page per OCR page, each as large as the target page's MediaBox."""
    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pageCompression=1)
    targets = []
    for page in doc.pages:
        if page.source != "ocr" or not page.blocks or page.index >= len(pdf.pages):
            continue
        target = pdf.pages[page.index]
        mx0, my0, mx1, my1 = (float(v) for v in target.mediabox)
        cx0, cy0, cx1, cy1 = (float(v) for v in target.cropbox)
        c.setPageSize((mx1 - mx0, my1 - my0))
        page_rotate = int(target.obj.get("/Rotate", 0)) % 360
        # the rendered page image shows the crop box turned clockwise by /Rotate, and the model
        # read that image turned clockwise by rotation_applied
        rotation = (page.rotation_applied + page_rotate) % 360
        _draw_page_text(c, page, rotation, cx1 - cx0, cy1 - cy0, (cx0 - mx0, cy0 - my0))
        c.showPage()
        targets.append(page.index)
    c.save()
    return buffer.getvalue(), targets


def _stamp(target: pikepdf.Page, form: pikepdf.Object) -> None:
    """Draw `form` over the page at the MediaBox origin, scale 1. pikepdf's Page.add_overlay is
    not used: on a page with /Rotate it turned the layer a second time (seen while testing), and
    _overlay_for_pdf has already taken /Rotate into account."""
    name = target.add_resource(form, pikepdf.Name.XObject)
    x0, y0 = float(target.mediabox[0]), float(target.mediabox[1])
    target.contents_add(b"q\n", prepend=True)
    target.contents_add(b"\nQ\nq 1 0 0 1 %.4f %.4f cm %s Do Q\n" % (x0, y0, name.unparse()),
                        prepend=False)
    target.contents_coalesce()


def _export_pdf_source(doc: Document, source: Path, out: Path) -> Path:
    with pikepdf.open(source) as pdf:
        overlay_bytes, targets = _overlay_for_pdf(doc, pdf)
        if targets:
            with pikepdf.open(io.BytesIO(overlay_bytes)) as overlay:
                for n, index in enumerate(targets):
                    _stamp(pdf.pages[index], pdf.copy_foreign(overlay.pages[n].as_form_xobject()))
        pdf.save(out)
    return out


def _image_dpi(image: Image.Image) -> float:
    dpi = image.info.get("dpi")
    try:
        value = float(dpi[0]) if dpi else 0.0
    except (TypeError, ValueError, IndexError):
        value = 0.0
    return value if value >= 50 else IMAGE_DPI_DEFAULT


def _export_image_source(doc: Document, source: Path, out: Path) -> Path:
    with Image.open(source) as original:
        dpi = _image_dpi(original)
    c = rl_canvas.Canvas(str(out), pageCompression=1)
    with tempfile.TemporaryDirectory() as tmp:
        for page in doc.pages:
            png = Path(tmp) / f"page_{page.index:04d}.png"
            pixels_w, pixels_h = render_page(source, page.index, IMAGE_DPI_DEFAULT, png)
            width, height = pixels_w * 72 / dpi, pixels_h * 72 / dpi
            c.setPageSize((width, height))
            c.drawImage(str(png), 0, 0, width, height)
            if page.source == "ocr":
                _draw_page_text(c, page, page.rotation_applied, width, height)
            c.showPage()
        c.save()
    return out


def export_searchable_pdf(doc: Document, source: Path, out: Path) -> Path:
    _register_font()
    out = unique_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        return _export_pdf_source(doc, source, out)
    return _export_image_source(doc, source, out)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_searchable_pdf.py -v
```

Expected: `10 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/searchable_pdf.py tests/test_searchable_pdf.py
git commit -m "Export searchable PDF with an invisible Czech text layer over the untouched page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 17: Word export

**Files:**
- Create: `owlocr/export/docx.py`
- Test: `tests/test_docx_export.py`

**Interfaces:**
- Consumes: `unique_path`, `FURNITURE_LABELS`, `Document`, `Page`, `Block`, `guards.rotate_image`, `pages.render_page`, `parse.html_table_to_rows`.
- Produces: `docx.export_docx(doc: Document, out: Path, page_breaks: bool = False, keep_furniture: bool = False) -> Path`.

Rules (design 11): `title` → Heading 1 when its box is at least 1.6 times the page's typical text line (the same rule as plan A's Markdown `#`), otherwise Heading 2; `text` → paragraph (line breaks kept); `list` → "List Bullet" / "List Number" items with the bullet stripped; `table` → a real Word table ("Table Grid"), and when the HTML has `rowspan`/`colspan` the spans are ignored and the cells kept in reading order; `image`/`figure` → cut from the page image and placed inline: like plan A's Markdown export there is no source parameter, so the page is re-rendered from `Document.source_path` (150 dpi) and turned clockwise by `rotation_applied` so the box fits; when the source is gone, pictures are left out; captions in italics; `formula` → paragraph with its text; page furniture only with `keep_furniture`; optional page break between pages. Always `Block.text`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_docx_export.py`:

```python
"""Plan C: Word export (design 11)."""
from pathlib import Path

from docx import Document as WordDocument
from PIL import Image, ImageDraw

from owlocr.export.docx import export_docx
from owlocr.pipeline.document import Block, Document, Page

TABLE = ("<table><tr><td>Jméno</td><td>Obec</td></tr>"
         "<tr><td>Řehoř Dvořák</td><td>Třebíč</td></tr></table>")
SPAN_TABLE = ("<table><tr><td colspan=\"2\">Přehled</td></tr>"
              "<tr><td>Dub</td><td>Buk</td></tr></table>")
BODY = ("Rostlina je buď velký strom, nebo malý stonek. Listy rostou na stonku a jsou "
        "střídavé nebo vstřícné, podle druhu.")


def _b(label, text, box=(100, 100, 900, 200)):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def _page(index, blocks, width=1000, height=1400, rotation=0):
    return Page(index=index, source="ocr", mode="quality", width_px=width, height_px=height,
                rotation_applied=rotation, blocks=blocks, raw="", warnings=[], seconds=1.0)


def _doc(source: Path, pages):
    return Document(source_path=str(source), engine_id="unlimited_ocr", engine_revision="x",
                    app_version="0.1.0", created="2026-09-28T10:00:00", pages=pages)


def _source_image(path: Path) -> Path:
    img = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(img).rectangle((200, 700, 600, 1000), fill=(200, 30, 30))   # the "figure"
    img.save(path)
    return path


def _blocks():
    return [
        _b("header", "Učebnice botaniky", (100, 10, 900, 30)),
        _b("title", "Stavba listu", (100, 30, 600, 90)),
        _b("title", "Postavení listů", (100, 100, 500, 120)),
        _b("text", BODY, (100, 130, 900, 160)),
        _b("list", "- první bod\n- druhý bod\n1. očíslovaný bod", (100, 210, 900, 280)),
        _b("table", TABLE, (100, 290, 900, 400)),
        _b("image", "", (200, 500, 600, 714)),
        _b("image_caption", "Obr. 3 Řez listem", (200, 720, 600, 740)),
        _b("formula", "E = mc^2", (100, 750, 400, 780)),
        _b("page_number", "12", (480, 960, 520, 980)),
    ]


def _paragraphs(path):
    return [(p.style.name, p.text) for p in WordDocument(str(path)).paragraphs if p.text]


def test_structure_of_the_word_file(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    out = export_docx(_doc(source, [_page(0, _blocks())]), tmp_path / "scan.docx")
    assert out == tmp_path / "scan.docx"
    paragraphs = _paragraphs(out)
    assert paragraphs[0] == ("Heading 1", "Stavba listu")
    assert paragraphs[1] == ("Heading 2", "Postavení listů")
    assert paragraphs[2] == ("Normal", BODY)
    assert paragraphs[3:6] == [("List Bullet", "první bod"), ("List Bullet", "druhý bod"),
                               ("List Number", "očíslovaný bod")]
    assert ("Normal", "E = mc^2") in paragraphs
    caption = [p for p in WordDocument(str(out)).paragraphs if p.text == "Obr. 3 Řez listem"][0]
    assert all(run.italic for run in caption.runs)


def test_table_is_a_real_table(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    out = export_docx(_doc(source, [_page(0, _blocks())]), tmp_path / "scan.docx")
    table = WordDocument(str(out)).tables[0]
    assert [[c.text for c in row.cells] for row in table.rows] == [
        ["Jméno", "Obec"], ["Řehoř Dvořák", "Třebíč"]]


def test_table_with_spans_still_becomes_a_table(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    doc = _doc(source, [_page(0, [_b("table", SPAN_TABLE)])])
    table = WordDocument(str(export_docx(doc, tmp_path / "s.docx"))).tables[0]
    assert table.cell(1, 0).text == "Dub" and table.cell(1, 1).text == "Buk"
    assert table.cell(0, 0).text == "Přehled"


def test_image_is_cut_from_the_page_and_inlined(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    out = export_docx(_doc(source, [_page(0, _blocks())]), tmp_path / "scan.docx")
    word = WordDocument(str(out))
    assert len(word.inline_shapes) == 1
    blob = word.inline_shapes[0]._inline.graphic.graphicData.pic.blipFill.blip.embed
    image_part = word.part.related_parts[blob]
    from io import BytesIO
    with Image.open(BytesIO(image_part.blob)) as picture:
        assert picture.getpixel((picture.width // 2, picture.height // 2)) == (200, 30, 30)


def test_missing_source_skips_images_but_keeps_text(tmp_path):
    out = export_docx(_doc(tmp_path / "gone.png", [_page(0, _blocks())]), tmp_path / "x.docx")
    word = WordDocument(str(out))
    assert len(word.inline_shapes) == 0
    assert any(p.text == BODY for p in word.paragraphs)


def test_furniture_left_out_unless_asked(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    doc = _doc(source, [_page(0, _blocks())])
    without = [t for _s, t in _paragraphs(export_docx(doc, tmp_path / "a.docx"))]
    assert "Učebnice botaniky" not in without and "12" not in without
    kept = [t for _s, t in _paragraphs(export_docx(doc, tmp_path / "b.docx", keep_furniture=True))]
    assert "Učebnice botaniky" in kept and "12" in kept


def test_optional_page_breaks(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    pages = [_page(0, [_b("text", "První strana.")]), _page(1, [_b("text", "Druhá strana.")])]

    def breaks(path):
        return WordDocument(str(path)).element.body.xml.count('w:type="page"')

    assert breaks(export_docx(_doc(source, pages), tmp_path / "a.docx")) == 0
    assert breaks(export_docx(_doc(source, pages), tmp_path / "b.docx", page_breaks=True)) == 1


def test_existing_file_is_not_overwritten(tmp_path):
    source = _source_image(tmp_path / "scan.png")
    (tmp_path / "scan.docx").write_bytes(b"keep")
    out = export_docx(_doc(source, [_page(0, _blocks())]), tmp_path / "scan.docx")
    assert out == tmp_path / "scan_1.docx"


def test_image_is_cut_from_the_turned_page(tmp_path):
    upright = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(upright).rectangle((200, 700, 600, 1000), fill=(200, 30, 30))
    source = tmp_path / "sideways.png"
    upright.rotate(90, expand=True).save(source)       # scanned sideways (counter-clockwise)
    page = _page(0, [_b("image", "", (200, 500, 600, 714))], rotation=90)   # read after 90° cw
    word = WordDocument(str(export_docx(_doc(source, [page]), tmp_path / "t.docx")))
    blob = word.inline_shapes[0]._inline.graphic.graphicData.pic.blipFill.blip.embed
    from io import BytesIO
    with Image.open(BytesIO(word.part.related_parts[blob].blob)) as picture:
        assert picture.getpixel((picture.width // 2, picture.height // 2)) == (200, 30, 30)
        assert picture.width > picture.height                 # upright crop, not sideways
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_docx_export.py -v
```

Expected: collection error `ModuleNotFoundError: No module named 'owlocr.export.docx'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/export/docx.py` (inside the package, `from docx import ...` still imports python-docx, because imports are absolute):

```python
"""Word export (design 11): headings, paragraphs, lists, real tables, images cut from the page
image, captions in italics, optional page breaks. python-docx (MIT)."""
from __future__ import annotations

import io
import re
import statistics
import tempfile
from pathlib import Path

from docx import Document as WordDocument
from docx.enum.text import WD_BREAK
from docx.shared import Inches
from PIL import Image

from owlocr.paths import unique_path
from owlocr.pipeline.document import FURNITURE_LABELS, Block, Document, Page
from owlocr.pipeline.guards import rotate_image
from owlocr.pipeline.pages import render_page
from owlocr.pipeline.parse import html_table_to_rows

IMAGE_DPI = 150
TEXT_WIDTH_IN = 6.0            # usable width of the default Word page
HEADING_1_RATIO = 1.6          # same rule as the Markdown export of plan A
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦]|(\d+|[a-z])[.)])\s+")
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>")
_CAPTIONS = ("image_caption", "table_caption")
_PICTURES = ("image", "figure")


def _line_height(page: Page) -> float | None:
    """Typical height of one text line (0..999 units), the rule of plan A's Markdown export:
    the median of the smaller half of the text blocks' box heights."""
    heights = sorted(b.box[3] - b.box[1] for b in page.blocks if b.label == "text" and b.box)
    if not heights:
        return None
    return statistics.median(heights[: max(1, len(heights) // 2)])


def _heading_level(block: Block, line: float | None) -> int:
    """1 when the title's box is at least 1.6 times a text line (as '#' in Markdown), else 2."""
    if block.box and line and (block.box[3] - block.box[1]) >= HEADING_1_RATIO * line:
        return 1
    return 2


def _table_rows(html: str) -> list[list[str]]:
    rows = html_table_to_rows(html)
    if rows is not None:
        return rows
    # rowspan/colspan present: keep the cells in reading order and ignore the spans
    return [[" ".join(_TAG.sub(" ", cell).split()) for cell in _CELL.findall(row)]
            for row in _ROW.findall(html)]


def _add_text(paragraph, text: str, italic: bool = False) -> None:
    for n, line in enumerate(text.split("\n")):
        run = paragraph.add_run(line)
        run.italic = italic or None
        if n < text.count("\n"):
            run.add_break(WD_BREAK.LINE)


def _add_table(word, block: Block) -> None:
    rows = [r for r in _table_rows(block.text) if r]
    if not rows:
        return
    columns = max(len(r) for r in rows)
    table = word.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            table.cell(r, c).text = cell


def _add_list(word, block: Block) -> None:
    for line in block.text.split("\n"):
        if not line.strip():
            continue
        match = _BULLET.match(line)
        style = "List Number" if match and match.group(1) else "List Bullet"
        word.add_paragraph(line[match.end():] if match else line.strip(), style=style)


class _PageImages:
    """Renders each page image once (upright, as the model read it) for cutting out pictures."""

    def __init__(self, source: Path, folder: Path):
        self.source = source
        self.folder = folder
        self.cache: dict[int, Image.Image | None] = {}

    def get(self, page: Page) -> Image.Image | None:
        if page.index not in self.cache:
            self.cache[page.index] = self._render(page)
        return self.cache[page.index]

    def _render(self, page: Page) -> Image.Image | None:
        if not self.source.is_file():
            return None
        png = self.folder / f"page_{page.index:04d}.png"
        try:
            render_page(self.source, page.index, IMAGE_DPI, png)
            if page.rotation_applied:
                png = rotate_image(png, page.rotation_applied, png.with_name(png.stem + "_up.png"))
            with Image.open(png) as img:
                img.load()
                return img.copy()
        except Exception:
            return None


def _add_picture(word, block: Block, page: Page, images: _PageImages) -> None:
    image = images.get(page)
    if image is None or block.box is None:
        return
    x1, y1, x2, y2 = block.box
    crop = image.crop((round(x1 / 999 * image.width), round(y1 / 999 * image.height),
                       round(x2 / 999 * image.width), round(y2 / 999 * image.height)))
    if crop.width < 2 or crop.height < 2:
        return
    stream = io.BytesIO()
    crop.convert("RGB").save(stream, format="PNG")
    stream.seek(0)
    width = max(0.5, min(TEXT_WIDTH_IN, (x2 - x1) / 999 * TEXT_WIDTH_IN))
    word.add_picture(stream, width=Inches(width))


def export_docx(doc: Document, out: Path, page_breaks: bool = False,
                keep_furniture: bool = False) -> Path:
    out = unique_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    word = WordDocument()
    with tempfile.TemporaryDirectory() as tmp:
        images = _PageImages(Path(doc.source_path), Path(tmp))
        for n, page in enumerate(doc.pages):
            if n and page_breaks:
                word.add_page_break()
            line = _line_height(page)
            for block in page.blocks:
                if block.label in FURNITURE_LABELS and not keep_furniture:
                    continue
                if block.label in _PICTURES:
                    _add_picture(word, block, page, images)
                elif not block.text.strip():
                    continue
                elif block.label == "title":
                    level = _heading_level(block, line)
                    word.add_heading(block.text.replace("\n", " "), level=level)
                elif block.label == "table":
                    _add_table(word, block)
                elif block.label == "list":
                    _add_list(word, block)
                elif block.label in _CAPTIONS:
                    _add_text(word.add_paragraph(), block.text, italic=True)
                else:
                    _add_text(word.add_paragraph(), block.text)
        word.save(str(out))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_docx_export.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/docx.py tests/test_docx_export.py
git commit -m "Export Word documents with headings, real tables and cut-out images" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 18: Markdown: crops of turned pages, foreign letters in the appendix

**Files:**
- Modify: `owlocr/export/markdown.py` (class `_ImageCutter` and function `_appendix` replaced)
- Test: `tests/test_markdown_plan_c.py`

**Interfaces:**
- Consumes: plan A's `markdown.py` (`_CROP_DPI`, `render_page`, `tempfile`, `Image`, `Document`, `Page`, `Block` are already imported or defined there).
- Produces: `export_markdown` (contract signature unchanged) now cuts pictures from the page turned clockwise by `rotation_applied`, and its optional appendix (plan A's format: the heading `**Suspicious words / Podezřelá slova**`, then one line per flag with the page number and the word) also lists `'foreign_letter'` flags. Words are never marked inside the text (design 9.1 point 4).

- [ ] **Step 1: Write the failing test**

Create `tests/test_markdown_plan_c.py`:

```python
"""Plan C additions to the Markdown export: foreign letters in the appendix, crops of turned pages."""
from PIL import Image, ImageDraw

from owlocr.export.markdown import export_markdown
from owlocr.pipeline.document import Block, Document, Flag, Page

TEXT = "Rostlina je bylinny strom a także list."


def _doc(source, blocks, rotation=0, size=(1000, 1400)):
    page = Page(index=0, source="ocr", mode="quality", width_px=size[0], height_px=size[1],
                rotation_applied=rotation, blocks=blocks, raw="", warnings=[], seconds=1.0)
    return Document(str(source), "unlimited_ocr", "x", "0.1.0", "2026-09-28T10:00:00", [page])


def test_appendix_lists_foreign_letters_too(tmp_path):
    flags = [Flag("suspicious", 12, 19, "bylinny", "not in the dictionary"),
             Flag("foreign_letter", 28, 33, "także", "letter does not exist in Czech")]
    doc = _doc(tmp_path / "gone.png", [Block("text", (100, 100, 900, 200), TEXT, TEXT, flags)])
    text = export_markdown(doc, tmp_path / "a.md", suspicious_appendix=True).read_text(
        encoding="utf-8")
    assert text.endswith("**Suspicious words / Podezřelá slova**\n\n"
                         "- page 1: `bylinny`\n- page 1: `także`\n")
    assert text.startswith(TEXT)                       # words are not marked inside the text


def test_image_is_cut_from_the_turned_page(tmp_path):
    upright = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(upright).rectangle((200, 700, 600, 1000), fill=(200, 30, 30))
    source = tmp_path / "sideways.png"
    upright.rotate(90, expand=True).save(source)        # scanned sideways (counter-clockwise)
    doc = _doc(source, [Block("image", (200, 500, 600, 714), "", "", [])], rotation=90)
    out = export_markdown(doc, tmp_path / "out" / "sideways.md")
    with Image.open(tmp_path / "out" / "sideways_images" / "page001_img1.png") as crop:
        assert crop.width > crop.height                           # upright, not sideways
        assert crop.getpixel((crop.width // 2, crop.height // 2)) == (200, 30, 30)
    assert out.read_text(encoding="utf-8") == "![](sideways_images/page001_img1.png)\n"
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_markdown_plan_c.py -v
```

Expected: `2 failed`: the appendix lacks `także`, and the crop is cut from the unturned page (`AssertionError` on the crop's colour).

- [ ] **Step 3: Write minimal implementation**

3a. In `owlocr/export/markdown.py` replace the class `_ImageCutter` with:

```python
class _ImageCutter:
    """Cuts image blocks out of the source pages into <out stem>_images/. The page is rendered
    again and turned clockwise by Page.rotation_applied, so the boxes (which refer to the image
    the model read) fit."""

    def __init__(self, doc: Document, out: Path) -> None:
        self.source = Path(doc.source_path)
        self.folder = out.with_name(out.stem + "_images")
        self.count = 0
        self._rendered: dict[int, Image.Image | None] = {}

    def link(self, page: Page, block: Block) -> str | None:
        if block.box is None or not self.source.is_file():
            return None
        image = self._page_image(page)
        if image is None:
            return None
        x1, y1, x2, y2 = block.box
        w, h = image.size
        box = (x1 * w // 999, y1 * h // 999, max(x2 * w // 999, x1 * w // 999 + 1),
               max(y2 * h // 999, y1 * h // 999 + 1))
        self.count += 1
        self.folder.mkdir(parents=True, exist_ok=True)
        name = f"page{page.index + 1:03d}_img{self.count}.png"
        image.crop(box).save(self.folder / name, "PNG")
        return f"![]({self.folder.name}/{name})"

    def _page_image(self, page: Page) -> Image.Image | None:
        if page.index not in self._rendered:
            with tempfile.TemporaryDirectory() as tmp:
                png = Path(tmp) / "page.png"
                try:
                    render_page(self.source, page.index, _CROP_DPI, png)
                except (OSError, ValueError, IndexError, EOFError):
                    self._rendered[page.index] = None
                    return None
                with Image.open(png) as im:
                    # rotate() returns a new image, also for 0 degrees
                    self._rendered[page.index] = im.rotate(-page.rotation_applied, expand=True)
        return self._rendered[page.index]
```

3b. Replace the function `_appendix` with:

```python
_LISTED_FLAGS = ("suspicious", "foreign_letter")


def _appendix(doc: Document) -> str | None:
    """Design 9.1 point 4: the flagged words, page by page. Words with a letter that does not
    exist in Czech (plan C's 'foreign_letter' flags) are listed like the suspicious ones."""
    lines = []
    for page in doc.pages:
        for block in page.blocks:
            for flag in block.flags:
                if flag.kind in _LISTED_FLAGS:
                    lines.append(f"- page {page.index + 1}: `{flag.original}`")
    if not lines:
        return None
    return "---\n\n**Suspicious words / Podezřelá slova**\n\n" + "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_markdown_plan_c.py -v
py -3.11 -m pytest -q
```

Expected: `2 passed`; the whole suite passes (plan A's `tests/test_export_markdown.py` is unchanged and still passes).

- [ ] **Step 5: Commit**

```
git add owlocr/export/markdown.py tests/test_markdown_plan_c.py
git commit -m "Cut Markdown images from turned pages and list foreign letters" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 19: export_all with all four formats, and the final check

**Files:**
- Modify: `owlocr/export/__init__.py` (imports, `FORMATS_AVAILABLE`, `export_all` replaced), `tests/test_export_all.py` and `tests/test_cli.py` (one plan A test each replaced)
- Test: `tests/test_export_all_formats.py`

**Interfaces:**
- Consumes: `export_markdown`, `export_text`, `export_docx`, `export_searchable_pdf`; settings keys `keep_page_furniture` and `append_suspicious_list` (design 10.3).
- Produces: `export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]` for `md`, `txt`, `docx`, `pdf` (file names of design 10.6: `<source stem>.md`, `.txt`, `.docx`, `.ocr.pdf`; `ValueError` for an unknown format before anything is written; never writes the `.owl.json` sidecar, the CLI and plan B's runner do); constant `FORMATS_AVAILABLE = ("md", "txt", "docx", "pdf")`, which plan B's `owlocr/jobs/formats.py` reads to enable the Word and PDF checkboxes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_export_all_formats.py`:

```python
"""Plan C: export_all with all four formats (design 11, file names of design 10.6)."""
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from docx import Document as WordDocument
from PIL import Image

from owlocr import export
from owlocr.export import FORMATS, export_all
from owlocr.pipeline.document import Block, Document, Flag, Page
from tests.conftest import PAGES

TEXT = "Rostlina je bylinny strom a także list."


def _doc(source: Path) -> Document:
    flags = [Flag("suspicious", 12, 19, "bylinny", "not in the dictionary"),
             Flag("foreign_letter", 28, 33, "także", "letter does not exist in Czech")]
    blocks = [Block("text", (100, 100, 900, 200), TEXT, TEXT, flags),
              Block("footer", (100, 950, 900, 980), "Zápatí stránky", "Zápatí stránky", [])]
    page = Page(0, "ocr", "quality", 2480, 3508, 0, blocks, "", [], 1.0)
    return Document(str(source), "unlimited_ocr", "x", "0.1.0", "2026-09-28T10:00:00", [page])


def _png(tmp_path: Path) -> Path:
    source = tmp_path / "dopis.png"
    with Image.open(PAGES / "01_letter_clean.png") as img:
        img.save(source, dpi=(200, 200))
    return source


def test_all_four_formats_are_available():
    assert export.FORMATS_AVAILABLE == ("md", "txt", "docx", "pdf") == FORMATS


def test_export_all_writes_all_four_formats_and_no_sidecar(tmp_path):
    source = _png(tmp_path)
    outputs = export_all(_doc(source), source, list(FORMATS), tmp_path / "out", {})
    assert outputs == {"md": tmp_path / "out" / "dopis.md", "txt": tmp_path / "out" / "dopis.txt",
                       "docx": tmp_path / "out" / "dopis.docx",
                       "pdf": tmp_path / "out" / "dopis.ocr.pdf"}
    assert all(p.is_file() for p in outputs.values())
    assert any(p.text == TEXT for p in WordDocument(str(outputs["docx"])).paragraphs)
    pdf = pdfium.PdfDocument(str(outputs["pdf"]))
    assert "Rostlina" in pdf[0].get_textpage().get_text_range()
    pdf.close()
    assert not list((tmp_path / "out").glob("*.owl.json"))      # the runner writes the sidecar


def test_export_all_honours_the_settings(tmp_path):
    source = _png(tmp_path)
    settings = {"keep_page_furniture": True, "append_suspicious_list": True}
    outputs = export_all(_doc(source), source, ["md", "docx"], tmp_path / "out", settings)
    markdown = outputs["md"].read_text(encoding="utf-8")
    assert "Zápatí stránky" in markdown and "- page 1: `także`" in markdown
    assert any(p.text == "Zápatí stránky" for p in WordDocument(str(outputs["docx"])).paragraphs)
    plain = export_all(_doc(source), source, ["docx"], tmp_path / "plain", {})
    assert not any(p.text == "Zápatí stránky"
                   for p in WordDocument(str(plain["docx"])).paragraphs)


def test_exports_use_the_edited_text_not_the_raw_reading(tmp_path):
    source = _png(tmp_path)
    doc = _doc(source)
    doc.pages[0].blocks = [Block("text", (100, 100, 900, 200), "Opravený řádek textu.",
                                 "Puvodni cteni radku.", [])]
    outputs = export_all(doc, source, list(FORMATS), tmp_path / "out", {})
    pdf = pdfium.PdfDocument(str(outputs["pdf"]))
    texts = {
        "md": outputs["md"].read_text(encoding="utf-8"),
        "txt": outputs["txt"].read_text(encoding="utf-8"),
        "docx": "\n".join(p.text for p in WordDocument(str(outputs["docx"])).paragraphs),
        "pdf": pdf[0].get_textpage().get_text_range(),
    }
    pdf.close()
    for fmt, text in texts.items():
        assert "Opravený" in text and "Puvodni" not in text, fmt


def test_unknown_format_is_rejected_before_writing(tmp_path):
    source = _png(tmp_path)
    with pytest.raises(ValueError):
        export_all(_doc(source), source, ["md", "odt"], tmp_path / "out", {})
    assert not (tmp_path / "out" / "dopis.md").exists()
```

Two plan A tests expected Word and PDF to fail; they are replaced now. In `tests/test_export_all.py` replace the function `test_export_all_rejects_later_and_unknown_formats` with:

```python
def test_export_all_rejects_unknown_formats(tmp_path):
    doc = sample_document()
    with pytest.raises(ValueError):
        export.export_all(doc, tmp_path / "k.pdf", ["md", "html"], tmp_path / "out", {})
    assert not (tmp_path / "out" / "k.md").exists()
```

In `tests/test_cli.py` replace the function `test_later_formats_fail_the_input` with:

```python
def test_word_and_searchable_pdf_are_written(letter):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "md,docx,pdf"]) == 0
    for name in ("dopis.md", "dopis.docx", "dopis.ocr.pdf"):
        assert (letter.parent / name).is_file(), name
```

- [ ] **Step 2: Run test to verify it fails**

```
py -3.11 -m pytest tests/test_export_all_formats.py tests/test_export_all.py tests/test_cli.py -v
```

Expected: `5 failed, 13 passed`: `AttributeError: module 'owlocr.export' has no attribute 'FORMATS_AVAILABLE'`, then `NotImplementedError: docx, pdf export arrives with plan C` in the `export_all` tests, and `test_word_and_searchable_pdf_are_written` fails because the CLI returns 1.

- [ ] **Step 3: Write minimal implementation**

In `owlocr/export/__init__.py`:

3a. Add below plan A's imports:

```python
from owlocr.export.docx import export_docx
from owlocr.export.searchable_pdf import export_searchable_pdf
```

3b. Directly below the line `FORMATS = ("md", "txt", "docx", "pdf")` add:

```python
FORMATS_AVAILABLE = ("md", "txt", "docx", "pdf")   # all four work; plan B enables the checkboxes from it
```

3c. Replace the function `export_all` with:

```python
def export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]:
    """Write every requested format into out_dir, named after the source file (design 10.6).
    Returns format -> path actually written (existing files are never overwritten). Never writes
    the .owl.json sidecar (the CLI and the plan B runner do)."""
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:                                  # checked before anything is written
        raise ValueError(f"unknown export formats: {unknown}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    stem = source.stem
    keep = bool(settings.get("keep_page_furniture", False))
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "md":
            written["md"] = export_markdown(doc, out_dir / f"{stem}.md", keep_furniture=keep,
                                            suspicious_appendix=bool(settings.get("append_suspicious_list", False)))
        elif fmt == "txt":
            written["txt"] = export_text(doc, out_dir / f"{stem}.txt", keep_furniture=keep)
        elif fmt == "docx":
            written["docx"] = export_docx(doc, out_dir / f"{stem}.docx", keep_furniture=keep)
        elif fmt == "pdf":
            written["pdf"] = export_searchable_pdf(doc, source, out_dir / f"{stem}.ocr.pdf")
    return written
```

Also change the module docstring's first line to `"""Exports: Markdown, plain text, Word and searchable PDF."""`.

- [ ] **Step 4: Run test to verify it passes**

```
py -3.11 -m pytest tests/test_export_all_formats.py tests/test_export_all.py tests/test_cli.py -v
py -3.11 -m pytest -q
$env:OWLOCR_NETWORK_TESTS = "1"; py -3.11 -m pytest -q; Remove-Item Env:OWLOCR_NETWORK_TESTS
```

Expected: `18 passed` for the three files; the whole suite passes (without the variable the three network tests are skipped); the network run passes everything, including `tests/test_real_dictionaries.py` and the two real downloads. Finally `git status --short` lists only the files of this task.

- [ ] **Step 5: Commit**

```
git add owlocr/export/__init__.py tests/test_export_all_formats.py tests/test_export_all.py tests/test_cli.py
git commit -m "Export all four formats and mark Word and PDF as available" -m "Replaces the two plan A tests that expected NotImplementedError for Word and PDF." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## Contract notes

Additions and clarifications to `docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md` made by this plan, including the points agreed with plans A and B.

1. **Rotation convention (agreed with plan B).** `Page.rotation_applied` is the number of degrees **clockwise** applied to the rendered page image before reading; the read image is `Image.rotate(-rotation_applied, expand=True)` of the page image, and block boxes (0..999) and `Page.width_px`/`height_px` refer to it. `guards.rotate_image` turns clockwise and `guards.best_rotation` returns clockwise degrees relative to the image it was given. The searchable PDF maps boxes back onto the original, unrotated page (including a PDF page's own `/Rotate`); Word and Markdown cut pictures from the page turned the same way.
2. **Exports (agreed with plan B).** `FORMATS_AVAILABLE = ("md", "txt", "docx", "pdf")` is defined in `owlocr/export/__init__.py` next to `FORMATS`. `export_all` never writes the `.owl.json` sidecar. Every export uses `Block.text` (edited in review), never `raw_text`.
3. **Engine errors, cancel and progress (agreed with plan A).** `process_page` never catches `EngineError`; the out-of-memory → Fast retry stays in the caller (CLI, plan B runner). The empty → other-mode retry (plan A's code, moved unchanged into `_read_once`) and the orientation probes live inside `process_page`; every engine call, probes included, gets the page's `on_progress` and `cancel` (probes through the private `_Relay`). A cancelled probe ends the probing and keeps the page as it is; it is never taken for an empty page. A timed-out or cancelled probe or strip ends the page's engine calls (pre-flight ruling R3): `best_rotation` returns 0 on `cancelled or timed_out` and `_read_strips` stops at the first such strip, because a timeout means the worker has ended itself and the caller reloads it for the next page (plan A contract note 24).
4. **Orientation and strips are plan C only (plan A contract note 17).** `looks_sideways` normalises the page against its own brightness (1st percentile = ink, median = paper), like plan A's `is_blank`, and is tested on `05_letter_poor_scan`, `07_letter_phone_photo` (not sideways), `09_letter_rotated_90` (sideways) and grey low-contrast copies.
5. **Pictures without a source parameter (plan A contract note 16).** `export_docx` re-renders the page from `Document.source_path`, as plan A's Markdown export does; when the file is gone, pictures are left out. `find_inputs` already skips `*.ocr.pdf`, the name the searchable PDF gets.
6. **New public helpers (additions, nothing in the contract reshaped):** `guards.rotate_image(image: Path, degrees: int, out: Path) -> Path`; `pages.cut_strips(image: Path, out_dir: Path) -> list[tuple[Path, int, int]]`; module `owlocr/pipeline/edits.py` (`Edit`, `apply_edits`); module `owlocr/pipeline/layout_rules.py` (`furniture_to_edges`, `move_captions`, `dehyphenate`, `ends_sentence`, `starts_lower`); `process.W_ROTATED = "rotated"`, a new code next to plan A's warnings `empty_retried`, `empty`, `runaway`, `time_limit`, `cancelled`.
7. **Dictionary component (plan B settings, plan D wizard).** Module `owlocr/pipeline/dictionaries.py`: `LANGUAGES`, `DictionaryError`, `manifest() -> dict`, `download(language, on_progress=None, cancel=None, entry=None) -> Path`, `verify(language, entry=None) -> dict[str, str]`, `remove(language) -> None`. Pins live in `owlocr/pipeline/dictionaries.json`. Czech (GPL) and English (SCOWL) dictionaries are downloaded on demand into `spellcheck.dictionaries_dir()`, never bundled in v1. Nothing downloads them automatically: plan D's wizard (as an optional component) or plan B's Settings must call `dictionaries.download`. Without them every dictionary rule is skipped and the app works as in plan A.
8. **Changed plan A internals.** `layout.arrange` → `_arrange_basic` (body unchanged, used only when no dictionary is installed); `markdown._ImageCutter` and `markdown._appendix` replaced (same output for unturned pages and `'suspicious'` flags, except the picture names and link style of note 19); `process.process_page` replaced, with plan A's reading logic moved unchanged into `_read_once` (same warnings, same engine arguments). Replaced plan A tests (task 19, pre-flight ruling R1): `tests/test_export_all.py::test_export_all_rejects_later_and_unknown_formats` → `test_export_all_rejects_unknown_formats`, `tests/test_cli.py::test_later_formats_fail_the_input` → `test_word_and_searchable_pdf_are_written`, and `tests/test_cli.py::test_later_formats_are_rejected_before_any_ocr` → `test_formats_not_available_are_rejected_before_any_ocr`; `owlocr/cli.py` is edited too (note 20).
9. **Private helpers used across modules:** `spellcheck._reset_cache`, `_mask_tags`, `_words`, `_protected`, `_personal_lower`, `_hit_rate` (used by `repair`, `layout_rules`, `guards`, `dictionaries` and the tests).
10. **Rules without a dictionary.** R1, plain d/t → ď/ť and look-alike repairs need a dictionary (design 9.1 point 1 wins over the unconditional wording of R1 in 9.2); R3, R4, R5 are character normalisations that always run and are still recorded as Flags; R2 flags foreign letters without a dictionary. The word rules run for Czech only; English text gets R3–R5 and suspicious-word flags.
11. **`bud` (plain letter) stays.** The real Czech dictionary contains `bud`, so the design's example `bud` → `buď` cannot be repaired safely; `bud'` (with apostrophe) is repaired, `kaprad` → `kapraď` works.
12. **`dictionary_hit_rate`** returns 1.0 without a dictionary (contract) and 0.0 with a dictionary when the text has no words. The post-OCR orientation check needs at least 10 words. `best_rotation` probes all four rotations including 0 (the same 120-token limit for a fair comparison, 60 s per probe) and makes no probe without a dictionary.
13. **Language `auto`** is resolved per page with `detect_language` on that page's text, as plan A already does (the design says "first page"; plan B's runner may pass the first page's result as a fixed language for the rest of a document).
14. **Suspicious appendix** exists only in Markdown, because only `export_markdown` has the parameter in the contract; it keeps plan A's format.
15. **`export_all`** passes `page_comments=False` to Markdown and `page_breaks=False` to Word (design 10.3 has no settings for them).
16. **Packaging (plan D).** Include `owlocr/pipeline/dictionaries.json` and `owlocr/export/fonts/*` as PyInstaller data at the same relative paths (the code finds them next to its module via `__file__`), list DejaVu Sans (Bitstream Vera licence + public domain) and the new dependencies (spylls MIT, pikepdf MPL-2.0, reportlab BSD, python-docx MIT, numpy BSD) in `THIRD_PARTY_NOTICES.md`.
17. **Accuracy thresholds (plan A contract note 10).** Plan C adds no accuracy test and does not change plan A's: CER at most 3 % per upright page and at least 95 % accented letters over all upright pages together.
18. **Test fixtures.** `tests/conftest.py` gains `tiny_dicts` and `no_dicts` next to plan A's autouse `owl_env`; they point `OWLOCR_HOME`/`OWLOCR_CONFIG` at their own temporary folders.
19. **Markdown image links and names (owner ruling R9, task 18; plan B Settings screen, plan D).** New setting `image_links` in `owlocr/settings.py`: default `"markdown"`, choices `"markdown"`, `"obsidian"`. `export_markdown` gains a keyword-only parameter `image_links: str = "markdown"` (any other value raises `ValueError`); `export_all` passes `settings.get("image_links", "markdown")`; the CLI has no flag for it (it reads the settings). Cut-out pictures are always saved as `<safe stem>-s<page:03d>-obr<n>.png` in the folder `<out stem>_images/` next to the `.md`, where safe stem = the stem of the `.md` actually written (after `paths.unique_path`, so a second export `Botanika_1.md` gets `Botanika_1-s001-obr1.png` and never collides with `Botanika-s001-obr1.png`), not the source file's stem, with each of `[]#^|\/:*?"<>` replaced by `_`; page is 1-based and `n` counts pictures through the whole document; this replaces plan A's `page001_img1.png`. `"markdown"` writes `![](<out stem>_images/<name>)`, wrapped as `![](<...>)` when the target contains a space or a parenthesis (ruling R2); `"obsidian"` writes `![[<name>]]` (file name only; Obsidian finds it anywhere in the vault, hence the unique `.md` stem in the name). Plan A tests updated for the new names: `tests/test_export_markdown.py::test_markdown_cuts_images_from_the_source` and `::test_image_links_survive_spaces_and_parentheses`; `tests/test_settings.py::test_defaults_have_exactly_the_design_keys` gains the key. Later (plan B, after its merge): Settings option "Odkazy na obrázky: Markdown / Obsidian" and an "Otevřít složku s obrázky" button.
20. **CLI format gate (pre-flight ruling R1, supersedes plan A contract note 20).** `owlocr/cli.py` refuses, before the engine starts, only formats missing from `FORMATS_AVAILABLE` (message "… export is not available in this build", exit code 1); with plan C all four formats pass. Unknown formats are still refused as before. Help text and module docstring read `md,txt,docx,pdf`.
21. **Language `auto` with one dictionary installed (final review I1).** With `auto`, repairs and flags use the detected language, except that a detected language without an installed dictionary gives way to Czech when the Czech dictionary is installed (the default install has only Czech; a Czech page with a low hit rate is detected as `en`). The orientation check, the probes and the "second reading is better" comparison always use a language whose dictionary is installed: the detected one if installed, else an installed one, Czech first (`process._orientation_language`). A fixed `cs`/`en` setting is used as it is.
22. **Orientation margin (final review M7).** `guards.ROTATION_MARGIN = 0.15`: `best_rotation` returns a turn only when that probe's dictionary hit rate beats probe 0 (the page as it is) by at least 0.15; otherwise it returns 0 and no second reading is made.
23. **Image-source page size and atomic writes (final review M5, M6).** For an image input, a searchable-PDF page larger than `searchable_pdf.MAX_PAGE_PT = 14400` pt on either side (a tall screenshot at 72 dpi) is scaled down, aspect kept, so its longer side is 14,400 pt; the text layer uses the same scale. `export_docx` and `export_searchable_pdf` write to a temporary file in the target folder and move it into place (`paths.atomic_write_file`); a failed write leaves neither the final file nor the temporary one.

## Self-review

| Contract or design item (plan C) | Task |
|---|---|
| `guards.looks_sideways` | 10 |
| `guards.dictionary_hit_rate` | 11 |
| `guards.best_rotation` (120-token Fast probes through the engine interface) | 11, used in 13 |
| Post-OCR orientation check wired into `process.py` | 13 |
| "Empty → retry once in the other mode" | plan A's code, kept inside `process_page` (`_read_once`), task 13; per strip in 14 |
| Tall-image strips (design 7.1) in `pages.py` / `process.py` | 12, 14 |
| `layout.arrange` caption move, furniture handling | 8 |
| `layout.arrange` dictionary-aware de-hyphenation (design 7.5) | 9 |
| `repair.repair_block` R1–R5 and dictionary-gated repairs, every repair a Flag | 5, 6, 7 |
| `spellcheck.available`, `known`, `dictionaries_dir`, look-up cache | 2 |
| `spellcheck.flag_suspicious`, `detect_language`, tokeniser keeping Czech letters, protection rules | 3 |
| Dictionary licence check, pinned manifest, download and verify | 1, 4 (real dictionaries also in 9 and 19) |
| `export_docx` | 17 |
| `export_searchable_pdf` (pikepdf + reportlab, render mode 3, font fitted, Unicode TTF, image inputs) | 15, 16 |
| `export_markdown(..., suspicious_appendix)` | plan A; foreign letters and turned crops 18 |
| `export_all` with all four formats, `FORMATS_AVAILABLE`, no sidecar, `Block.text` | 19 |
| Rotation convention agreed with plan B | 10, 11, 13, 16, 17, 18 |
| `EngineError` propagation, cancel and progress through probes (plan A) | 13 |

| Design section 9 error table row | Handling | Task and test |
|---|---|---|
| `ď`, `ť` as letter + apostrophe (`bud'`, `pojišt’ovnou`) | R1 | 7: `test_r1_straight_apostrophe_becomes_d_caron`, `test_r1_typographic_apostrophe_inside_word`; real dictionary: `tests/test_real_dictionaries.py` (9) |
| `ď`, `ť` as plain letter (`bud`, `kaprad`) | dictionary variant | 7: `test_plain_d_becomes_d_caron_when_only_that_is_a_word`, `test_known_word_with_d_is_left_alone` (see contract note 11 for `bud`) |
| Letter from another language (`także`) | R2 flag, repair by look-alike when known | 7: `test_r2_foreign_letter_repaired_to_known_look_alike`, `test_r2_foreign_letter_flagged_when_no_look_alike_is_known`, `test_r2_flags_even_without_dictionary`; appendix 18 |
| Line-break hyphen left in (`kaktu-sovitých`) | layout 7.5 | 9: `test_hyphen_inside_line_joined_when_joined_word_is_known`, `test_hyphen_at_line_break_joined`, `test_real_compound_keeps_its_hyphen`, `test_with_a_dictionary_a_line_break_join_needs_the_dictionary` |
| Accent wrong, letter swapped, space lost, scrambled (`bylinny`, `sporořyly`, `křápíku`) | flagged, no automatic change | 3: `test_unknown_words_are_flagged_with_offsets`; 13: `test_repairs_and_flags_are_applied` |
| Dash type (`-` for `–`) | R3 | 6: `test_r3_hyphen_between_spaces_becomes_en_dash` |
| Real word replaced by another real word | cannot be detected; review view and notice (plan B) | no code in plan C, by design |
| 9.2 R4 `,,` → `„`, R5 ligatures | rules | 6: `test_r4_double_comma_becomes_low_quote`, `test_r5_ligatures_become_plain_letters` |
| 9.1 principle 1 (repair only to a dictionary word) | gate in every word rule | 7: `test_r1_not_applied_when_result_unknown`, `test_word_repairs_skipped_without_dictionary`; 9: `test_no_joining_without_dictionary` |
| 9.1 principle 2 (every repair a Flag, can be switched off) | `edits.apply_edits` | 5; 7: `test_offsets_stay_right_after_several_length_changes`; plan A's `test_layout_runs_and_repairs_can_be_switched_off` |
| 9.1 principle 3 (capitalised inside a sentence, personal words) | `spellcheck._protected` | 3: `test_capitalised_word_inside_a_sentence_is_protected`, `test_personal_words_are_protected`; 7: `test_r2_capitalised_name_inside_sentence_is_protected`, `test_personal_word_list_protects` |
| 9.1 principle 4 (suspicious words as optional appendix, not marked in the text) | Markdown appendix | plan A; 18: `test_appendix_lists_foreign_letters_too` |
| 9.3 dictionary not bundled, downloaded; `document_language` `auto` | on-demand download; `detect_language` | 1, 4; 3: `test_detect_language*`; 13: `test_auto_language_picks_english` |

Verification done while writing this plan: plan A's code was rebuilt from `docs/superpowers/plans/2026-09-28-plan-a-foundation.md` in a scratch folder outside the repository (its suite: 213 passed without the `gpu` and `slow` tests), and every code block of tasks 1–19 was then applied to it in order. Each task's new tests failed before and passed after its implementation, and the whole suite passed after every task (335 passed, 3 network tests skipped at the end), including `tests/test_rotation_fake_worker.py` through plan A's real `SubprocessEngine` and `tests/fake_worker.py`, and the network run with the real pinned dictionaries (338 passed): the real Czech dictionary repaired `bud'`, `pojišt’ovnou`, `kaprad`, `także`, joined `kaktu-sovitých` and flagged `bylinny`. The searchable PDF was also checked by rendering a visible version of the text layer over the letter scan, including a page with `/Rotate 90`. No GPU was used and the model was never loaded.

Placeholder search: the plan was searched for "TBD", "TODO", "add error handling", "similar to task", "write tests for", "placeholder" and "fill in"; none occur outside this sentence.
