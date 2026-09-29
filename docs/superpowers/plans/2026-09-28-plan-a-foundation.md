# Owl OCR Plan A: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the engine-independent core of Owl OCR: paths and settings, the engine worker and its JSON-lines protocol, process lifetime, the client, the model store, the page pipeline, Markdown and text export, and a command-line tool that turns an image or PDF into Markdown and text.
**Architecture:** The app never imports torch. `owlocr.engine.client.SubprocessEngine` starts `worker/owl_worker.py` in the engine's own Python inside a Windows Job Object and talks one JSON object per line over stdin/stdout; `tests/fake_worker.py` speaks the same protocol without torch, so everything except the GPU accuracy test runs on any PC. `owlocr.pipeline` turns one input page into a `Page` (render with pypdfium2/Pillow, blank and runaway guards, parse the model's tagged output, basic layout), and `owlocr.export` writes Markdown and text from the resulting `Document`.
**Tech Stack:** Python 3.11 on Windows, Pillow 12, pypdfium2 5, ctypes (Job Object, process checks), urllib (model download), pytest 8+ and rapidfuzz (tests); engine side: torch 2.10.0, transformers 4.57.1.
**Spec:** docs/superpowers/specs/2026-09-28-owl-ocr-design.md and docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md

## Global Constraints

- Windows 10/11 x64 only. Python 3.11 only: every command uses `py -3.11`. Run all commands from the repository root `%USERPROFILE%\Desktop\OCR project`.
- Tests: `py -3.11 -m pytest ...` from the repository root. The default run excludes the `gpu` marker (`addopts = "-ra -m 'not gpu'"`).
- Names, parameters and return types of the interface contract (`docs/superpowers/specs/2026-09-28-owl-ocr-interfaces.md`) are used verbatim. Extra helpers must start with an underscore.
- Model pin: repo `baidu/Unlimited-OCR`, revision `07dea832e22aefee32ad281d4b80551282e1c168`, weights `model-00001-of-000001.safetensors`, 6,672,547,120 bytes, sha256 `2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6`. ModelScope mirror `PaddlePaddle/Unlimited-OCR`.
- Download skips `assets/*`, `wheel/*`, `*.pdf`, `*.gif`, `.gitattributes`. The model folder name stays `unlimited_ocr`.
- Engine pins: torch 2.10.0, torchvision 0.25.0, transformers 4.57.1 exactly (5.x breaks the model), tokenizers `>=0.22,<0.23`, huggingface_hub `>=0.34,<1.0`, Pillow 12.1.1, einops 0.8.2, addict 2.4.0, easydict 1.13, matplotlib 3.10.8, psutil 7.2.2, numpy `<3`, safetensors `>=0.4.3`, accelerate.
- AppData trap (design 4.1): tools started from the Claude desktop app get `%APPDATA%` and `%LOCALAPPDATA%` redirected. Every test gets `OWLOCR_HOME` and `OWLOCR_CONFIG` in a temp folder (`tests/conftest.py`, autouse). Every manual run sets `$env:OWLOCR_HOME = "%USERPROFILE%\Desktop\OCR project\engine"` and `$env:OWLOCR_CONFIG = "%USERPROFILE%\Desktop\OCR project\engine\config"` first.
- Hugging Face environment variables are set before the first import of `huggingface_hub` or `transformers`; the worker gets `HF_HOME`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, `PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`.
- Never use PyMuPDF (`fitz`, AGPL). PDFs are read and rendered only with `pypdfium2`.
- Model calls: `AutoModel` (never the class directly), never pass `attn_implementation`, always `eval_mode=True`, never `save_results=True` (it runs Python `eval()` on model output), always `no_repeat_ngram_size=35, ngram_window=128`.
- `worker/owl_worker.py` must not import `owlocr`: it runs in the engine's own Python.
- Never use the GPU without the owner's explicit permission: never run `-m gpu` tests, `spike/run_ocr.py`, or the manual real-engine command of Task 29 unless the owner asked for it and at least 9500 MiB of VRAM are free. Tests that start the real worker hide the GPU with `CUDA_VISIBLE_DEVICES=-1` (an empty value does not hide it).
- Never commit anything from `samples/` or any `spike/out/sample_*` file (copyrighted textbook). Only the ten synthetic pages and their raw outputs become fixtures.
- Never run `.bat` files on this PC.
- Subagents run on Opus 5.5 or Sonnet only.
- Work on branch `plan-a-foundation` (created in Task 1). Never push.
- Every commit message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (passed as a second `-m`).
- All text files UTF-8; JSON written to disk goes through `owlocr.paths.atomic_write_text`.

## File Structure

| File | Responsibility |
|---|---|
| `.gitignore` | modified: root-anchored `/engine/`, `/models/`, `/build/`, `/dist/`, `/output/` so the `owlocr/engine/` package is not ignored |
| `pyproject.toml` | project metadata and pytest configuration (markers `gpu`, `slow`; `gpu` excluded by default) |
| `requirements.txt` | app runtime dependencies of plan A (Pillow, pypdfium2) |
| `requirements-dev.txt` | test dependencies (pytest, rapidfuzz) |
| `LICENSE` | MIT, copyright Tomáš Burcal |
| `owlocr/__init__.py` | `__version__` |
| `owlocr/paths.py` | config dir, data root and every derived folder; atomic writes; unique file names |
| `owlocr/settings.py` | `settings.json`: defaults, validation, load/save/update |
| `owlocr/hardware.py` | `free_vram_mib()` via nvidia-smi and `REQUIRED_FREE_VRAM_MIB` (plan D adds the rest) |
| `owlocr/engine/__init__.py` | package marker |
| `owlocr/engine/registry.py` | `EngineSpec` and the pinned `UNLIMITED_OCR` |
| `owlocr/engine/protocol.py` | JSON-lines messages, `EngineInfo`, `PageResult`, `EngineError`, `ProtocolError` |
| `owlocr/engine/lifetime.py` | Windows Job Object with kill-on-close; process checks |
| `owlocr/engine/client.py` | `SubprocessEngine`, `sweep_stale_worker()`, `default_engine()` |
| `owlocr/engine/store.py` | model manifest, readiness check, verification, resumable download, adopt |
| `owlocr/pipeline/__init__.py` | package marker |
| `owlocr/pipeline/document.py` | `Flag`, `Block`, `Page`, `Document`, sidecar JSON, `plain_text()` |
| `owlocr/pipeline/parse.py` | raw model output to blocks; HTML tables to rows |
| `owlocr/pipeline/pages.py` | input files to pages (pypdfium2, Pillow); scan vs born-digital; `find_inputs` |
| `owlocr/pipeline/guards.py` | blank page, runaway output detection and trimming |
| `owlocr/pipeline/layout.py` | block order and line-break de-hyphenation |
| `owlocr/pipeline/repair.py` | pass-through stub (plan C) |
| `owlocr/pipeline/spellcheck.py` | pass-through stubs (plan C) |
| `owlocr/pipeline/process.py` | `ProcessOptions`, `process_page()`, `cleanup()` |
| `owlocr/export/__init__.py` | `FORMATS`, `export_all()` |
| `owlocr/export/text.py` | plain text export and clipboard text |
| `owlocr/export/markdown.py` | Markdown export, image crops |
| `owlocr/cli.py` | `python -m owlocr.cli` |
| `worker/owl_worker.py` | the real engine worker (torch, transformers, model) |
| `worker/requirements-engine.txt` | engine venv dependencies (without torch) |
| `scripts/dev_engine.py` | writes a development `install.json` (spike venv Python, model in `engine\`) |
| `tests/__init__.py` | makes `tests` importable (`from tests.conftest import ...`) |
| `tests/conftest.py` | per-test `OWLOCR_HOME` / `OWLOCR_CONFIG`; fixture paths |
| `tests/fixtures/pages/*` | the ten synthetic Czech pages and ground truth (moved from `spike/synthetic`) |
| `tests/fixtures/raw/*` | recorded model output of those pages (copied from `spike/out`) |
| `tests/fake_worker.py` | protocol-compatible fake worker, behaviour via `FAKE_WORKER` |
| `tests/lifetime_helper.py` | stand-in "app" process for the lifetime test |
| `tests/store_fakes.py` | fake Hugging Face / ModelScope server |
| `tests/pdf_fixtures.py` | builds born-digital and scanned PDFs on the fly |
| `tests/samples.py` | a small `Document` for document and export tests |
| `tests/scoring.py` | CER and accent accuracy (method of `spike/score.py`) |
| `tests/test_*.py` | one test module per unit, listed in each task |

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `LICENSE`, `owlocr/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- Modify: `.gitignore`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `owlocr.__version__ = "0.1.0"`; pytest fixture `owl_env` (autouse) returning `{"home": Path, "config": Path}`; constants `tests.conftest.REPO`, `FIXTURES`, `PAGES`, `RAW`, `FAKE_WORKER`.

- [ ] **Step 1: Write the failing test**

Create the branch and the dependency and pytest configuration, then install the dependencies:

```
git switch -c plan-a-foundation
```

Create `pyproject.toml`:

```toml
[project]
name = "owlocr"
version = "0.1.0"
description = "Offline OCR for Windows built on Baidu's Unlimited-OCR model"
requires-python = ">=3.11,<3.12"
license = { text = "MIT" }
authors = [{ name = "Tomáš Burcal" }]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -m 'not gpu'"
markers = [
    "gpu: needs an NVIDIA GPU with at least 9500 MiB free VRAM and the installed engine",
    "slow: takes more than a few seconds (starts real Python processes that import torch)",
]
```

Create `requirements.txt`:

```text
Pillow>=12.1,<13
pypdfium2>=5.10,<6
```

Create `requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.3
rapidfuzz>=3.14,<4
```

```
py -3.11 -m pip install -r requirements-dev.txt
```

Create `tests/__init__.py` as an empty file.

Create `tests/conftest.py`:

```python
"""Shared test setup.

Every test gets its own OWLOCR_HOME and OWLOCR_CONFIG inside pytest's tmp folder, so no test
ever reads or writes the real %APPDATA% / %LOCALAPPDATA% (design 4.1: tools started from the
Claude desktop app get those folders silently redirected).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
PAGES = FIXTURES / "pages"
RAW = FIXTURES / "raw"
FAKE_WORKER = REPO / "tests" / "fake_worker.py"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def owl_env(tmp_path, monkeypatch):
    home = tmp_path / "owl_home"
    config = tmp_path / "owl_config"
    home.mkdir()
    config.mkdir()
    monkeypatch.setenv("OWLOCR_HOME", str(home))
    monkeypatch.setenv("OWLOCR_CONFIG", str(config))
    monkeypatch.delenv("FAKE_WORKER", raising=False)
    return {"home": home, "config": config}
```

Create `tests/test_scaffold.py`:

```python
import os
from pathlib import Path

import owlocr
from tests.conftest import REPO


def test_version():
    assert owlocr.__version__ == "0.1.0"


def test_every_test_gets_private_folders(owl_env, tmp_path):
    assert Path(os.environ["OWLOCR_HOME"]) == owl_env["home"]
    assert Path(os.environ["OWLOCR_CONFIG"]) == owl_env["config"]
    assert tmp_path in Path(os.environ["OWLOCR_HOME"]).parents


def test_license_is_mit():
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Tomáš Burcal" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_scaffold.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr'` (collection error).

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `.gitignore` (the old bare `engine/` pattern would also hide the `owlocr/engine/` package; check with `git check-ignore -v --no-index owlocr/engine/client.py`, which must print nothing afterwards):

```text
# Python
__pycache__/
*.pyc
venv/
.venv/
.pytest_cache/
/build/
/dist/
*.spec.bak

# Model weights and the development engine: never commit (GBs).
# Anchored to the repository root: a bare "engine/" would also hide the owlocr/engine package.
/models/
/engine/
*.safetensors
*.bin
*.gguf

# App output / runtime
/output/
*.log
settings.local.json

# OS / editor
Thumbs.db
.DS_Store
.vscode/
.idea/

# Claude Code session files
.claude/
.superpowers/

# Spike / test data (samples/ holds a copyrighted textbook: never commit anything from it)
samples/
spike/out/
```

Create `LICENSE`:

```text
MIT License

Copyright (c) 2026 Tomáš Burcal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Create `owlocr/__init__.py`:

```python
"""Owl OCR: offline OCR for Windows."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_scaffold.py -q`
Expected: `3 passed`.
Run: `git check-ignore -v --no-index owlocr/engine/client.py`
Expected: no output (exit code 1).

- [ ] **Step 5: Commit**

```
git add .gitignore pyproject.toml requirements.txt requirements-dev.txt LICENSE owlocr/__init__.py tests/__init__.py tests/conftest.py tests/test_scaffold.py
git commit -m "Add project scaffolding, pytest config and MIT licence" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Test fixtures from the spike

**Files:**
- Create: `tests/fixtures/pages/*` (moved), `tests/fixtures/raw/*` (copied)
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: `tests.conftest.PAGES`, `tests.conftest.RAW`.
- Produces: `tests/fixtures/pages/NN_name.png` + `NN_name.gt.txt` for the ten pages `01_letter_clean`, `02_textbook_clean`, `03_small_print_clean`, `04_table_clean`, `05_letter_poor_scan`, `06_textbook_poor_scan`, `07_letter_phone_photo`, `08_screenshot`, `09_letter_rotated_90`, `10_blank_page`; `tests/fixtures/raw/NN_name.gundam.raw.txt` (Quality) and `NN_name.base.raw.txt` (Fast).

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixtures.py`:

```python
"""The fixture pages and the recorded model output of the spike."""
from tests.conftest import PAGES, RAW

NAMES = ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
         "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo", "08_screenshot",
         "09_letter_rotated_90", "10_blank_page")


def test_ten_pages_with_ground_truth():
    assert sorted(p.name for p in PAGES.iterdir()) == sorted(
        [f"{n}.png" for n in NAMES] + [f"{n}.gt.txt" for n in NAMES])


def test_recorded_raw_output_of_the_synthetic_pages_only():
    assert sorted(p.name for p in RAW.iterdir()) == sorted(
        [f"{n}.gundam.raw.txt" for n in NAMES] + [f"{n}.base.raw.txt" for n in NAMES])
    assert not [p for p in RAW.parent.rglob("*") if p.name.lower().startswith("sample")]


def test_ground_truth_is_utf8_czech():
    assert "Šťastná" in (PAGES / "01_letter_clean.gt.txt").read_text(encoding="utf-8")
    assert (PAGES / "10_blank_page.gt.txt").read_text(encoding="utf-8").strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_fixtures.py -q`
Expected: FAIL — `FileNotFoundError` for `tests\fixtures\pages`.

- [ ] **Step 3: Write minimal implementation**

Move the synthetic pages with git (keeps their history) and copy only the raw outputs whose names start with two digits (never `sample_*`, a copyrighted textbook):

```
py -3.11 -c "import pathlib; pathlib.Path('tests/fixtures').mkdir(parents=True, exist_ok=True)"
git mv spike/synthetic tests/fixtures/pages
py -3.11 -c "import shutil, pathlib; d = pathlib.Path('tests/fixtures/raw'); d.mkdir(parents=True, exist_ok=True); [shutil.copy2(p, d) for p in sorted(pathlib.Path('spike/out').glob('[0-9][0-9]_*.raw.txt'))]"
```

`spike/make_synthetic.py` and `spike/run_ocr.py` still name `spike/synthetic`; they are throwaway spike scripts and stay as they are.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_fixtures.py -q`
Expected: `3 passed`.
Run: `git status --short`
Expected: the renames `spike/synthetic/... -> tests/fixtures/pages/...`, untracked `tests/fixtures/raw/` and `tests/test_fixtures.py`, nothing from `samples/` and no `sample_` file.

- [ ] **Step 5: Commit**

```
git add tests/fixtures/raw tests/test_fixtures.py
git commit -m "Move synthetic pages to tests/fixtures and add recorded raw output" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Paths

**Files:**
- Create: `owlocr/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces (contract, verbatim): `config_dir() -> Path`, `data_root() -> Path`, `set_data_root(path: Path) -> None`, `engine_dir() -> Path`, `engine_python() -> Path`, `worker_dir() -> Path`, `models_dir() -> Path`, `model_dir(engine_id: str = "unlimited_ocr") -> Path`, `hf_home() -> Path`, `work_dir(job_id: str) -> Path`, `logs_dir() -> Path`, `queue_file() -> Path`, `settings_file() -> Path`, `resource_path(rel: str) -> Path`, `atomic_write_text(path: Path, text: str) -> None`, `unique_path(path: Path) -> Path`. `config_dir()`, `work_dir()` and `logs_dir()` create their folder.

- [ ] **Step 1: Write the failing test**

Create `tests/test_paths.py`:

```python
import sys
from pathlib import Path

from owlocr import paths


def test_env_overrides(owl_env):
    assert paths.config_dir() == owl_env["config"]
    assert paths.data_root() == owl_env["home"]


def test_config_dir_is_created(tmp_path, monkeypatch):
    target = tmp_path / "new" / "config"
    monkeypatch.setenv("OWLOCR_CONFIG", str(target))
    assert paths.config_dir() == target
    assert target.is_dir()


def test_location_txt_used_when_no_owlocr_home(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME")
    chosen = tmp_path / "D_drive" / "OwlData"
    paths.set_data_root(chosen)
    assert (paths.config_dir() / "location.txt").read_text(encoding="utf-8").strip() == str(chosen.resolve())
    assert paths.data_root() == chosen.resolve()


def test_default_data_root_is_localappdata(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_HOME")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.data_root() == tmp_path / "local" / "OwlOCR"


def test_default_config_dir_is_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("OWLOCR_CONFIG")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.config_dir() == tmp_path / "roaming" / "OwlOCR"


def test_owlocr_home_wins_over_location_txt(owl_env, tmp_path):
    paths.set_data_root(tmp_path / "elsewhere")
    assert paths.data_root() == owl_env["home"]


def test_derived_folders(owl_env):
    home = owl_env["home"]
    assert paths.engine_dir() == home / "engine"
    assert paths.engine_python() == home / "engine" / "venv" / "Scripts" / "python.exe"
    assert paths.worker_dir() == home / "engine" / "worker"
    assert paths.models_dir() == home / "models"
    assert paths.model_dir() == home / "models" / "unlimited_ocr"
    assert paths.model_dir("other") == home / "models" / "other"
    assert paths.hf_home() == home / "hf_home"
    assert paths.queue_file() == home / "queue.json"
    assert paths.settings_file() == owl_env["config"] / "settings.json"


def test_work_and_logs_dirs_are_created(owl_env):
    work = paths.work_dir("job42")
    assert work == owl_env["home"] / "work" / "job42" and work.is_dir()
    logs = paths.logs_dir()
    assert logs == owl_env["home"] / "logs" and logs.is_dir()


def test_resource_path_dev_and_frozen(tmp_path, monkeypatch):
    repo = Path(paths.__file__).resolve().parent.parent
    assert paths.resource_path("worker/owl_worker.py") == repo / "worker" / "owl_worker.py"
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("worker/owl_worker.py") == tmp_path / "worker" / "owl_worker.py"


def test_atomic_write_text(tmp_path):
    target = tmp_path / "sub" / "file.json"
    paths.atomic_write_text(target, "Příliš žluťoučký kůň\n")
    assert target.read_bytes() == "Příliš žluťoučký kůň\n".encode("utf-8")
    paths.atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert [p.name for p in target.parent.iterdir()] == ["file.json"]


def test_unique_path(tmp_path):
    first = tmp_path / "book.md"
    assert paths.unique_path(first) == first
    first.write_text("x")
    assert paths.unique_path(first) == tmp_path / "book_1.md"
    (tmp_path / "book_1.md").write_text("x")
    assert paths.unique_path(first) == tmp_path / "book_2.md"


def test_unique_path_compound_suffixes(tmp_path):
    (tmp_path / "book.ocr.pdf").write_text("x")
    (tmp_path / "book.owl.json").write_text("x")
    assert paths.unique_path(tmp_path / "book.ocr.pdf") == tmp_path / "book_1.ocr.pdf"
    assert paths.unique_path(tmp_path / "book.owl.json") == tmp_path / "book_1.owl.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_paths.py -q`
Expected: FAIL — `ImportError: cannot import name 'paths' from 'owlocr'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/paths.py`:

```python
r"""Where Owl OCR keeps its files (design section 4).

Config dir (small files): env OWLOCR_CONFIG, else %APPDATA%\OwlOCR.
Data root (large files):  env OWLOCR_HOME, else the path in <config dir>\location.txt,
                          else %LOCALAPPDATA%\OwlOCR.
"""
import os
import sys
import time
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def config_dir() -> Path:
    folder = _env_path("OWLOCR_CONFIG")
    if folder is None:
        folder = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "OwlOCR"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def data_root() -> Path:
    home = _env_path("OWLOCR_HOME")
    if home is not None:
        return home
    location = config_dir() / "location.txt"
    if location.is_file():
        stored = location.read_text(encoding="utf-8").strip()
        if stored:
            return Path(stored)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "OwlOCR"


def set_data_root(path: Path) -> None:
    atomic_write_text(config_dir() / "location.txt", str(Path(path).resolve()) + "\n")


def engine_dir() -> Path:
    return data_root() / "engine"


def engine_python() -> Path:
    return engine_dir() / "venv" / "Scripts" / "python.exe"


def worker_dir() -> Path:
    return engine_dir() / "worker"


def models_dir() -> Path:
    return data_root() / "models"


def model_dir(engine_id: str = "unlimited_ocr") -> Path:
    return models_dir() / engine_id


def hf_home() -> Path:
    return data_root() / "hf_home"


def work_dir(job_id: str) -> Path:
    folder = data_root() / "work" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def logs_dir() -> Path:
    folder = data_root() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def queue_file() -> Path:
    return data_root() / "queue.json"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def resource_path(rel: str) -> Path:
    """Files shipped with the app. In a PyInstaller build they live under sys._MEIPASS,
    in development under the repository root."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / rel


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text so that readers see either the old or the new file, never half of it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows: a virus scanner or indexer may hold the target open for a moment.
            if attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


_COMPOUND_SUFFIXES = (".ocr.pdf", ".owl.json")


def unique_path(path: Path) -> Path:
    """Return `path` if it is free, else the first free name with _1, _2 ... before the suffix."""
    path = Path(path)
    if not path.exists():
        return path
    name = path.name
    suffix = next((s for s in _COMPOUND_SUFFIXES if name.lower().endswith(s)), path.suffix)
    stem = name[: len(name) - len(suffix)] if suffix else name
    n = 1
    while True:
        candidate = path.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_paths.py -q`
Expected: `12 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/paths.py tests/test_paths.py
git commit -m "Add paths: config dir, data root, atomic writes, unique names" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Settings

**Files:**
- Create: `owlocr/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `paths.settings_file()`, `paths.atomic_write_text()`.
- Produces (contract): `DEFAULTS: dict` (the 13 keys of design 10.3 plus `"personal_words": []`), `load() -> dict`, `save(values: dict) -> None`, `get(key: str)`, `update(changes: dict) -> dict`, `class SettingsError(ValueError)`. `mode_default` defaults to `"quality"` until plan D sets it by tier; `language_ui` defaults to `"cs"` on a Czech Windows UI, else `"en"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings.py`:

```python
import json

import pytest

from owlocr import paths, settings

EXPECTED_KEYS = {
    "language_ui", "mode_default", "output_location", "output_folder", "formats",
    "use_text_layer", "document_language", "repairs_enabled", "append_suspicious_list",
    "keep_page_furniture", "idle_stop_minutes", "time_limit_s", "pdf_dpi", "personal_words",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_settings.py -q`
Expected: FAIL — `ImportError: cannot import name 'settings' from 'owlocr'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/settings.py`:

```python
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
}

_CHOICES = {
    "language_ui": ("cs", "en"),
    "mode_default": ("quality", "fast"),
    "output_location": ("next_to_source", "folder"),
    "use_text_layer": ("born_digital", "never", "always"),
    "document_language": ("auto", "cs", "en"),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_settings.py -q`
Expected: `20 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/settings.py tests/test_settings.py
git commit -m "Add settings with design defaults and validation" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Engine registry

**Files:**
- Create: `owlocr/engine/__init__.py`, `owlocr/engine/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces (contract): frozen dataclass `EngineSpec(engine_id, repo, revision, ignore, weights_sha256, modelscope_repo, torch, torchvision, transformers)`, `UNLIMITED_OCR: EngineSpec`, `get(engine_id: str) -> EngineSpec` (raises `KeyError` for unknown ids).

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
import dataclasses

import pytest

from owlocr.engine import registry


def test_unlimited_ocr_pins():
    spec = registry.get("unlimited_ocr")
    assert spec is registry.UNLIMITED_OCR
    assert spec.engine_id == "unlimited_ocr"
    assert spec.repo == "baidu/Unlimited-OCR"
    assert spec.revision == "07dea832e22aefee32ad281d4b80551282e1c168"
    assert len(spec.revision) == 40
    assert spec.ignore == ("assets/*", "wheel/*", "*.pdf", "*.gif", ".gitattributes")
    assert spec.weights_sha256 == "2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6"
    assert spec.modelscope_repo == "PaddlePaddle/Unlimited-OCR"
    assert (spec.torch, spec.torchvision, spec.transformers) == ("2.10.0", "0.25.0", "4.57.1")


def test_spec_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        registry.UNLIMITED_OCR.revision = "x"


def test_unknown_engine():
    with pytest.raises(KeyError):
        registry.get("tesseract")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/__init__.py`:

```python
"""OCR engine: registry of pinned engines, worker protocol, process lifetime, client, model store."""
```

Create `owlocr/engine/registry.py`:

```python
"""Known engines and their pinned versions (design 5.1)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    repo: str
    revision: str
    ignore: tuple[str, ...]
    weights_sha256: str
    modelscope_repo: str
    torch: str
    torchvision: str
    transformers: str


UNLIMITED_OCR = EngineSpec(
    engine_id="unlimited_ocr",
    repo="baidu/Unlimited-OCR",
    revision="07dea832e22aefee32ad281d4b80551282e1c168",
    ignore=("assets/*", "wheel/*", "*.pdf", "*.gif", ".gitattributes"),
    weights_sha256="2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6",
    modelscope_repo="PaddlePaddle/Unlimited-OCR",
    torch="2.10.0",
    torchvision="0.25.0",
    transformers="4.57.1",
)

_ENGINES = {UNLIMITED_OCR.engine_id: UNLIMITED_OCR}


def get(engine_id: str) -> EngineSpec:
    try:
        return _ENGINES[engine_id]
    except KeyError:
        raise KeyError(f"unknown engine: {engine_id}") from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_registry.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/__init__.py owlocr/engine/registry.py tests/test_registry.py
git commit -m "Add engine registry with the pinned Unlimited-OCR spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Worker protocol

**Files:**
- Create: `owlocr/engine/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces (contract): `MODES = ("quality", "fast")`, `encode(message: dict) -> str`, `decode(line: str) -> dict`, `class ProtocolError(ValueError)`, dataclasses `EngineInfo(pid, torch, transformers, cuda_available, gpu_name)` and `PageResult(text, seconds, prefix_tokens, output_tokens, hit_token_cap, cancelled, timed_out, peak_vram_mib)`, `class EngineError(RuntimeError)` with `EngineError(kind: str, message: str = "")` and attributes `.kind`, `.message`. Also `REQUEST_FIELDS` and `EVENT_FIELDS` (the required fields of design 5.4 per `cmd` / `event`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol.py`:

```python
import pytest

from owlocr.engine import protocol
from owlocr.engine.protocol import EngineError, EngineInfo, PageResult, ProtocolError


def test_modes():
    assert protocol.MODES == ("quality", "fast")


def test_encode_is_one_utf8_line():
    line = protocol.encode({"event": "result", "text": "žluťoučký\nkůň"})
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert "žluťoučký" in line


def test_round_trip_every_message():
    samples = [
        {"cmd": "load", "id": "1", "model_dir": "C:\\m", "device": "cuda", "dtype": "bfloat16"},
        {"cmd": "ocr", "id": "2", "image": "C:\\p.png", "mode": "quality", "max_new_tokens": 6000,
         "time_limit_s": 300.0},
        {"cmd": "cancel", "id": "2"},
        {"cmd": "unload", "id": "3"},
        {"cmd": "ping", "id": "4"},
        {"cmd": "shutdown", "id": "5"},
        {"event": "ready", "pid": 1, "torch": "2.10.0", "transformers": "4.57.1",
         "cuda_available": True, "gpu_name": "RTX"},
        {"event": "loaded", "id": "1", "seconds": 5.1, "vram_mib": 6457},
        {"event": "progress", "id": "2", "tokens": 120},
        {"event": "result", "id": "2", "text": "x", "seconds": 1.0, "prefix_tokens": 907,
         "output_tokens": 10, "hit_token_cap": False, "cancelled": False, "timed_out": False,
         "peak_vram_mib": 9000},
        {"event": "error", "id": "2", "kind": "out_of_memory", "message": "CUDA OOM"},
        {"event": "pong", "id": "4"},
        {"event": "unloaded", "id": "3"},
        {"event": "bye", "id": "5"},
    ]
    for message in samples:
        assert protocol.decode(protocol.encode(message)) == message


@pytest.mark.parametrize("line", [
    "not json",
    "[1, 2]",
    '{"id": "1"}',
    '{"cmd": "dance", "id": "1"}',
    '{"event": "party"}',
    '{"cmd": "ocr", "id": "1", "image": "x"}',
    '{"event": "result", "id": "1", "text": "x"}',
])
def test_decode_rejects(line):
    with pytest.raises(ProtocolError):
        protocol.decode(line)


def test_protocol_error_is_value_error():
    assert issubclass(ProtocolError, ValueError)


def test_engine_error_kind():
    e = EngineError("out_of_memory", "CUDA out of memory")
    assert isinstance(e, RuntimeError)
    assert e.kind == "out_of_memory"
    assert "CUDA out of memory" in str(e)
    assert EngineError("died").kind == "died"


def test_dataclasses():
    info = EngineInfo(pid=1, torch="2.10.0", transformers="4.57.1", cuda_available=False, gpu_name=None)
    assert info.gpu_name is None
    r = PageResult(text="a", seconds=1.0, prefix_tokens=2, output_tokens=3, hit_token_cap=False,
                   cancelled=False, timed_out=False, peak_vram_mib=0)
    assert r.output_tokens == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_protocol.py -q`
Expected: FAIL — `ImportError: cannot import name 'protocol' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/protocol.py`:

```python
"""JSON-lines protocol between the app and the engine worker (design 5.4).

One JSON object per line, UTF-8. Requests carry "cmd", events carry "event".
worker/owl_worker.py and tests/fake_worker.py speak the same protocol without importing this
module (the worker runs in the engine's own Python, where owlocr is not installed).
"""
import json
from dataclasses import dataclass

MODES = ("quality", "fast")

REQUEST_FIELDS = {
    "load": ("id", "model_dir", "device", "dtype"),
    "ocr": ("id", "image", "mode", "max_new_tokens", "time_limit_s"),
    "cancel": ("id",),
    "unload": ("id",),
    "ping": ("id",),
    "shutdown": ("id",),
}

EVENT_FIELDS = {
    "ready": ("pid", "torch", "transformers", "cuda_available", "gpu_name"),
    "loaded": ("id", "seconds", "vram_mib"),
    "progress": ("id", "tokens"),
    "result": ("id", "text", "seconds", "prefix_tokens", "output_tokens", "hit_token_cap",
               "cancelled", "timed_out", "peak_vram_mib"),
    "error": ("id", "kind", "message"),
    "pong": ("id",),
    "unloaded": ("id",),
    "bye": ("id",),
}


class ProtocolError(ValueError):
    pass


def encode(message: dict) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode(line: str) -> dict:
    try:
        message = json.loads(line)
    except ValueError as e:
        raise ProtocolError(f"not JSON: {line[:200]!r}") from e
    if not isinstance(message, dict):
        raise ProtocolError(f"not a JSON object: {line[:200]!r}")
    if "cmd" in message:
        fields = REQUEST_FIELDS.get(message["cmd"])
        what = f"request {message['cmd']!r}"
    elif "event" in message:
        fields = EVENT_FIELDS.get(message["event"])
        what = f"event {message['event']!r}"
    else:
        raise ProtocolError(f"neither cmd nor event: {line[:200]!r}")
    if fields is None:
        raise ProtocolError(f"unknown {what}")
    missing = [f for f in fields if f not in message]
    if missing:
        raise ProtocolError(f"{what} is missing {', '.join(missing)}")
    return message


@dataclass
class EngineInfo:
    pid: int
    torch: str
    transformers: str
    cuda_available: bool
    gpu_name: str | None


@dataclass
class PageResult:
    text: str
    seconds: float
    prefix_tokens: int
    output_tokens: int
    hit_token_cap: bool
    cancelled: bool
    timed_out: bool
    peak_vram_mib: int


class EngineError(RuntimeError):
    """kind: 'out_of_memory' | 'bad_image' | 'not_loaded' | 'internal' | 'died' | 'not_installed'"""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind
        self.message = message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_protocol.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/protocol.py tests/test_protocol.py
git commit -m "Add JSON-lines worker protocol and engine result types" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Free graphics memory

**Files:**
- Create: `owlocr/hardware.py`
- Test: `tests/test_hardware.py`

**Interfaces:**
- Consumes: nothing.
- Produces (contract, plan A part only): `free_vram_mib() -> int | None` (first NVIDIA GPU; `None` without nvidia-smi or on any failure), `REQUIRED_FREE_VRAM_MIB = {"quality": 9500, "fast": 7500}`. Plan D adds `Gpu`, `Tier`, `probe_gpus`, `ram_total_mib`, `choose_tier` to this same file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hardware.py` (it never runs the real nvidia-smi):

```python
import subprocess
from types import SimpleNamespace

from owlocr import hardware


def test_required_free_vram():
    assert hardware.REQUIRED_FREE_VRAM_MIB == {"quality": 9500, "fast": 7500}


def _fake_run(stdout="", returncode=0, exc=None):
    def run(cmd, **kwargs):
        assert cmd[0] == "nvidia-smi"
        assert "--query-gpu=memory.free" in cmd
        if exc:
            raise exc
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


def test_free_vram_first_gpu(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("15234\n8000\n"))
    assert hardware.free_vram_mib() == 15234


def test_no_nvidia_smi(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run(exc=FileNotFoundError()))
    assert hardware.free_vram_mib() is None


def test_nvidia_smi_fails(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("", returncode=9))
    assert hardware.free_vram_mib() is None


def test_nvidia_smi_timeout(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run",
                        _fake_run(exc=subprocess.TimeoutExpired("nvidia-smi", 15)))
    assert hardware.free_vram_mib() is None


def test_garbage_output(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "run", _fake_run("[N/A]\n"))
    assert hardware.free_vram_mib() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_hardware.py -q`
Expected: FAIL — `ImportError: cannot import name 'hardware' from 'owlocr'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/hardware.py`:

```python
"""Hardware facts. Plan A: free VRAM only. Plan D adds the GPU/RAM probe and tiers."""
import subprocess

REQUIRED_FREE_VRAM_MIB = {"quality": 9500, "fast": 7500}

_CREATE_NO_WINDOW = 0x08000000


def free_vram_mib() -> int | None:
    """Free memory of the first NVIDIA GPU in MiB, or None when there is no NVIDIA GPU."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                return int(float(line))
            except ValueError:
                return None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_hardware.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/hardware.py tests/test_hardware.py
git commit -m "Add free VRAM check via nvidia-smi" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Windows Job Object

**Files:**
- Create: `owlocr/engine/lifetime.py`
- Test: `tests/test_lifetime_job.py`

**Interfaces:**
- Consumes: nothing.
- Produces (contract): `class JobObject` with `__init__()` (CreateJobObjectW + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), `assign(pid: int) -> None`, `close() -> None`; `process_alive(pid: int) -> bool`. Private helpers used by the client: `_process_create_time(pid: int) -> int | None` (FILETIME integer of a running process) and `_terminate(pid: int) -> bool`.

Background: the engine Python `...\venv\Scripts\python.exe` is a launcher that starts the real interpreter as a child process. Assigning the launcher to the job is enough: children join the job automatically, and the launcher kills its child when it dies (both verified on this PC). The worker reports its own pid in the `ready` event; that pid is the one to watch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifetime_job.py`:

```python
import os
import subprocess
import sys
import time

from owlocr.engine import lifetime

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def _wait_dead(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not lifetime.process_alive(pid):
            return True
        time.sleep(0.05)
    return not lifetime.process_alive(pid)


def test_process_alive():
    assert lifetime.process_alive(os.getpid())
    assert not lifetime.process_alive(0)
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not lifetime.process_alive(p.pid)


def test_closing_the_job_kills_its_processes():
    job = lifetime.JobObject()
    p = subprocess.Popen(SLEEPER)
    try:
        job.assign(p.pid)
        assert lifetime.process_alive(p.pid)
        job.close()
        assert _wait_dead(p.pid, 5)
    finally:
        p.kill()


def test_close_twice_is_harmless():
    job = lifetime.JobObject()
    job.close()
    job.close()


def test_create_time_identifies_a_process():
    p = subprocess.Popen(SLEEPER)
    try:
        first = lifetime._process_create_time(p.pid)
        assert isinstance(first, int) and first > 0
        assert lifetime._process_create_time(p.pid) == first
        assert lifetime._terminate(p.pid)
        assert _wait_dead(p.pid, 5)
        assert lifetime._process_create_time(p.pid) is None
    finally:
        p.kill()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_lifetime_job.py -q`
Expected: FAIL — `ImportError: cannot import name 'lifetime' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/lifetime.py`:

```python
"""Windows Job Object that kills the engine worker when the app ends (design 5.6, safeguard 1).

The app holds the only handle to the job. When the app process ends for any reason (normal exit,
crash, Task Manager), Windows closes the handle and JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE kills every
process in the job. Child processes of an assigned process join the job automatically.
"""
import ctypes
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_JobObjectExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_k32.SetInformationJobObject.restype = wintypes.BOOL
_k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_k32.AssignProcessToJobObject.restype = wintypes.BOOL
_k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.GetExitCodeProcess.restype = wintypes.BOOL
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.TerminateProcess.restype = wintypes.BOOL
_k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_k32.GetProcessTimes.restype = wintypes.BOOL
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(_FILETIME)] * 4


def _last_error(what: str) -> OSError:
    code = ctypes.get_last_error()
    return ctypes.WinError(code, f"{what} failed (error {code})")


class JobObject:
    def __init__(self) -> None:
        handle = _k32.CreateJobObjectW(None, None)
        if not handle:
            raise _last_error("CreateJobObjectW")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(handle, _JobObjectExtendedLimitInformation,
                                            ctypes.byref(info), ctypes.sizeof(info)):
            error = _last_error("SetInformationJobObject")
            _k32.CloseHandle(handle)
            raise error
        self._handle = handle

    def assign(self, pid: int) -> None:
        if not self._handle:
            raise RuntimeError("job object is closed")
        process = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not process:
            raise _last_error(f"OpenProcess({pid})")
        try:
            if not _k32.AssignProcessToJobObject(self._handle, process):
                raise _last_error(f"AssignProcessToJobObject({pid})")
        finally:
            _k32.CloseHandle(process)

    def close(self) -> None:
        """Closing the last handle kills every process still in the job."""
        if self._handle:
            _k32.CloseHandle(self._handle)
            self._handle = None

    def __del__(self) -> None:
        self.close()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # Access denied means the process exists but belongs to someone else.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        _k32.CloseHandle(handle)


def _process_create_time(pid: int) -> int | None:
    """Creation time of a running process as a FILETIME integer; None if it cannot be read.
    Together with the pid it identifies a process even after its pid is reused."""
    if not process_alive(pid):
        return None
    handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
        if not _k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                    ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        _k32.CloseHandle(handle)


def _terminate(pid: int) -> bool:
    handle = _k32.OpenProcess(_PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(_k32.TerminateProcess(handle, 1))
    finally:
        _k32.CloseHandle(handle)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_lifetime_job.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/lifetime.py tests/test_lifetime_job.py
git commit -m "Add Windows Job Object with kill-on-close and process checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Fake worker

**Files:**
- Create: `tests/fake_worker.py`
- Test: `tests/test_fake_worker.py`

**Interfaces:**
- Consumes: the message fields of design 5.4 (as in `protocol.REQUEST_FIELDS` / `EVENT_FIELDS`).
- Produces (contract): `python tests/fake_worker.py --parent-pid <pid>`; flags in `FAKE_WORKER` (comma-separated): `slow`, `crash_on_ocr`, `oom_on_quality`, `ignore_shutdown`, `ignore_stdin_eof`, `empty`, `runaway`. `ocr` answers with the content of `<image path>.raw.txt` when it exists, else `<|det|>text [100, 100, 900, 200]<|/det|>fake text for <image name>`. Like the real worker, it exits on stdin EOF, on `shutdown` and when the parent is gone (checked every 2 s), and `shutdown` also cancels a page being read.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fake_worker.py`:

```python
"""The fake worker itself, driven over raw pipes (no client code involved)."""
import json
import os
import subprocess
import sys

from owlocr.engine import lifetime
from tests.conftest import FAKE_WORKER


def _start(flags: str = ""):
    env = dict(os.environ, FAKE_WORKER=flags, PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(os.getpid())],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)


def _send(p, message):
    p.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    p.stdin.flush()


def _read(p):
    return json.loads(p.stdout.readline().decode("utf-8"))


def test_ready_ping_load_ocr_shutdown(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"not really a png")
    p = _start()
    try:
        ready = _read(p)
        assert ready["event"] == "ready"
        assert lifetime.process_alive(ready["pid"])       # the worker's own pid
        _send(p, {"cmd": "ping", "id": "1"})
        assert _read(p) == {"event": "pong", "id": "1"}
        _send(p, {"cmd": "ocr", "id": "2", "image": str(image), "mode": "quality",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        assert _read(p)["kind"] == "not_loaded"
        _send(p, {"cmd": "load", "id": "3", "model_dir": "x", "device": "cpu", "dtype": "float32"})
        assert _read(p)["event"] == "loaded"
        _send(p, {"cmd": "ocr", "id": "4", "image": str(image), "mode": "quality",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        result = _read(p)
        assert result["event"] == "result"
        assert result["text"] == "<|det|>text [100, 100, 900, 200]<|/det|>fake text for page.png"
        (tmp_path / "page.png.raw.txt").write_text("<|det|>title [1, 2, 3, 4]<|/det|>Nadpis", encoding="utf-8")
        _send(p, {"cmd": "ocr", "id": "5", "image": str(image), "mode": "fast",
                  "max_new_tokens": 6000, "time_limit_s": 300})
        assert _read(p)["text"] == "<|det|>title [1, 2, 3, 4]<|/det|>Nadpis"
        _send(p, {"cmd": "shutdown", "id": "6"})
        assert _read(p) == {"event": "bye", "id": "6"}
        assert p.wait(timeout=5) == 0
    finally:
        p.kill()


def test_stdin_eof_ends_the_fake_worker():
    p = _start()
    try:
        assert _read(p)["event"] == "ready"
        p.stdin.close()
        assert p.wait(timeout=5) == 0
    finally:
        p.kill()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_fake_worker.py -q`
Expected: FAIL — `json.decoder.JSONDecodeError: Expecting value` (the worker script does not exist, so stdout is empty).

- [ ] **Step 3: Write minimal implementation**

Create `tests/fake_worker.py`:

```python
"""Fake engine worker: same command line and protocol as worker/owl_worker.py, no torch.

    python fake_worker.py --parent-pid <pid>

Behaviour is chosen with the environment variable FAKE_WORKER, a comma-separated list of:
  slow              2 s per page with progress events (cancel and time limit work)
  crash_on_ocr      the process exits with code 3 when it receives `ocr`
  oom_on_quality    `ocr` in quality mode answers error out_of_memory
  ignore_shutdown   `shutdown` is ignored (the client must terminate the process)
  ignore_stdin_eof  stdin EOF does not end the process (only the parent watchdog does)
  empty             every page returns empty text
  runaway           every page returns a long repetition and hit_token_cap = true
`ocr` answers with the content of "<image path>.raw.txt" when that file exists, else with
"<|det|>text [100, 100, 900, 200]<|/det|>fake text for <image name>".
"""
import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

FLAGS = {f.strip() for f in os.environ.get("FAKE_WORKER", "").split(",") if f.strip()}

_out = sys.stdout
_out_lock = threading.Lock()
_requests: "queue.Queue[dict]" = queue.Queue()
_cancelled: set[str] = set()
_cancel_all = threading.Event()        # set by `shutdown`: the page being read stops, as in the real worker
_cancel_lock = threading.Lock()


def send(message: dict) -> None:
    with _out_lock:
        _out.write(json.dumps(message, ensure_ascii=False) + "\n")
        _out.flush()


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def parent_alive(pid: int) -> bool:
    handle = _k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5           # access denied = exists
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        _k32.CloseHandle(handle)


def watchdog(parent_pid: int) -> None:
    while True:
        time.sleep(2.0)
        if not parent_alive(parent_pid):
            os._exit(0)


def reader() -> None:
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            send({"event": "error", "id": None, "kind": "internal", "message": "bad JSON"})
            continue
        if message.get("cmd") == "cancel":
            with _cancel_lock:
                _cancelled.add(str(message.get("id")))
            continue
        if message.get("cmd") == "shutdown" and "ignore_shutdown" not in FLAGS:
            _cancel_all.set()
        _requests.put(message)
    if "ignore_stdin_eof" not in FLAGS:
        os._exit(0)


def is_cancelled(request_id: str) -> bool:
    with _cancel_lock:
        return request_id in _cancelled or _cancel_all.is_set()


def page_text(image: Path) -> str:
    if "empty" in FLAGS:
        return ""
    if "runaway" in FLAGS:
        return "<|det|>text [100, 100, 900, 900]<|/det|>" + "opakuji se pořád dokola " * 1000
    raw = Path(str(image) + ".raw.txt")
    if raw.is_file():
        return raw.read_text(encoding="utf-8")
    return f"<|det|>text [100, 100, 900, 200]<|/det|>fake text for {image.name}"


def ocr(message: dict, loaded: bool) -> None:
    rid = message["id"]
    if not loaded:
        send({"event": "error", "id": rid, "kind": "not_loaded", "message": "load the model first"})
        return
    if "crash_on_ocr" in FLAGS:
        os._exit(3)
    if "oom_on_quality" in FLAGS and message["mode"] == "quality":
        send({"event": "error", "id": rid, "kind": "out_of_memory", "message": "fake CUDA out of memory"})
        return
    image = Path(message["image"])
    if not image.is_file():
        send({"event": "error", "id": rid, "kind": "bad_image", "message": f"no such file: {image}"})
        return
    t0 = time.monotonic()
    text = page_text(image)
    cancelled = timed_out = False
    if "slow" in FLAGS:
        steps = 20                                      # 20 x 0.1 s = 2 s
        for step in range(1, steps + 1):
            time.sleep(0.1)
            if step % 5 == 0:
                send({"event": "progress", "id": rid, "tokens": step * 10})
            if is_cancelled(rid):
                cancelled = True
            elif time.monotonic() - t0 > float(message["time_limit_s"]):
                timed_out = True
            if cancelled or timed_out:
                text = text[: max(1, len(text) * step // steps)]
                break
    elif is_cancelled(rid):
        cancelled, text = True, ""
    send({
        "event": "result", "id": rid, "text": text, "seconds": round(time.monotonic() - t0, 3),
        "prefix_tokens": 907 if message["mode"] == "quality" else 277,
        "output_tokens": len(text) // 3,
        "hit_token_cap": "runaway" in FLAGS,
        "cancelled": cancelled, "timed_out": timed_out, "peak_vram_mib": 0,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    threading.Thread(target=watchdog, args=(args.parent_pid,), daemon=True).start()
    threading.Thread(target=reader, daemon=True).start()
    send({"event": "ready", "pid": os.getpid(), "torch": "fake", "transformers": "fake",
          "cuda_available": False, "gpu_name": None})
    loaded = False
    while True:
        message = _requests.get()
        cmd, rid = message.get("cmd"), message.get("id")
        if cmd == "load":
            loaded = True
            send({"event": "loaded", "id": rid, "seconds": 0.01, "vram_mib": 0})
        elif cmd == "unload":
            loaded = False
            send({"event": "unloaded", "id": rid})
        elif cmd == "ping":
            send({"event": "pong", "id": rid})
        elif cmd == "ocr":
            ocr(message, loaded)
        elif cmd == "shutdown":
            if "ignore_shutdown" in FLAGS:
                continue
            send({"event": "bye", "id": rid})
            os._exit(0)
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"unknown cmd {cmd!r}"})


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_fake_worker.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add tests/fake_worker.py tests/test_fake_worker.py
git commit -m "Add fake engine worker for tests" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: SubprocessEngine

**Files:**
- Create: `owlocr/engine/client.py` (everything except `sweep_stale_worker` and `default_engine`, which Task 11 appends)
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `paths.hf_home()`, `paths.engine_dir()`, `paths.atomic_write_text()`; `lifetime.JobObject`, `lifetime._process_create_time`; `protocol.MODES`, `EngineError`, `EngineInfo`, `PageResult`, `ProtocolError`, `decode`, `encode`.
- Produces (contract): `class SubprocessEngine` with class attribute `engine_id = "unlimited_ocr"`, `__init__(python: Path, worker_script: Path, model_dir: Path, device: str, dtype: str, log_file: Path, env: dict | None = None)`, `start() -> EngineInfo`, `load() -> float`, `ocr_page(image: Path, mode: str, max_new_tokens: int = 6000, time_limit_s: float = 300.0, on_progress: Callable[[int], None] | None = None, cancel: threading.Event | None = None) -> PageResult`, `unload() -> None`, `stop(timeout_s: float = 5.0) -> None`, `is_running() -> bool`, property `loaded -> bool`. Public attributes `python`, `worker_script`, `model_dir`, `device`, `dtype`, `log_file`, `env`.
- Guaranteed behaviour (plan B relies on it): the constructor starts nothing; `start()` (or `load()`, which starts when needed) launches the worker with `os.environ` merged with `env`; a dead worker raises `EngineError("died")` from the pending call and from later calls until `load()`/`start()` runs again; CUDA out of memory raises `EngineError("out_of_memory")`; `stop()` may be called from any thread at any time, and a call to `ocr_page` blocked in another thread then returns the partial `PageResult` with `cancelled=True` (the worker cancels the page on `shutdown` and answers before exiting); only if the worker does not exit within `timeout_s` is it killed, and then the blocked call raises `EngineError("died")`. Private: `_write_pid_file(pid)`, `_remove_pid_file(pid)`, `_pid_file()` (`<engine dir>\worker.pid` holds `{"pid", "created"}` of the worker's own process).

- [ ] **Step 1: Write the failing test**

Create `tests/test_client.py`:

```python
"""SubprocessEngine against tests/fake_worker.py."""
import json
import sys
import threading
import time

import pytest

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine
from owlocr.engine.protocol import EngineError, EngineInfo, PageResult
from tests.conftest import FAKE_WORKER


def make_engine(tmp_path, flags: str = "") -> SubprocessEngine:
    return SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER, model_dir=tmp_path / "model",
                            device="cpu", dtype="float32", log_file=tmp_path / "logs" / "engine.log",
                            env={"FAKE_WORKER": flags})


@pytest.fixture
def page(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"fake image")
    return image


def test_start_load_ocr_stop(tmp_path, page):
    engine = make_engine(tmp_path)
    try:
        info = engine.start()
        assert isinstance(info, EngineInfo)
        assert info.torch == "fake" and info.cuda_available is False and info.gpu_name is None
        assert engine.is_running() and not engine.loaded
        assert isinstance(engine.load(), float)
        assert engine.loaded
        result = engine.ocr_page(page, "quality")
        assert isinstance(result, PageResult)
        assert result.text.endswith("fake text for page.png")
        assert result.prefix_tokens == 907
        assert not (result.cancelled or result.timed_out or result.hit_token_cap)
        assert engine.ocr_page(page, "fast").prefix_tokens == 277
    finally:
        engine.stop()
    assert not engine.is_running() and not engine.loaded
    assert not lifetime.process_alive(info.pid)


def test_constructing_does_not_start_a_process(tmp_path):
    engine = make_engine(tmp_path)
    assert not engine.is_running() and not engine.loaded
    assert engine.device == "cpu" and engine.dtype == "float32"
    assert engine.engine_id == "unlimited_ocr"


def test_app_environment_reaches_the_worker(tmp_path, page, monkeypatch):
    monkeypatch.setenv("FAKE_WORKER", "oom_on_quality")
    engine = SubprocessEngine(python=sys.executable, worker_script=FAKE_WORKER, model_dir=tmp_path / "m",
                              device="cpu", dtype="float32", log_file=tmp_path / "engine.log")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "out_of_memory"
    finally:
        engine.stop()


def test_load_starts_the_worker_when_needed(tmp_path, page):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        assert engine.is_running() and engine.loaded
    finally:
        engine.stop()


def test_worker_env_and_log(tmp_path):
    engine = make_engine(tmp_path)
    env = engine._worker_env()
    assert env["HF_HUB_OFFLINE"] == "1" and env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["PYTORCH_CUDA_ALLOC_CONF"] == "expandable_segments:True"
    assert env["PYTHONIOENCODING"] == "utf-8" and env["PYTHONUNBUFFERED"] == "1"
    assert env["HF_HOME"] == str(paths.hf_home())
    assert env["FAKE_WORKER"] == ""
    try:
        engine.start()
    finally:
        engine.stop()
    assert "engine start" in (tmp_path / "logs" / "engine.log").read_text(encoding="utf-8")


def test_ocr_before_load_is_not_loaded(tmp_path, page):
    engine = make_engine(tmp_path)
    with pytest.raises(EngineError) as e:
        engine.ocr_page(page, "quality")
    assert e.value.kind == "not_loaded"
    try:
        engine.start()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "not_loaded"
    finally:
        engine.stop()


def test_bad_mode(tmp_path, page):
    with pytest.raises(ValueError):
        make_engine(tmp_path).ocr_page(page, "turbo")


def test_bad_image(tmp_path):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(tmp_path / "missing.png", "quality")
        assert e.value.kind == "bad_image"
        assert engine.is_running()
    finally:
        engine.stop()


def test_progress_events(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    seen = []
    try:
        engine.load()
        result = engine.ocr_page(page, "quality", on_progress=seen.append)
    finally:
        engine.stop()
    assert seen == [50, 100, 150, 200]
    assert not result.cancelled


def test_cancel_returns_partial_result(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    try:
        engine.load()
        t0 = time.monotonic()
        result = engine.ocr_page(page, "quality", cancel=cancel)
        assert time.monotonic() - t0 < 1.8
    finally:
        engine.stop()
    assert result.cancelled and not result.timed_out


def test_time_limit(tmp_path, page):
    engine = make_engine(tmp_path, "slow")
    try:
        engine.load()
        result = engine.ocr_page(page, "quality", time_limit_s=0.5)
    finally:
        engine.stop()
    assert result.timed_out and not result.cancelled


def test_out_of_memory_is_an_engine_error(tmp_path, page):
    engine = make_engine(tmp_path, "oom_on_quality")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "out_of_memory"
        assert engine.ocr_page(page, "fast").text        # the worker is still fine
    finally:
        engine.stop()


def test_crash_is_died_and_restart_works(tmp_path, page):
    engine = make_engine(tmp_path, "crash_on_ocr")
    try:
        engine.load()
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "died"
        assert not engine.is_running() and not engine.loaded
        with pytest.raises(EngineError) as e:
            engine.ocr_page(page, "quality")
        assert e.value.kind == "died"
        engine.env["FAKE_WORKER"] = ""
        engine.load()
        assert engine.ocr_page(page, "quality").text
    finally:
        engine.stop()


def test_stop_terminates_a_worker_that_ignores_shutdown(tmp_path):
    engine = make_engine(tmp_path, "ignore_shutdown")
    info = engine.start()
    t0 = time.monotonic()
    engine.stop(timeout_s=1.0)
    assert time.monotonic() - t0 < 4
    assert not engine.is_running()
    deadline = time.monotonic() + 5
    while lifetime.process_alive(info.pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not lifetime.process_alive(info.pid)


def test_stop_from_another_thread_while_a_page_is_read(tmp_path, page):
    """Plan B's manual "Stop engine": stop() while ocr_page() runs in the runner thread."""
    engine = make_engine(tmp_path, "slow")
    engine.load()
    outcome = {}

    def read():
        try:
            outcome["result"] = engine.ocr_page(page, "quality")
        except EngineError as e:
            outcome["error"] = e

    reader = threading.Thread(target=read)
    reader.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    engine.stop()
    reader.join(timeout=10)
    assert time.monotonic() - t0 < 3
    assert not reader.is_alive() and not engine.is_running()
    # The worker cancels the page on `shutdown` and answers before it exits, so the blocked call
    # returns the partial result. (A worker that does not exit within timeout_s is killed, and
    # then the blocked call raises EngineError("died") instead.)
    assert "error" not in outcome
    assert outcome["result"].cancelled is True


def test_unload(tmp_path):
    engine = make_engine(tmp_path)
    try:
        engine.load()
        engine.unload()
        assert engine.is_running() and not engine.loaded
    finally:
        engine.stop()


def test_stop_without_start_is_harmless(tmp_path):
    make_engine(tmp_path).stop()


def test_missing_python_is_not_installed(tmp_path):
    engine = make_engine(tmp_path)
    engine.python = tmp_path / "no" / "python.exe"
    with pytest.raises(EngineError) as e:
        engine.start()
    assert e.value.kind == "not_installed"


def test_pid_file_written_and_removed(tmp_path):
    engine = make_engine(tmp_path)
    info = engine.start()
    pid_file = paths.engine_dir() / "worker.pid"
    try:
        data = json.loads(pid_file.read_text(encoding="utf-8"))
        assert data["pid"] == info.pid and isinstance(data["created"], int)
    finally:
        engine.stop()
    assert not pid_file.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.engine.client'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/client.py`:

```python
"""SubprocessEngine: runs the engine worker as a child process and talks JSON lines to it.

The worker runs in the engine's own Python (with torch). It is started inside a Windows Job
Object, gets the app's pid for its watchdog, and exits on stdin EOF (design 5.6). Its stderr goes
to logs/engine.log. One request is in flight at a time.
"""
import itertools
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.protocol import MODES, EngineError, EngineInfo, PageResult, ProtocolError, decode, encode

_CREATE_NO_WINDOW = 0x08000000
_START_TIMEOUT_S = 180.0      # importing torch on a cold disk can take a minute
_LOAD_TIMEOUT_S = 900.0
_OCR_GRACE_S = 120.0          # on top of the page's own time limit
_SMALL_TIMEOUT_S = 60.0


class SubprocessEngine:
    engine_id = "unlimited_ocr"

    def __init__(self, python: Path, worker_script: Path, model_dir: Path,
                 device: str, dtype: str, log_file: Path, env: dict | None = None) -> None:
        self.python = Path(python)
        self.worker_script = Path(worker_script)
        self.model_dir = Path(model_dir)
        self.device = device
        self.dtype = dtype
        self.log_file = Path(log_file)
        self.env = dict(env or {})
        self._proc: subprocess.Popen | None = None
        self._job: lifetime.JobObject | None = None
        self._log = None
        self._events: queue.Queue = queue.Queue()
        self._request_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._loaded = False
        self._died = False
        self._info: EngineInfo | None = None

    # ---- process -------------------------------------------------------------------------

    def _worker_env(self) -> dict:
        env = dict(os.environ)
        env.update({
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "HF_HOME": str(paths.hf_home()),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        })
        env.update(self.env)
        return env

    def start(self) -> EngineInfo:
        if self.is_running() and self._info is not None:
            return self._info
        self._cleanup()
        self._died = False
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_file, "ab")
        self._log.write(f"\n--- engine start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode("utf-8"))
        self._log.flush()
        cmd = [str(self.python), "-u", str(self.worker_script), "--parent-pid", str(os.getpid())]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
                                    cwd=str(self.worker_script.parent), env=self._worker_env(),
                                    creationflags=_CREATE_NO_WINDOW)
        except OSError as e:
            self._cleanup()
            raise EngineError("not_installed", f"cannot start {self.python}: {e}") from e
        self._proc = proc
        self._job = lifetime.JobObject()
        try:
            self._job.assign(proc.pid)
        except OSError:
            if proc.poll() is None:   # a live worker outside the job would break design 5.6
                proc.kill()
                self._cleanup()
                raise
        self._events = queue.Queue()
        threading.Thread(target=self._read_events, args=(proc, self._events),
                         name="owl-engine-reader", daemon=True).start()
        ready = self._wait(None, {"ready"}, _START_TIMEOUT_S)
        self._info = EngineInfo(pid=int(ready["pid"]), torch=str(ready["torch"]),
                                transformers=str(ready["transformers"]),
                                cuda_available=bool(ready["cuda_available"]), gpu_name=ready["gpu_name"])
        _write_pid_file(self._info.pid)
        return self._info

    def _read_events(self, proc: subprocess.Popen, events: queue.Queue) -> None:
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    events.put(decode(line))
                except ProtocolError as e:
                    self._log_line(f"[client] ignored bad line from worker: {e}")
        except (OSError, ValueError):
            pass
        events.put(None)

    def _log_line(self, text: str) -> None:
        log = self._log
        if log is not None and not log.closed:
            try:
                log.write((text + "\n").encode("utf-8"))
                log.flush()
            except (OSError, ValueError):
                pass

    def _send(self, message: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise EngineError("died", "engine is not running")
        with self._send_lock:
            try:
                proc.stdin.write(encode(message).encode("utf-8"))
                proc.stdin.flush()
            except (OSError, ValueError) as e:
                raise EngineError("died", f"cannot write to the engine: {e}") from e

    def _wait(self, request_id: str | None, done: set[str], timeout: float,
              on_progress: Callable[[int], None] | None = None,
              cancel: threading.Event | None = None) -> dict:
        deadline = time.monotonic() + timeout
        cancel_sent = False
        while True:
            if cancel is not None and cancel.is_set() and not cancel_sent and request_id is not None:
                self._send({"cmd": "cancel", "id": request_id})
                cancel_sent = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._die(f"no answer within {timeout:.0f} s")
            try:
                event = self._events.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue
            if event is None:
                code = self._proc.poll() if self._proc else None
                self._die(f"worker exited (code {code}); see {self.log_file}")
            if request_id is not None and event.get("id") != request_id:
                continue          # late event of an earlier request
            kind = event["event"]
            if kind == "progress":
                if on_progress is not None:
                    on_progress(int(event["tokens"]))
                continue
            if kind == "error":
                raise EngineError(str(event["kind"]), str(event["message"]))
            if kind in done:
                return event

    def _die(self, message: str):
        self._died = True
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
        self._cleanup()
        raise EngineError("died", message)

    def _request(self, cmd: str, fields: dict, done: set[str], timeout: float,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> dict:
        with self._request_lock:
            if not self.is_running():
                raise EngineError("died" if self._died else "not_loaded", "engine is not running")
            request_id = str(next(self._ids))
            self._send({"cmd": cmd, "id": request_id, **fields})
            return self._wait(request_id, done, timeout, on_progress, cancel)

    # ---- public API ----------------------------------------------------------------------

    def load(self) -> float:
        if not self.is_running():
            self.start()
        event = self._request("load", {"model_dir": str(self.model_dir), "device": self.device,
                                       "dtype": self.dtype}, {"loaded"}, _LOAD_TIMEOUT_S)
        self._loaded = True
        return float(event["seconds"])

    def ocr_page(self, image: Path, mode: str, max_new_tokens: int = 6000,
                 time_limit_s: float = 300.0,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> PageResult:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        event = self._request("ocr", {"image": str(Path(image).resolve()), "mode": mode,
                                      "max_new_tokens": int(max_new_tokens),
                                      "time_limit_s": float(time_limit_s)},
                              {"result"}, float(time_limit_s) + _OCR_GRACE_S, on_progress, cancel)
        return PageResult(text=str(event["text"]), seconds=float(event["seconds"]),
                          prefix_tokens=int(event["prefix_tokens"]),
                          output_tokens=int(event["output_tokens"]),
                          hit_token_cap=bool(event["hit_token_cap"]), cancelled=bool(event["cancelled"]),
                          timed_out=bool(event["timed_out"]), peak_vram_mib=int(event["peak_vram_mib"]))

    def unload(self) -> None:
        if self.is_running():
            self._request("unload", {}, {"unloaded"}, _SMALL_TIMEOUT_S)
        self._loaded = False

    def stop(self, timeout_s: float = 5.0) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                self._send({"cmd": "shutdown", "id": "stop"})
            except EngineError:
                pass
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self._cleanup()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def loaded(self) -> bool:
        return self._loaded and self.is_running()

    def _cleanup(self) -> None:
        proc, self._proc = self._proc, None
        self._loaded = False
        if proc is not None and proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        if self._job is not None:
            self._job.close()          # kills whatever is left of the worker
            self._job = None
        if self._info is not None:
            _remove_pid_file(self._info.pid)
            self._info = None
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None


# ---- worker.pid (read by sweep_stale_worker) ------------------------------------------------

def _pid_file() -> Path:
    return paths.engine_dir() / "worker.pid"


def _write_pid_file(pid: int) -> None:
    created = lifetime._process_create_time(pid)
    paths.atomic_write_text(_pid_file(), json.dumps({"pid": pid, "created": created}))


def _remove_pid_file(pid: int) -> None:
    try:
        if json.loads(_pid_file().read_text(encoding="utf-8")).get("pid") == pid:
            _pid_file().unlink()
    except (OSError, ValueError, AttributeError):
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_client.py -q`
Expected: `19 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/client.py tests/test_client.py
git commit -m "Add SubprocessEngine: start, load, ocr_page, cancel, stop" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Stale worker sweep and the installed engine

**Files:**
- Modify: `owlocr/engine/client.py` (append)
- Test: `tests/test_client_install.py`

**Interfaces:**
- Consumes: `SubprocessEngine`, `_pid_file()`, `lifetime._process_create_time`, `lifetime._terminate`, `paths.engine_dir()`, `paths.engine_python()`, `paths.worker_dir()`, `paths.model_dir()`, `paths.logs_dir()`.
- Produces (contract): `sweep_stale_worker() -> None`, `default_engine() -> SubprocessEngine` (raises `EngineError("not_installed")`). `install.json` keys read by plan A (plan D writes them): `engine_id` (default `"unlimited_ocr"`), `device` (default `"cuda"`), `dtype` (default `bfloat16` on cuda, `float32` on cpu), and optional overrides `python`, `worker_script`, `model_dir`, `env` (dict). The engine's log file is `logs_dir()/engine.log`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_client_install.py`:

```python
"""default_engine() and sweep_stale_worker()."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from owlocr import paths
from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine, default_engine, sweep_stale_worker
from owlocr.engine.protocol import EngineError
from tests.conftest import FAKE_WORKER


def write_install(data: dict) -> None:
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps(data))


def test_not_installed_without_install_json():
    with pytest.raises(EngineError) as e:
        default_engine()
    assert e.value.kind == "not_installed"


def test_not_installed_when_python_missing():
    write_install({"engine_id": "unlimited_ocr", "device": "cuda"})
    with pytest.raises(EngineError) as e:
        default_engine()
    assert e.value.kind == "not_installed"


def test_standard_locations(owl_env):
    python = paths.engine_python()
    worker = paths.worker_dir() / "owl_worker.py"
    for f in (python, worker):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    write_install({"engine_id": "unlimited_ocr", "device": "cuda", "dtype": "bfloat16"})
    engine = default_engine()
    assert isinstance(engine, SubprocessEngine)
    assert engine.python == python and engine.worker_script == worker
    assert engine.model_dir == paths.model_dir("unlimited_ocr")
    assert (engine.device, engine.dtype) == ("cuda", "bfloat16")
    assert engine.log_file == paths.logs_dir() / "engine.log"


def test_overrides_and_cpu_default_dtype(tmp_path):
    write_install({"python": sys.executable, "worker_script": str(FAKE_WORKER),
                   "model_dir": str(tmp_path / "m"), "device": "cpu", "env": {"FAKE_WORKER": "slow"}})
    engine = default_engine()
    assert engine.python == Path(sys.executable)
    assert engine.worker_script == FAKE_WORKER
    assert engine.model_dir == tmp_path / "m"
    assert (engine.device, engine.dtype) == ("cpu", "float32")
    assert engine.env == {"FAKE_WORKER": "slow"}
    try:
        engine.load()
        assert engine.loaded
    finally:
        engine.stop()


def test_sweep_terminates_the_recorded_worker():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        paths.atomic_write_text(paths.engine_dir() / "worker.pid",
                                json.dumps({"pid": p.pid, "created": lifetime._process_create_time(p.pid)}))
        sweep_stale_worker()
        assert p.wait(timeout=5) is not None
        assert not (paths.engine_dir() / "worker.pid").exists()
    finally:
        p.kill()


def test_sweep_spares_a_process_that_reused_the_pid():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        paths.atomic_write_text(paths.engine_dir() / "worker.pid", json.dumps({"pid": p.pid, "created": 12345}))
        sweep_stale_worker()
        time.sleep(0.3)
        assert p.poll() is None
        assert not (paths.engine_dir() / "worker.pid").exists()
    finally:
        p.kill()


def test_sweep_without_or_with_broken_file():
    sweep_stale_worker()
    paths.atomic_write_text(paths.engine_dir() / "worker.pid", "garbage")
    sweep_stale_worker()
    assert not (paths.engine_dir() / "worker.pid").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_client_install.py -q`
Expected: FAIL — `ImportError: cannot import name 'default_engine' from 'owlocr.engine.client'`.

- [ ] **Step 3: Write minimal implementation**

Append to the end of `owlocr/engine/client.py`:

```python
# ---- stale worker sweep and the installed engine (design 5.6, 6.3) ------------------------

def sweep_stale_worker() -> None:
    """Terminate a worker left over from an earlier run of the app, if it is still alive."""
    path = _pid_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid, created = int(data["pid"]), data.get("created")
    except (OSError, ValueError, KeyError, TypeError):
        path.unlink(missing_ok=True)
        return
    # The creation time proves it is the same process and not a new one that reused the pid.
    if created is not None and lifetime._process_create_time(pid) == created:
        lifetime._terminate(pid)
    path.unlink(missing_ok=True)


# ---- the engine as installed ----------------------------------------------------------------

def default_engine() -> SubprocessEngine:
    """Engine described by <engine dir>/install.json (written by plan D's bootstrap, or by
    scripts/dev_engine.py in development). Optional keys python, worker_script, model_dir and
    env override the standard locations."""
    install = paths.engine_dir() / "install.json"
    try:
        data = json.loads(install.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise EngineError("not_installed", f"{install} is missing or unreadable") from e
    if not isinstance(data, dict):
        raise EngineError("not_installed", f"{install} is not a JSON object")
    engine_id = str(data.get("engine_id") or "unlimited_ocr")
    python = Path(data.get("python") or paths.engine_python())
    worker = Path(data.get("worker_script") or paths.worker_dir() / "owl_worker.py")
    model = Path(data.get("model_dir") or paths.model_dir(engine_id))
    for required in (python, worker):
        if not required.is_file():
            raise EngineError("not_installed", f"missing {required}")
    device = str(data.get("device") or "cuda")
    dtype = str(data.get("dtype") or ("bfloat16" if device == "cuda" else "float32"))
    engine = SubprocessEngine(python, worker, model, device, dtype,
                              paths.logs_dir() / "engine.log", env=data.get("env") or None)
    engine.engine_id = engine_id
    return engine
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_client.py tests/test_client_install.py -q`
Expected: `26 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/client.py tests/test_client_install.py
git commit -m "Add stale worker sweep and default_engine from install.json" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Engine lifetime tests (design 5.6)

**Files:**
- Create: `tests/lifetime_helper.py`
- Test: `tests/test_lifetime.py`

**Interfaces:**
- Consumes: `SubprocessEngine.start()`, `lifetime.process_alive`, `lifetime._terminate`, `tests/fake_worker.py` flags `ignore_stdin_eof`, `ignore_shutdown`.
- Produces: `python tests/lifetime_helper.py <log file>` prints the worker's pid and waits to be killed.

The three tests cover safeguards 1 to 3 of design 5.6: the helper stands in for the app and is killed with TerminateProcess (no clean-up code runs); the worker must be gone within 5 s. The stdin-EOF test and the watchdog test drive the fake worker directly; in the watchdog test the worker ignores stdin EOF and its "parent" is a separate process, so only the watchdog can end it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifetime.py`:

```python
"""Design 5.6: the engine worker never outlives the app."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from owlocr.engine import lifetime
from tests.conftest import FAKE_WORKER, REPO

HELPER = REPO / "tests" / "lifetime_helper.py"


def _gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not lifetime.process_alive(pid):
            return True
        time.sleep(0.05)
    return False


def _start_helper(tmp_path: Path, flags: str) -> tuple[subprocess.Popen, int]:
    env = dict(os.environ, FAKE_WORKER=flags)
    helper = subprocess.Popen([sys.executable, str(HELPER), str(tmp_path / "engine.log")],
                              stdout=subprocess.PIPE, env=env)
    worker_pid = int(helper.stdout.readline())
    assert lifetime.process_alive(worker_pid)
    return helper, worker_pid


def test_worker_dies_when_the_app_is_killed(tmp_path):
    helper, worker_pid = _start_helper(tmp_path, "ignore_stdin_eof,ignore_shutdown")
    try:
        helper.kill()                        # TerminateProcess: no clean-up code runs in the app
        assert _gone_within(worker_pid, 5)
    finally:
        helper.kill()
        lifetime._terminate(worker_pid)


def test_worker_exits_on_stdin_eof(tmp_path):
    env = dict(os.environ, FAKE_WORKER="")
    worker = subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(os.getpid())],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        assert b'"ready"' in worker.stdout.readline()
        worker.stdin.close()
        assert worker.wait(timeout=5) == 0
    finally:
        worker.kill()


def test_parent_watchdog_ends_the_worker(tmp_path):
    # The "parent" is a separate short-lived process that is not in any job with the worker,
    # and the worker ignores stdin EOF, so only the watchdog can end it.
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    env = dict(os.environ, FAKE_WORKER="ignore_stdin_eof")
    worker = subprocess.Popen([sys.executable, str(FAKE_WORKER), "--parent-pid", str(parent.pid)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        worker_pid = int(json.loads(worker.stdout.readline())["pid"])
        parent.kill()
        parent.wait(timeout=5)
        assert _gone_within(worker_pid, 5)
    finally:
        worker.kill()
        parent.kill()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_lifetime.py -q`
Expected: FAIL — `test_worker_dies_when_the_app_is_killed` with `ValueError: invalid literal for int() with base 10: b''` (the helper script does not exist yet); the other two tests pass.

- [ ] **Step 3: Write minimal implementation**

Create `tests/lifetime_helper.py`:

```python
"""Stand-in for the app in the lifetime tests: starts the fake worker through SubprocessEngine,
prints the worker's pid, then waits to be killed.

    python tests/lifetime_helper.py <log file>
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from owlocr.engine.client import SubprocessEngine  # noqa: E402


def main() -> None:
    log_file = Path(sys.argv[1])
    engine = SubprocessEngine(python=Path(sys.executable), worker_script=REPO / "tests" / "fake_worker.py",
                              model_dir=log_file.parent / "model", device="cpu", dtype="float32",
                              log_file=log_file)
    info = engine.start()
    print(info.pid, flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_lifetime.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add tests/lifetime_helper.py tests/test_lifetime.py
git commit -m "Test that the worker never outlives the app" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Model store: readiness and verification

**Files:**
- Create: `owlocr/engine/store.py` (Task 14 and 15 append to it), `tests/store_fakes.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `paths.model_dir()`, `registry.get()`, `registry.EngineSpec`.
- Produces (contract): `manifest_path(engine_id: str = "unlimited_ocr") -> Path`, `is_ready(engine_id: str = "unlimited_ocr", deep: bool = False) -> bool`, `verify(engine_id: str = "unlimited_ocr") -> dict[str, str]`, `class StoreError(RuntimeError)`. Manifest format (the one `spike/download_model.py` wrote, so the existing model is ready): `{"repo": str, "commit": <revision>, "files": {path: {"size": int, "sha256": str|None, "git_sha1": str|None}}}`; plan A also writes `"engine_id"`. `tests/store_fakes.py` provides `FILES`, `LFS`, `SPEC`, `git_blob_sha1()`, `manifest_entries()`, `FakeRemote`.

- [ ] **Step 1: Write the failing test**

Create `tests/store_fakes.py`:

```python
"""A fake Hugging Face / ModelScope server for the model store tests (no network)."""
import dataclasses
import hashlib
import io
import json
import urllib.error
import urllib.parse

from owlocr.engine import registry

FILES = {
    "config.json": b'{"model_type": "unlimited-ocr"}',
    "modeling_unlimitedocr.py": "# model code, žluťoučký\n".encode("utf-8") * 50,
    "model-00001-of-000001.safetensors": bytes(range(256)) * 400,
}
LFS = {"model-00001-of-000001.safetensors"}
SPEC = dataclasses.replace(
    registry.UNLIMITED_OCR,
    weights_sha256=hashlib.sha256(FILES["model-00001-of-000001.safetensors"]).hexdigest())


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def manifest_entries() -> dict:
    return {
        path: {"size": len(data),
               "sha256": hashlib.sha256(data).hexdigest() if path in LFS else None,
               "git_sha1": None if path in LFS else git_blob_sha1(data)}
        for path, data in FILES.items()
    }


class _Response(io.BytesIO):
    def __init__(self, status: int, body: bytes, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class FakeRemote:
    def __init__(self):
        self.requests: list[tuple[str, int]] = []
        self.down_hosts: set[str] = set()
        self.ignore_range = False
        self.corrupt: set[tuple[str, str]] = set()      # (host, path) serving wrong bytes

    def tree(self) -> list[dict]:
        entries = [{"type": "directory", "oid": "d0", "size": 0, "path": "assets"},
                   {"type": "file", "oid": "a1", "size": 3, "path": "assets/logo.png"},
                   {"type": "file", "oid": "a2", "size": 5, "path": ".gitattributes"}]
        for path, data in FILES.items():
            entry = {"type": "file", "path": path, "size": len(data), "oid": git_blob_sha1(data)}
            if path in LFS:
                entry["oid"] = "pointer-blob"
                entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest(), "size": len(data), "pointerSize": 131}
            entries.append(entry)
        return entries

    def open(self, url: str, start: int = 0):
        self.requests.append((url, start))
        host = urllib.parse.urlsplit(url).hostname
        if host in self.down_hosts:
            raise urllib.error.URLError(f"{host} is down")
        if "/api/models/" in url:
            return _Response(200, json.dumps(self.tree()).encode("utf-8"))
        path = urllib.parse.unquote(url.split("/resolve/", 1)[1].split("/", 1)[1])
        data = FILES[path]
        if (host, path) in self.corrupt:
            data = b"X" * len(data)
        if start and not self.ignore_range:
            return _Response(206, data[start:])
        return _Response(200, data)

    def file_requests(self, name: str) -> list[tuple[str, int]]:
        return [(u, s) for u, s in self.requests if u.endswith("/" + name)]
```

Create `tests/test_store.py`:

```python
"""Model store: readiness check and verification of files already on disk."""
import json

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, manifest_entries


def install_model(commit: str = SPEC.revision) -> None:
    folder = paths.model_dir("unlimited_ocr")
    folder.mkdir(parents=True, exist_ok=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    (folder / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": commit, "files": manifest_entries()}), encoding="utf-8")


def test_manifest_path(owl_env):
    assert store.manifest_path() == owl_env["home"] / "models" / "unlimited_ocr" / "manifest.json"


def test_not_ready_without_manifest():
    assert store.is_ready() is False
    assert store.verify() == {"manifest.json": "missing"}


def test_ready_and_verified():
    install_model()
    assert store.is_ready() is True
    assert store.is_ready(deep=True) is True
    assert store.verify() == {}


def test_wrong_revision_is_not_ready():
    install_model(commit="0" * 40)
    assert store.is_ready() is False
    assert "manifest.json" in store.verify()


def test_missing_or_truncated_file_is_not_ready():
    install_model()
    folder = paths.model_dir()
    (folder / "config.json").unlink()
    assert store.is_ready() is False
    assert store.verify() == {"config.json": "missing"}
    install_model()
    (folder / "model-00001-of-000001.safetensors").write_bytes(b"short")
    assert store.is_ready() is False
    assert store.verify()["model-00001-of-000001.safetensors"].startswith("size ")


def test_same_size_corruption_needs_deep_check():
    install_model()
    folder = paths.model_dir()
    weights = folder / "model-00001-of-000001.safetensors"
    weights.write_bytes(b"\0" * weights.stat().st_size)
    code = folder / "modeling_unlimitedocr.py"
    code.write_bytes(b"#" * code.stat().st_size)
    assert store.is_ready() is True                 # fast check: sizes only
    assert store.is_ready(deep=True) is False
    assert store.verify() == {"model-00001-of-000001.safetensors": "sha256 mismatch",
                              "modeling_unlimitedocr.py": "git sha1 mismatch"}


def test_spike_manifest_format_is_accepted():
    """The owner's existing download (spike/download_model.py) has no engine_id key."""
    install_model()
    data = json.loads(store.manifest_path().read_text(encoding="utf-8"))
    assert "engine_id" not in data
    assert store.is_ready()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_store.py -q`
Expected: FAIL — `ImportError: cannot import name 'store' from 'owlocr.engine'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/engine/store.py`:

```python
"""Model files on disk: download once, verify, remember (design 6.3).

manifest.json in the model folder is written LAST, after every file has been verified. It holds
the pinned revision and the size and hash of every file. On later starts is_ready() only checks
that the files exist with the recorded sizes: no hashing, no network.
The manifest format is the one the spike wrote ({"repo", "commit", "files"}), so the model the
owner already downloaded with spike/download_model.py is recognised as ready.
"""
import fnmatch
import hashlib
import json
import shutil
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from owlocr import __version__, paths
from owlocr.engine import registry
from owlocr.engine.registry import EngineSpec

_HF_TREE = "https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
_HF_FILE = "https://huggingface.co/{repo}/resolve/{revision}/{path}"
_MODELSCOPE_FILE = "https://www.modelscope.cn/models/{repo}/resolve/master/{path}"
_CHUNK = 8 << 20
_TIMEOUT_S = 60


class StoreError(RuntimeError):
    pass


def manifest_path(engine_id: str = "unlimited_ocr") -> Path:
    return paths.model_dir(engine_id) / "manifest.json"


def _read_manifest(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    return data


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    """Hash the way git does, so small (non-LFS) files can be checked against the blob id."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % path.stat().st_size)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_file(path: Path, info: dict, deep: bool) -> str | None:
    """None when the file is good, else a short reason."""
    if not path.is_file():
        return "missing"
    size = path.stat().st_size
    if size != info["size"]:
        return f"size {size} != {info['size']}"
    if deep:
        if info.get("sha256"):
            if _sha256(path) != info["sha256"]:
                return "sha256 mismatch"
        elif info.get("git_sha1"):
            if _git_blob_sha1(path) != info["git_sha1"]:
                return "git sha1 mismatch"
    return None


def is_ready(engine_id: str = "unlimited_ocr", deep: bool = False) -> bool:
    spec = registry.get(engine_id)
    folder = paths.model_dir(engine_id)
    manifest = _read_manifest(folder)
    if manifest is None or manifest.get("commit") != spec.revision:
        return False
    return all(_check_file(folder / rel, info, deep) is None for rel, info in manifest["files"].items())


def verify(engine_id: str = "unlimited_ocr") -> dict[str, str]:
    spec = registry.get(engine_id)
    folder = paths.model_dir(engine_id)
    manifest = _read_manifest(folder)
    if manifest is None:
        return {"manifest.json": "missing"}
    if manifest.get("commit") != spec.revision:
        return {"manifest.json": f"revision {manifest.get('commit')} != {spec.revision}"}
    problems = {}
    for rel, info in manifest["files"].items():
        reason = _check_file(folder / rel, info, deep=True)
        if reason:
            problems[rel] = reason
    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_store.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/store.py tests/store_fakes.py tests/test_store.py
git commit -m "Add model store readiness check and verification" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Model store: resumable download

**Files:**
- Modify: `owlocr/engine/store.py` (append)
- Test: `tests/test_store_download.py`

**Interfaces:**
- Consumes: Task 13 helpers `_read_manifest`, `_check_file`, `StoreError`; `EngineSpec.repo`, `.revision`, `.ignore`, `.modelscope_repo`.
- Produces (contract): `fetch_remote_manifest(spec: EngineSpec) -> dict[str, dict]`, `download(spec: EngineSpec, on_progress: Callable[[int, int], None] | None = None, cancel: threading.Event | None = None) -> None`. `on_progress(done_bytes, total_bytes)`. Cancel raises `StoreError("cancelled")`. Sources in order: `https://huggingface.co/<repo>/resolve/<revision>/<path>` then `https://www.modelscope.cn/models/<modelscope_repo>/resolve/master/<path>`; plain HTTPS with Range via `urllib` (no Xet). Private: `_open(url, start=0)` (the only network call; tests replace it), `_write_manifest(folder, spec, files)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store_download.py`:

```python
"""Model store: remote file list and resumable download against a fake server."""
import threading

import pytest

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, FakeRemote, manifest_entries

WEIGHTS = "model-00001-of-000001.safetensors"


@pytest.fixture
def remote(monkeypatch):
    fake = FakeRemote()
    monkeypatch.setattr(store, "_open", fake.open)
    return fake


def test_fetch_remote_manifest(remote):
    files = store.fetch_remote_manifest(SPEC)
    assert files == manifest_entries()
    assert "assets/logo.png" not in files and ".gitattributes" not in files
    assert remote.requests[0][0] == (
        "https://huggingface.co/api/models/baidu/Unlimited-OCR/tree/"
        "07dea832e22aefee32ad281d4b80551282e1c168?recursive=true")


def test_fetch_remote_manifest_offline(remote):
    remote.down_hosts.add("huggingface.co")
    with pytest.raises(store.StoreError):
        store.fetch_remote_manifest(SPEC)


def test_download_everything(remote):
    progress = []
    store.download(SPEC, on_progress=lambda done, total: progress.append((done, total)))
    folder = paths.model_dir()
    for rel, data in FILES.items():
        assert (folder / rel).read_bytes() == data
    total = sum(len(d) for d in FILES.values())
    assert progress[-1] == (total, total)
    assert store.is_ready(deep=True)
    assert not list(folder.glob("*.part"))
    url, start = remote.file_requests(WEIGHTS)[0]
    assert url == f"https://huggingface.co/baidu/Unlimited-OCR/resolve/{SPEC.revision}/{WEIGHTS}"


def test_second_download_does_nothing(remote):
    store.download(SPEC)
    remote.requests.clear()
    store.download(SPEC)
    assert remote.requests == []


def test_resume_partial_file(remote):
    folder = paths.model_dir()
    folder.mkdir(parents=True)
    (folder / (WEIGHTS + ".part")).write_bytes(FILES[WEIGHTS][:1000])
    progress = []
    store.download(SPEC, on_progress=lambda done, total: progress.append(done))
    assert remote.file_requests(WEIGHTS) == [(remote.file_requests(WEIGHTS)[0][0], 1000)]
    assert (folder / WEIGHTS).read_bytes() == FILES[WEIGHTS]
    assert progress[-1] == sum(len(d) for d in FILES.values())


def test_server_that_ignores_range(remote):
    remote.ignore_range = True
    folder = paths.model_dir()
    folder.mkdir(parents=True)
    (folder / (WEIGHTS + ".part")).write_bytes(FILES[WEIGHTS][:1000])
    store.download(SPEC)
    assert (folder / WEIGHTS).read_bytes() == FILES[WEIGHTS]


def test_falls_back_to_modelscope(remote):
    remote.corrupt.add(("huggingface.co", WEIGHTS))
    store.download(SPEC)
    urls = [u for u, _ in remote.file_requests(WEIGHTS)]
    assert urls[1] == f"https://www.modelscope.cn/models/PaddlePaddle/Unlimited-OCR/resolve/master/{WEIGHTS}"
    assert store.is_ready(deep=True)


def test_every_source_bad(remote):
    remote.corrupt.add(("huggingface.co", WEIGHTS))
    remote.corrupt.add(("www.modelscope.cn", WEIGHTS))
    with pytest.raises(store.StoreError):
        store.download(SPEC)
    assert not store.manifest_path().exists()
    assert not (paths.model_dir() / WEIGHTS).exists()


def test_cancel(remote):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(store.StoreError, match="cancelled"):
        store.download(SPEC, cancel=cancel)
    assert not store.manifest_path().exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_store_download.py -q`
Expected: FAIL — `AttributeError: <module 'owlocr.engine.store' ...> has no attribute '_open'`.

- [ ] **Step 3: Write minimal implementation**

Append to the end of `owlocr/engine/store.py`:

```python
# ---- network ----------------------------------------------------------------------------------

def _open(url: str, start: int = 0):
    """GET `url`, from byte `start` on. Returns a response with .status, .headers, .read(n)."""
    headers = {"User-Agent": f"OwlOCR/{__version__}", "Accept-Encoding": "identity"}
    if start:
        headers["Range"] = f"bytes={start}-"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=_TIMEOUT_S)


def _ignored(path: str, spec: EngineSpec) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in spec.ignore)


def _next_link(link_header: str | None) -> str | None:
    for part in (link_header or "").split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1: part.find(">")]
    return None


def fetch_remote_manifest(spec: EngineSpec) -> dict[str, dict]:
    """path -> {size, sha256, git_sha1} for every file of the pinned revision, minus spec.ignore."""
    files: dict[str, dict] = {}
    url = _HF_TREE.format(repo=spec.repo, revision=spec.revision)
    try:
        while url:
            with _open(url) as response:
                entries = json.loads(response.read().decode("utf-8"))
                url = _next_link(response.headers.get("Link"))
            for entry in entries:
                if entry.get("type") != "file" or _ignored(entry["path"], spec):
                    continue
                lfs = entry.get("lfs")
                files[entry["path"]] = {
                    "size": int(lfs["size"] if lfs else entry["size"]),
                    "sha256": lfs["oid"] if lfs else None,
                    "git_sha1": None if lfs else entry["oid"],
                }
    except (OSError, ValueError, KeyError) as e:
        raise StoreError(f"cannot read the file list of {spec.repo}: {e}") from e
    if not files:
        raise StoreError(f"{spec.repo} at {spec.revision} lists no files")
    return files


def _download_file(urls: list[str], dest: Path, info: dict, on_bytes: Callable[[int], None],
                   cancel: threading.Event | None) -> None:
    """Fetch one file into dest via dest.part, resuming, trying each url in turn."""
    part = dest.with_name(dest.name + ".part")
    if part.exists():
        on_bytes(part.stat().st_size)          # bytes fetched by an earlier, interrupted run
    last_error: Exception | None = None
    for url in urls:
        try:
            have = part.stat().st_size if part.exists() else 0
            if have > info["size"]:
                on_bytes(-have)
                part.unlink()
                have = 0
            if have < info["size"]:
                with _open(url, have) as response:
                    if have and response.status != 206:     # server ignored Range: start again
                        on_bytes(-have)
                        have = 0
                    with open(part, "ab" if have else "wb") as fh:
                        while True:
                            if cancel is not None and cancel.is_set():
                                raise StoreError("cancelled")
                            chunk = response.read(_CHUNK)
                            if not chunk:
                                break
                            fh.write(chunk)
                            on_bytes(len(chunk))
            reason = _check_file(part, info, deep=True)
            if reason is None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                part.replace(dest)
                return
            on_bytes(-part.stat().st_size)
            part.unlink()
            last_error = StoreError(f"{dest.name}: {reason} (from {url})")
        except StoreError as e:
            if str(e) == "cancelled":
                raise
            last_error = e
        except OSError as e:                     # includes urllib.error.URLError and HTTPError
            last_error = e
    raise StoreError(f"cannot download {dest.name}: {last_error}")


def download(spec: EngineSpec, on_progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None) -> None:
    """Download and verify every file of the pinned revision into model_dir(spec.engine_id).
    Resumable: finished files are kept, partial files continue. manifest.json is written last.
    Raises StoreError("cancelled") when `cancel` is set."""
    if is_ready(spec.engine_id):
        return
    folder = paths.model_dir(spec.engine_id)
    folder.mkdir(parents=True, exist_ok=True)
    files = fetch_remote_manifest(spec)
    total = sum(info["size"] for info in files.values())
    done = 0

    def on_bytes(n: int) -> None:
        nonlocal done
        done += n
        if on_progress is not None:
            on_progress(done, total)

    for rel, info in files.items():
        dest = folder / rel
        if _check_file(dest, info, deep=True) is None:
            on_bytes(info["size"])
            continue
        dest.unlink(missing_ok=True)
        quoted = urllib.parse.quote(rel)
        urls = [_HF_FILE.format(repo=spec.repo, revision=spec.revision, path=quoted),
                _MODELSCOPE_FILE.format(repo=spec.modelscope_repo, path=quoted)]
        _download_file(urls, dest, info, on_bytes, cancel)
    _write_manifest(folder, spec, files)


def _write_manifest(folder: Path, spec: EngineSpec, files: dict[str, dict]) -> None:
    paths.atomic_write_text(folder / "manifest.json", json.dumps(
        {"repo": spec.repo, "commit": spec.revision, "engine_id": spec.engine_id, "files": files}, indent=1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_store.py tests/test_store_download.py -q`
Expected: `16 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/store.py tests/test_store_download.py
git commit -m "Add resumable, verified model download with ModelScope fallback" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Model store: adopt an existing download

**Files:**
- Modify: `owlocr/engine/store.py` (append)
- Test: `tests/test_store_adopt.py`

**Interfaces:**
- Consumes: `fetch_remote_manifest`, `_read_manifest`, `_check_file`, `_write_manifest`, `EngineSpec.weights_sha256`, `paths.model_dir()`.
- Produces (contract): `adopt(folder: Path, spec: EngineSpec, move: bool = True) -> None`. Accepts the model folder itself, a folder containing `<engine_id>`, or one containing `models\<engine_id>`. Uses the folder's own manifest when its revision matches, else the remote list; the weights must match `spec.weights_sha256`; every file is hashed; files are then moved (or copied) into `model_dir()` and the manifest is written last. Refuses a non-empty different target.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store_adopt.py`:

```python
"""Model store: adopting a model folder downloaded earlier ("I already have the engine")."""
import dataclasses
import json

import pytest

from owlocr import paths
from owlocr.engine import store
from tests.store_fakes import FILES, SPEC, FakeRemote, manifest_entries


def make_download(folder, with_manifest: bool = True):
    folder.mkdir(parents=True, exist_ok=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    if with_manifest:
        (folder / "manifest.json").write_text(json.dumps(
            {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")
    return folder


def test_adopt_moves_the_model_folder(tmp_path):
    source = make_download(tmp_path / "old" / "unlimited_ocr")
    store.adopt(source, SPEC)
    assert store.is_ready(deep=True)
    assert not (source / "config.json").exists()


def test_adopt_parent_folder_with_models_subfolder(tmp_path):
    make_download(tmp_path / "old_engine" / "models" / "unlimited_ocr")
    store.adopt(tmp_path / "old_engine", SPEC, move=False)
    assert store.is_ready(deep=True)
    assert (tmp_path / "old_engine" / "models" / "unlimited_ocr" / "config.json").exists()


def test_adopt_without_manifest_uses_the_remote_list(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_open", FakeRemote().open)
    source = make_download(tmp_path / "unlimited_ocr", with_manifest=False)
    store.adopt(source, SPEC)
    assert store.is_ready(deep=True)


def test_adopt_rejects_other_weights(tmp_path):
    source = make_download(tmp_path / "unlimited_ocr")
    other = dataclasses.replace(SPEC, weights_sha256="0" * 64)
    with pytest.raises(store.StoreError, match="weights"):
        store.adopt(source, other)
    assert not store.is_ready()


def test_adopt_rejects_corrupt_files(tmp_path):
    source = make_download(tmp_path / "unlimited_ocr")
    (source / "config.json").write_bytes(b"{" + b" " * (len(FILES["config.json"]) - 1))
    with pytest.raises(store.StoreError, match="config.json"):
        store.adopt(source, SPEC)
    assert (source / "config.json").exists()


def test_adopt_folder_without_model(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(store.StoreError):
        store.adopt(tmp_path / "empty", SPEC)


def test_adopt_in_place(tmp_path):
    make_download(paths.model_dir(), with_manifest=False)
    (paths.model_dir() / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")
    store.adopt(paths.model_dir(), SPEC)
    assert store.is_ready(deep=True)


def test_adopt_refuses_to_mix_with_existing_files(tmp_path):
    paths.model_dir().mkdir(parents=True)
    (paths.model_dir() / "stray.txt").write_text("x")
    source = make_download(tmp_path / "unlimited_ocr")
    with pytest.raises(store.StoreError, match="already contains"):
        store.adopt(source, SPEC)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_store_adopt.py -q`
Expected: FAIL — `AttributeError: module 'owlocr.engine.store' has no attribute 'adopt'`.

- [ ] **Step 3: Write minimal implementation**

Append to the end of `owlocr/engine/store.py`:

```python
# ---- adopt an existing download ----------------------------------------------------------

def _find_model_folder(folder: Path, spec: EngineSpec) -> Path:
    for candidate in (folder, folder / spec.engine_id, folder / "models" / spec.engine_id):
        if (candidate / "config.json").is_file():
            return candidate
    raise StoreError(f"no {spec.engine_id} model found in {folder}")


def adopt(folder: Path, spec: EngineSpec, move: bool = True) -> None:
    """Take over a model folder downloaded earlier (design 6.3 point 7). `folder` may be the model
    folder itself, contain it, or contain models/<engine_id>. Every file is verified by hash; the
    weights must match the pinned sha256. The files are then moved (or copied) into the data root."""
    source = _find_model_folder(Path(folder), spec)
    stored = _read_manifest(source)
    if stored is not None and stored.get("commit") == spec.revision:
        files = stored["files"]
    else:
        files = fetch_remote_manifest(spec)
    weights = [rel for rel, info in files.items() if rel.endswith(".safetensors")]
    if not weights or any(files[rel].get("sha256") != spec.weights_sha256 for rel in weights):
        raise StoreError("the weights listed for this folder are not the pinned ones")
    problems = {rel: reason for rel, info in files.items()
                if (reason := _check_file(source / rel, info, deep=True))}
    if problems:
        raise StoreError("files do not verify: " + ", ".join(f"{k} ({v})" for k, v in sorted(problems.items())))
    target = paths.model_dir(spec.engine_id)
    if source.resolve() != target.resolve():
        if target.exists() and any(target.iterdir()):
            raise StoreError(f"{target} already contains files; remove the engine first")
        target.mkdir(parents=True, exist_ok=True)
        for rel in files:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(source / rel), str(dest))
            else:
                shutil.copy2(source / rel, dest)
    _write_manifest(target, spec, files)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_store.py tests/test_store_download.py tests/test_store_adopt.py -q`
Expected: `24 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/engine/store.py tests/test_store_adopt.py
git commit -m "Add adopting an existing model download" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: The real engine worker

**Files:**
- Create: `worker/owl_worker.py`, `worker/requirements-engine.txt`
- Test: `tests/test_worker_unit.py`, `tests/test_worker_engine.py`

**Interfaces:**
- Consumes: nothing from `owlocr` (the worker runs in the engine's own Python). Protocol of design 5.4.
- Produces (contract): `python owl_worker.py --parent-pid <pid>`. Module-level names used by the tests: `PROMPT`, `MODES`, `NO_REPEAT_NGRAM_SIZE`, `NGRAM_WINDOW`, `PROGRESS_INTERVAL_S`, `send()`, `Control` (`begin`, `end`, `cancel`, `should_stop`), `CONTROL`, `Engine` (`load`, `_wrap_generate`, `unload`, `ocr`), `handle(engine, message)`, `_is_out_of_memory()`, `_check_image()`, `detach_stdin()`, `reader(stream)`, `watchdog(parent_pid)`, `main()`.

Facts this worker is built on (verified on this PC without the GPU):
- `infer()` only accepts `max_length` (prompt plus output). The wrapper around `model.generate` reads `kwargs["input_ids"].shape[1]` (the prefix), sets `max_length = prefix + max_new_tokens`, and adds a `StoppingCriteria` subclass to `stopping_criteria`; transformers 4.57.1 merges it with its own criteria and calls it after every token with the whole sequence. The criteria return a bool tensor of shape `(batch,)`.
- **stdin deadlock:** a thread blocked in `ReadFile` on the stdin pipe makes every `GetFileType()` on that handle wait; each DLL with its own C runtime calls it while loading, so `import torch` hung forever with a reader thread on the real stdin. `detach_stdin()` moves the pipe to a private file descriptor and points the standard input handle at NUL before the reader starts.
- `CUDA_VISIBLE_DEVICES=""` did not hide the GPU on this PC (torch reported CUDA available, then `get_device_name(0)` failed); `-1` hides it. The worker also treats a failing `get_device_name` as "no CUDA".
- The model code prints to stdout (for example `directly resize`); `main()` keeps the real stdout for the protocol and points `sys.stdout` at stderr, which the app writes to `engine.log`.

`tests/test_worker_engine.py` starts the real worker with the engine Python (`OWLOCR_TEST_ENGINE_PYTHON`, else `spike\.venv\Scripts\python.exe`), hides the GPU with `CUDA_VISIBLE_DEVICES=-1`, never loads the OCR model, and tests the `generate` wrapper on a random one-layer GPT-2. It is skipped when that Python does not exist.

- [ ] **Step 1: Write the failing test**

Create `tests/test_worker_unit.py`:

```python
"""worker/owl_worker.py logic that needs neither torch nor the model."""
import importlib.util
import os
import re

import pytest
from PIL import Image

from tests.conftest import REPO


@pytest.fixture
def worker(monkeypatch):
    saved_env = dict(os.environ)             # the worker module sets HF_* defaults on import
    spec = importlib.util.spec_from_file_location("owl_worker_under_test", REPO / "worker" / "owl_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sent = []
    monkeypatch.setattr(module, "send", sent.append)
    module.sent = sent
    yield module
    os.environ.clear()
    os.environ.update(saved_env)


def test_import_does_not_redirect_stdout(worker):
    import sys
    assert worker._proto is None
    assert sys.stdout is not sys.stderr


def test_modes_and_guard_values(worker):
    assert worker.PROMPT == "<image>document parsing."
    assert worker.MODES["quality"] == {"base_size": 1024, "image_size": 640, "crop_mode": True}
    assert worker.MODES["fast"] == {"base_size": 1024, "image_size": 1024, "crop_mode": False}
    assert (worker.NO_REPEAT_NGRAM_SIZE, worker.NGRAM_WINDOW) == (35, 128)


def test_cancel_stops_generation(worker):
    control = worker.Control()
    control.begin("7", time_limit_s=300)
    control.prefix_tokens = 100
    assert control.should_stop(101) is False
    control.cancel("other")
    assert control.should_stop(102) is False
    control.cancel("7")
    assert control.should_stop(103) is True
    assert control.cancelled and not control.timed_out


def test_cancel_before_the_page_starts(worker):
    control = worker.Control()
    control.cancel("8")
    control.begin("8", time_limit_s=300)
    assert control.should_stop(1) is True and control.cancelled


def test_shutdown_cancel_hits_whatever_runs(worker):
    control = worker.Control()
    control.begin("9", time_limit_s=300)
    control.cancel(None)
    assert control.should_stop(1) is True


@pytest.fixture
def clock(worker, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(worker.time, "monotonic", lambda: now[0])
    return now


def test_time_limit(worker, clock):
    control = worker.Control()
    control.begin("1", time_limit_s=300)
    clock[0] += 299
    assert control.should_stop(1) is False
    clock[0] += 2
    assert control.should_stop(2) is True
    assert control.timed_out and not control.cancelled


def test_progress_is_throttled(worker, clock):
    control = worker.Control()
    control.begin("3", time_limit_s=300)
    control.prefix_tokens = 1000
    clock[0] += 0.2
    control.should_stop(1001)                 # too early: no event yet
    clock[0] += 0.4
    control.should_stop(1010)                 # 0.6 s after the start: event
    clock[0] += 0.1
    control.should_stop(1011)                 # 0.1 s after the last event: none
    clock[0] += 0.5
    control.should_stop(1020)
    assert worker.sent == [{"event": "progress", "id": "3", "tokens": 10},
                           {"event": "progress", "id": "3", "tokens": 20}]


def test_out_of_memory_detection(worker):
    assert worker._is_out_of_memory(MemoryError())
    assert worker._is_out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    assert worker._is_out_of_memory(RuntimeError("DefaultCPUAllocator: can't allocate memory"))
    assert not worker._is_out_of_memory(ValueError("out of memory"))
    assert not worker._is_out_of_memory(RuntimeError("shape mismatch"))


def test_check_image(worker, tmp_path):
    good = tmp_path / "good.png"
    Image.new("RGB", (10, 10), "white").save(good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert worker._check_image(str(good)) is None
    assert "cannot read image" in worker._check_image(str(bad))
    assert "no such file" in worker._check_image(str(tmp_path / "missing.png"))


def test_handle_without_model(worker, tmp_path):
    engine = worker.Engine()
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "white").save(image)
    worker.handle(engine, {"cmd": "ping", "id": "1"})
    worker.handle(engine, {"cmd": "ocr", "id": "2", "image": str(image), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    worker.handle(engine, {"cmd": "dance", "id": "3"})
    worker.handle(engine, {"cmd": "unload", "id": "4"})
    assert worker.sent[0] == {"event": "pong", "id": "1"}
    assert worker.sent[1]["kind"] == "not_loaded"
    assert worker.sent[2]["kind"] == "internal"
    assert worker.sent[3] == {"event": "unloaded", "id": "4"}


def test_handle_bad_image_and_bad_mode(worker, tmp_path):
    engine = worker.Engine()
    engine.model = object()                  # pretend a model is loaded; ocr is never reached
    worker.handle(engine, {"cmd": "ocr", "id": "5", "image": str(tmp_path / "x.png"), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    worker.handle(engine, {"cmd": "ocr", "id": "6", "image": "x", "mode": "turbo",
                           "max_new_tokens": 10, "time_limit_s": 5})
    assert worker.sent[0]["kind"] == "bad_image"
    assert worker.sent[1]["kind"] == "internal"


def test_worker_never_uses_save_results():
    source = (REPO / "worker" / "owl_worker.py").read_text(encoding="utf-8")
    assert "save_results=True" not in source.replace("NEVER save_results=True", "")
    assert "eval_mode=True" in source
    assert "attn_implementation=" not in source
    assert not re.search(r"^\s*(import|from)\s+owlocr", source, re.M)


def test_worker_env_defaults(worker):
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


def test_engine_requirements_pin_the_design_versions():
    text = (REPO / "worker" / "requirements-engine.txt").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert {"transformers==4.57.1", "tokenizers>=0.22,<0.23", "huggingface_hub>=0.34,<1.0",
            "safetensors>=0.4.3", "accelerate", "Pillow==12.1.1", "einops==0.8.2", "addict==2.4.0",
            "easydict==1.13", "matplotlib==3.10.8", "psutil==7.2.2", "numpy<3"} <= lines
    assert not any(line.lower().startswith(("torch", "pymupdf")) for line in lines)
```

Create `tests/test_worker_engine.py`:

```python
"""The real worker in the engine's Python (torch + transformers), with CUDA hidden.

Never loads the OCR model and never touches the GPU: CUDA_VISIBLE_DEVICES=-1 hides every GPU.
Skipped when no engine Python is available. Uses OWLOCR_TEST_ENGINE_PYTHON, else the spike venv.
"""
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine
from owlocr.engine.protocol import EngineError
from tests.conftest import REPO

ENGINE_PYTHON = Path(os.environ.get("OWLOCR_TEST_ENGINE_PYTHON")
                     or REPO / "spike" / ".venv" / "Scripts" / "python.exe")
WORKER = REPO / "worker" / "owl_worker.py"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ENGINE_PYTHON.is_file(), reason=f"no engine Python at {ENGINE_PYTHON}"),
]


def make_engine(tmp_path) -> SubprocessEngine:
    return SubprocessEngine(python=ENGINE_PYTHON, worker_script=WORKER, model_dir=tmp_path / "no_model",
                            device="cpu", dtype="float32", log_file=tmp_path / "engine.log",
                            env={"CUDA_VISIBLE_DEVICES": "-1"})


def test_real_worker_protocol_without_model(tmp_path):
    engine = make_engine(tmp_path)
    try:
        info = engine.start()
        assert info.torch.startswith("2.")
        assert info.transformers == "4.57.1"
        assert info.cuda_available is False and info.gpu_name is None
        with pytest.raises(EngineError) as e:
            engine.ocr_page(REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.png", "quality")
        assert e.value.kind == "not_loaded"
        with pytest.raises(EngineError) as e:
            engine.load()                     # the model folder does not exist
        assert e.value.kind == "internal"
        assert engine.is_running()
    finally:
        engine.stop()
    assert not lifetime.process_alive(info.pid)
    log = (tmp_path / "engine.log").read_text(encoding="utf-8", errors="replace")
    assert "Traceback" in log                 # the failed load was logged to stderr, not stdout


def test_real_worker_exits_on_stdin_eof(tmp_path):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="-1")
    p = subprocess.Popen([str(ENGINE_PYTHON), str(WORKER), "--parent-pid", str(os.getpid())],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    try:
        assert b'"ready"' in p.stdout.readline()
        p.stdin.close()
        assert p.wait(timeout=10) == 0
    finally:
        p.kill()


def test_generate_wrapper_on_a_tiny_model(tmp_path):
    """The generate() wrapper with a 1-layer random GPT-2 on the CPU: max_new_tokens becomes
    max_length, the prefix is learned, the token cap is reported, and cancel stops generation."""
    script = textwrap.dedent(f"""
        import importlib.util, json, sys
        import torch
        from transformers import GPT2Config, GPT2LMHeadModel
        spec = importlib.util.spec_from_file_location("w", r"{WORKER}")
        w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
        events = []
        w.send = events.append
        torch.manual_seed(0)
        model = GPT2LMHeadModel(GPT2Config(n_layer=1, n_head=2, n_embd=16, vocab_size=50,
                                           n_positions=64)).eval()
        engine = w.Engine()
        engine._wrap_generate(model)
        ids = torch.tensor([[1, 2, 3, 4, 5, 6, 7]])
        engine.max_new_tokens = 5
        w.CONTROL.begin("a", 300)
        out = model.generate(input_ids=ids, max_length=60, do_sample=False, eos_token_id=None,
                             pad_token_id=0)
        first = dict(engine.last, length=int(out.shape[1]))
        engine.max_new_tokens = 40
        w.CONTROL.begin("b", 300)
        w.CONTROL.cancel("b")
        out = model.generate(input_ids=ids, max_length=60, do_sample=False, eos_token_id=None,
                             pad_token_id=0)
        second = dict(engine.last, length=int(out.shape[1]), cancelled=w.CONTROL.cancelled)
        print(json.dumps([first, second]))
    """)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="-1")
    out = subprocess.run([str(ENGINE_PYTHON), "-c", script], capture_output=True, text=True, env=env,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    first, second = json.loads(out.stdout.strip().splitlines()[-1])
    assert first == {"prefix_tokens": 7, "output_tokens": 5, "hit_token_cap": True, "length": 12}
    assert second["cancelled"] is True
    assert second["output_tokens"] == 1 and second["hit_token_cap"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_worker_unit.py tests/test_worker_engine.py -q`
Expected: FAIL — `FileNotFoundError` for `worker\owl_worker.py` in every `test_worker_unit` test; the `test_worker_engine` tests fail with `EngineError: died` / empty output (or are skipped when the spike venv is missing).

- [ ] **Step 3: Write minimal implementation**

Create `worker/owl_worker.py`:

```python
"""Owl OCR engine worker. Runs inside the engine's own Python (torch + transformers + model).

    python owl_worker.py --parent-pid <pid>

Protocol (design 5.4): one JSON object per line. Requests arrive on stdin, events leave on stdout.
Nothing else may reach stdout: main() points sys.stdout at stderr, so prints of the model code and
of libraries land in the app's engine.log.

The worker exits on stdin EOF, on `shutdown`, and when the parent process is gone (checked every
2 s). The app also starts it inside a Job Object, so it dies with the app in every case.

This file must not import owlocr: it is copied on its own into <data root>\\engine\\worker.
torch and transformers are imported inside functions so the control logic can be unit-tested
without them.
"""
import argparse
import ctypes
import gc
import json
import msvcrt
import os
import queue
import sys
import tempfile
import threading
import time
import traceback
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

PROMPT = "<image>document parsing."
MODES = {
    "quality": {"base_size": 1024, "image_size": 640, "crop_mode": True},
    "fast": {"base_size": 1024, "image_size": 1024, "crop_mode": False},
}
NO_REPEAT_NGRAM_SIZE = 35
NGRAM_WINDOW = 128
PLACEHOLDER_MAX_LENGTH = 8192     # replaced per page by prefix_tokens + max_new_tokens
PROGRESS_INTERVAL_S = 0.5
WATCHDOG_INTERVAL_S = 2.0

_proto = None                     # the protocol stream, set by main()
_proto_lock = threading.Lock()


def send(message: dict) -> None:
    line = json.dumps(message, ensure_ascii=False) + "\n"
    with _proto_lock:
        stream = _proto or sys.__stdout__
        stream.write(line)
        stream.flush()


def log(text: str) -> None:
    print(f"[worker] {text}", file=sys.stderr, flush=True)


# ---- parent watchdog (design 5.6, safeguard 3) -----------------------------------------------

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.restype = wintypes.BOOL
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.SetStdHandle.restype = wintypes.BOOL
_k32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
_STD_INPUT_HANDLE = 0xFFFFFFF6        # (DWORD)-10


def parent_alive(pid: int) -> bool:
    handle = _k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5                # access denied: it exists
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        _k32.CloseHandle(handle)


def watchdog(parent_pid: int) -> None:
    while True:
        time.sleep(WATCHDOG_INTERVAL_S)
        if not parent_alive(parent_pid):
            log(f"parent {parent_pid} is gone, exiting")
            os._exit(0)


# ---- control shared between the stdin reader and generation ---------------------------------

class Control:
    """Cancel flag, time limit and progress throttle for the page being read."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.request_id: str | None = None
        self.pending_cancels: set[str] = set()   # cancels that arrived before their ocr started
        self.cancel_requested = False
        self.started = 0.0
        self.time_limit_s = 0.0
        self.prefix_tokens = 0
        self.cancelled = False
        self.timed_out = False
        self.last_progress = 0.0
        self.last_tokens = -1

    def begin(self, request_id: str, time_limit_s: float) -> None:
        with self.lock:
            self.request_id = request_id
            self.cancel_requested = request_id in self.pending_cancels
            self.pending_cancels.discard(request_id)
            self.cancelled = self.timed_out = False
            self.started = time.monotonic()
            self.time_limit_s = float(time_limit_s)
            self.prefix_tokens = 0
            self.last_progress = self.started
            self.last_tokens = -1

    def end(self) -> None:
        with self.lock:
            self.request_id = None

    def cancel(self, request_id: str | None = None) -> None:
        """request_id None cancels whatever is running (used on shutdown)."""
        with self.lock:
            if self.request_id is not None and (request_id is None or request_id == self.request_id):
                self.cancel_requested = True
            elif request_id is not None:
                self.pending_cancels.add(request_id)

    def should_stop(self, total_tokens: int) -> bool:
        """Called after every generated token with the length of the whole sequence."""
        now = time.monotonic()
        with self.lock:
            generated = max(0, total_tokens - self.prefix_tokens)
            if self.cancel_requested:
                self.cancelled = True
            elif now - self.started > self.time_limit_s:
                self.timed_out = True
            emit = (self.request_id is not None and generated != self.last_tokens
                    and now - self.last_progress >= PROGRESS_INTERVAL_S)
            if emit:
                self.last_progress, self.last_tokens = now, generated
            request_id, stop = self.request_id, self.cancelled or self.timed_out
        if emit:
            send({"event": "progress", "id": request_id, "tokens": generated})
        return stop


CONTROL = Control()
REQUESTS: "queue.Queue[dict]" = queue.Queue()


def detach_stdin():
    """Move the request pipe away from the standard input handle and return it as a stream.

    Windows serialises synchronous I/O per file object: while the reader thread waits in
    ReadFile on the pipe, any GetFileType() on the same handle blocks. Every DLL with its own C
    runtime calls GetFileType() on the standard handles when it loads, and torch loads many (at
    import and lazily on first CUDA use), so a reader on the real stdin deadlocks the worker.
    After this call the standard input handle is NUL and only the reader touches the pipe."""
    pipe_fd = os.dup(0)
    null_fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_fd, 0)
    os.close(null_fd)
    _k32.SetStdHandle(_STD_INPUT_HANDLE, msvcrt.get_osfhandle(0))
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    return os.fdopen(pipe_fd, "rb")


def reader(stream) -> None:
    """Reads requests. `cancel` is handled here at once; everything else is queued for the main
    thread. EOF means the app is gone or closed the pipe: exit immediately."""
    for raw in stream:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or "cmd" not in message:
                raise ValueError("no cmd")
        except ValueError:
            send({"event": "error", "id": None, "kind": "internal", "message": f"bad request: {line[:200]}"})
            continue
        if message["cmd"] == "cancel":
            CONTROL.cancel(str(message.get("id")))
            continue
        if message["cmd"] == "shutdown":
            CONTROL.cancel()
        REQUESTS.put(message)
    log("stdin closed, exiting")
    os._exit(0)


# ---- the model --------------------------------------------------------------------------

class Engine:
    def __init__(self) -> None:
        self.tokenizer = None
        self.model = None
        self.device = "cuda"
        self.max_new_tokens = 6000
        self.last: dict = {}
        self.scratch = Path(tempfile.mkdtemp(prefix="owl_worker_"))

    def load(self, model_dir: str, device: str, dtype: str) -> tuple[float, int]:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.unload()
        t0 = time.perf_counter()
        folder = str(Path(model_dir).resolve())
        tokenizer = AutoTokenizer.from_pretrained(folder, trust_remote_code=True, local_files_only=True)
        # AutoModel, not the class itself: only AutoModel injects generate() into the remote code.
        # Never pass attn_implementation (design 5.2).
        model = AutoModel.from_pretrained(folder, trust_remote_code=True, use_safetensors=True,
                                          dtype=getattr(torch, dtype), local_files_only=True).eval()
        if device == "cuda":
            model = model.cuda()
        self._wrap_generate(model)
        self.tokenizer, self.model, self.device = tokenizer, model, device
        vram = torch.cuda.memory_allocated() // 2**20 if device == "cuda" else 0
        return time.perf_counter() - t0, int(vram)

    def _wrap_generate(self, model) -> None:
        """infer() only knows max_length (prompt + output) and reports nothing. The wrapper learns
        the prompt length, turns max_new_tokens into max_length and adds the stopping criteria."""
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        class _Stop(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                stop = CONTROL.should_stop(int(input_ids.shape[1]))
                return torch.full((input_ids.shape[0],), stop, dtype=torch.bool, device=input_ids.device)

        original = model.generate
        engine = self

        def generate(*args, **kwargs):
            prefix = int(kwargs["input_ids"].shape[1])
            with CONTROL.lock:
                CONTROL.prefix_tokens = prefix
            kwargs["max_length"] = prefix + engine.max_new_tokens
            criteria = StoppingCriteriaList(list(kwargs.get("stopping_criteria") or []))
            criteria.append(_Stop())
            kwargs["stopping_criteria"] = criteria
            out = original(*args, **kwargs)
            engine.last = {"prefix_tokens": prefix, "output_tokens": int(out.shape[1]) - prefix,
                           "hit_token_cap": int(out.shape[1]) >= kwargs["max_length"]}
            return out

        model.generate = generate

    def unload(self) -> None:
        if self.model is None:
            return
        import torch

        self.model = self.tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def ocr(self, request_id: str, image: str, mode: str, max_new_tokens: int, time_limit_s: float) -> dict:
        import torch

        self.max_new_tokens = int(max_new_tokens)
        self.last = {"prefix_tokens": 0, "output_tokens": 0, "hit_token_cap": False}
        cuda = self.device == "cuda"
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        CONTROL.begin(request_id, time_limit_s)
        t0 = time.perf_counter()
        try:
            # eval_mode=True returns the text. NEVER save_results=True: that path runs Python
            # eval() on model output. The n-gram guard defaults to 0 and must be passed.
            text = self.model.infer(self.tokenizer, prompt=PROMPT, image_file=image,
                                    output_path=str(self.scratch), max_length=PLACEHOLDER_MAX_LENGTH,
                                    no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE, ngram_window=NGRAM_WINDOW,
                                    eval_mode=True, **MODES[mode])
        finally:
            CONTROL.end()
        seconds = time.perf_counter() - t0
        peak = torch.cuda.max_memory_allocated() // 2**20 if cuda else 0
        stopped = CONTROL.cancelled or CONTROL.timed_out
        return {"event": "result", "id": request_id, "text": text or "", "seconds": round(seconds, 3),
                "prefix_tokens": self.last["prefix_tokens"], "output_tokens": self.last["output_tokens"],
                "hit_token_cap": bool(self.last["hit_token_cap"]) and not stopped,
                "cancelled": CONTROL.cancelled, "timed_out": CONTROL.timed_out, "peak_vram_mib": int(peak)}


def _is_out_of_memory(error: BaseException) -> bool:
    if isinstance(error, MemoryError):
        return True
    torch = sys.modules.get("torch")
    if torch is not None and isinstance(error, torch.cuda.OutOfMemoryError):
        return True
    text = str(error).lower()
    return isinstance(error, RuntimeError) and ("out of memory" in text or "can't allocate memory" in text)


def _check_image(image: str) -> str | None:
    from PIL import Image

    path = Path(image)
    if not path.is_file():
        return f"no such file: {image}"
    try:
        with Image.open(path) as im:
            im.load()
    except Exception as e:  # noqa: BLE001 - any decoder error means the page cannot be read
        return f"cannot read image {path.name}: {e}"
    return None


def _free_cuda_cache() -> None:
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def handle(engine: Engine, message: dict) -> None:
    cmd, rid = message.get("cmd"), message.get("id")
    try:
        if cmd == "ping":
            send({"event": "pong", "id": rid})
        elif cmd == "load":
            seconds, vram = engine.load(message["model_dir"], message["device"], message["dtype"])
            send({"event": "loaded", "id": rid, "seconds": round(seconds, 2), "vram_mib": vram})
        elif cmd == "unload":
            engine.unload()
            send({"event": "unloaded", "id": rid})
        elif cmd == "ocr":
            if engine.model is None:
                send({"event": "error", "id": rid, "kind": "not_loaded", "message": "load the model first"})
                return
            if message["mode"] not in MODES:
                send({"event": "error", "id": rid, "kind": "internal",
                      "message": f"unknown mode {message['mode']!r}"})
                return
            problem = _check_image(message["image"])
            if problem:
                send({"event": "error", "id": rid, "kind": "bad_image", "message": problem})
                return
            send(engine.ocr(rid, message["image"], message["mode"], message["max_new_tokens"],
                            message["time_limit_s"]))
        elif cmd == "shutdown":
            send({"event": "bye", "id": rid})
            os._exit(0)
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"unknown cmd {cmd!r}"})
    except KeyError as e:
        send({"event": "error", "id": rid, "kind": "internal", "message": f"missing field {e}"})
    except Exception as e:  # noqa: BLE001 - the worker must answer, whatever happened
        log(traceback.format_exc())
        if _is_out_of_memory(e):
            _free_cuda_cache()
            send({"event": "error", "id": rid, "kind": "out_of_memory", "message": str(e)[:500]})
        else:
            send({"event": "error", "id": rid, "kind": "internal", "message": f"{type(e).__name__}: {e}"[:500]})


def main() -> int:
    global _proto
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    _proto = sys.stdout
    _proto.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout = sys.stderr           # prints of the model code must not corrupt the protocol
    threading.Thread(target=watchdog, args=(args.parent_pid,), name="watchdog", daemon=True).start()
    threading.Thread(target=reader, args=(detach_stdin(),), name="stdin", daemon=True).start()

    import torch
    import transformers

    cuda = torch.cuda.is_available() and torch.cuda.device_count() > 0
    gpu_name = None
    if cuda:
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001 - a name is nice to have, not required
            cuda = False
    send({"event": "ready", "pid": os.getpid(), "torch": torch.__version__,
          "transformers": transformers.__version__, "cuda_available": cuda, "gpu_name": gpu_name})
    engine = Engine()
    while True:
        handle(engine, REQUESTS.get())


if __name__ == "__main__":
    sys.exit(main())
```

Create `worker/requirements-engine.txt`:

```text
# Engine runtime, installed by plan D into <data root>\engine\venv (design 5.1).
# torch and torchvision come first, from the PyTorch index of the hardware tier:
#   uv pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
# then:
#   uv pip install -r requirements-engine.txt
# transformers must stay 4.57.1: 5.x breaks the model's imports.
transformers==4.57.1
tokenizers>=0.22,<0.23
huggingface_hub>=0.34,<1.0
safetensors>=0.4.3
accelerate
Pillow==12.1.1
einops==0.8.2
addict==2.4.0
easydict==1.13
matplotlib==3.10.8
psutil==7.2.2
numpy<3
requests
tqdm
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_worker_unit.py tests/test_worker_engine.py -q`
Expected: `17 passed` (about 15 s: three starts of the engine Python importing torch, GPU hidden). Without the spike venv: `14 passed, 3 skipped`.

- [ ] **Step 5: Commit**

```
git add worker/owl_worker.py worker/requirements-engine.txt tests/test_worker_unit.py tests/test_worker_engine.py
git commit -m "Add the engine worker: protocol, cancel, time limit, progress, watchdog" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Document model and sidecar

**Files:**
- Create: `owlocr/pipeline/__init__.py`, `owlocr/pipeline/document.py`, `tests/samples.py`
- Test: `tests/test_document.py`

**Interfaces:**
- Consumes: `paths.atomic_write_text()`.
- Produces (contract): dataclasses `Flag(kind, start, end, original, note)`, `Block(label, box, text, raw_text, flags)`, `Page(index, source, mode, width_px, height_px, rotation_applied, blocks, raw, warnings, seconds)`, `Document(source_path, engine_id, engine_revision, app_version, created, pages)` exactly as design section 8 (no defaults); `to_json(doc: Document) -> str`, `from_json(text: str) -> Document`, `save_sidecar(doc: Document, path: Path) -> None`, `load_sidecar(path: Path) -> Document`, `plain_text(page: Page, keep_furniture: bool = False) -> str`, `FURNITURE_LABELS = ("page_number", "header", "footer")`. `plain_text` skips `image`/`figure` blocks and empty blocks, joins blocks with one blank line, and turns tables into tab-separated rows (through `parse.html_table_to_rows`, imported inside the function; Task 18 creates it and tests that part). `tests/samples.py` provides `sample_document()`.

- [ ] **Step 1: Write the failing test**

Create `tests/samples.py`:

```python
"""A small Document used by the document and export tests."""
from owlocr.pipeline.document import Block, Document, Flag, Page


def sample_document() -> Document:
    table = "<table><tr><td>Jméno</td><td>Obec</td></tr><tr><td>Žaneta</td><td>Třebíč</td></tr></table>"
    blocks = [
        Block(label="header", box=(10, 5, 300, 20), text="Kapitola 1", raw_text="Kapitola 1", flags=[]),
        Block(label="title", box=(100, 50, 400, 80), text="Buněčné dýchání", raw_text="Buněčné dýchání", flags=[]),
        Block(label="text", box=(100, 90, 900, 200), text="Buňka získává energii.",
              raw_text="Buňka ziskává energii.",
              flags=[Flag(kind="repaired", start=6, end=13, original="ziskává", note="R1")]),
        Block(label="image", box=(100, 210, 500, 400), text="", raw_text="", flags=[]),
        Block(label="table", box=(100, 410, 900, 600), text=table, raw_text=table, flags=[]),
        Block(label="page_number", box=(480, 960, 520, 980), text="7", raw_text="7", flags=[]),
    ]
    page = Page(index=0, source="ocr", mode="quality", width_px=1700, height_px=2200, rotation_applied=0,
                blocks=blocks, raw="<|det|>...", warnings=["runaway"], seconds=12.5)
    blank = Page(index=1, source="blank", mode=None, width_px=1700, height_px=2200, rotation_applied=0,
                 blocks=[], raw="", warnings=[], seconds=0.1)
    return Document(source_path="C:\\scans\\kniha.pdf", engine_id="unlimited_ocr",
                    engine_revision="07dea832e22aefee32ad281d4b80551282e1c168", app_version="0.1.0",
                    created="2026-09-28T12:00:00+02:00", pages=[page, blank])
```

Create `tests/test_document.py`:

```python
import json

from owlocr.pipeline import document
from owlocr.pipeline.document import Flag
from tests.samples import sample_document


def test_furniture_labels():
    assert document.FURNITURE_LABELS == ("page_number", "header", "footer")


def test_json_round_trip():
    doc = sample_document()
    text = document.to_json(doc)
    assert "Buněčné dýchání" in text                   # UTF-8, not \\u escapes
    back = document.from_json(text)
    assert back == doc
    assert isinstance(back.pages[0].blocks[0].box, tuple)
    assert isinstance(back.pages[0].blocks[2].flags[0], Flag)
    assert json.loads(text)["pages"][1]["source"] == "blank"


def test_sidecar(tmp_path):
    doc = sample_document()
    path = tmp_path / "kniha.owl.json"
    document.save_sidecar(doc, path)
    assert document.load_sidecar(path) == doc


def test_block_without_box_round_trips():
    doc = sample_document()
    doc.pages[0].blocks[1].box = None
    assert document.from_json(document.to_json(doc)).pages[0].blocks[1].box is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_document.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/__init__.py`:

```python
"""Processing pipeline: pages, guards, parsing, layout, repair, spell check."""
```

Create `owlocr/pipeline/document.py`:

```python
"""Document, Page, Block, Flag (design section 8) and the sidecar <name>.owl.json."""
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from owlocr import paths

FURNITURE_LABELS = ("page_number", "header", "footer")
_NO_TEXT_LABELS = ("image", "figure")


@dataclass
class Flag:
    kind: str          # 'repaired' | 'suspicious' | 'foreign_letter'
    start: int         # character offsets in Block.text
    end: int
    original: str      # text before repair, or the suspicious word
    note: str


@dataclass
class Block:
    label: str
    box: tuple[int, int, int, int] | None   # 0..999, None for text-layer blocks without geometry
    text: str          # after repair
    raw_text: str      # exactly as read
    flags: list[Flag]


@dataclass
class Page:
    index: int                  # 0-based
    source: str                 # 'ocr' | 'text_layer' | 'blank'
    mode: str | None            # 'quality' | 'fast'
    width_px: int
    height_px: int
    rotation_applied: int       # 0, 90, 180, 270
    blocks: list[Block]
    raw: str
    warnings: list[str]
    seconds: float


@dataclass
class Document:
    source_path: str
    engine_id: str
    engine_revision: str
    app_version: str
    created: str                # ISO 8601
    pages: list[Page]


def to_json(doc: Document) -> str:
    return json.dumps(asdict(doc), ensure_ascii=False, indent=1)


def _block(data: dict) -> Block:
    box = data.get("box")
    return Block(label=data["label"], box=tuple(box) if box is not None else None, text=data["text"],
                 raw_text=data["raw_text"], flags=[Flag(**f) for f in data.get("flags", [])])


def _page(data: dict) -> Page:
    values = dict(data)
    values["blocks"] = [_block(b) for b in data["blocks"]]
    return Page(**values)


def from_json(text: str) -> Document:
    data = json.loads(text)
    values = dict(data)
    values["pages"] = [_page(p) for p in data["pages"]]
    return Document(**values)


def save_sidecar(doc: Document, path: Path) -> None:
    paths.atomic_write_text(Path(path), to_json(doc) + "\n")


def load_sidecar(path: Path) -> Document:
    return from_json(Path(path).read_text(encoding="utf-8"))


def _table_text(html: str) -> str:
    from owlocr.pipeline.parse import html_table_to_rows

    rows = html_table_to_rows(html)
    if rows is None:            # merged cells: flatten the HTML row by row
        rows = []
        for row in re.split(r"</tr\s*>", html, flags=re.I):
            cells = [re.sub(r"<[^>]+>", " ", c) for c in re.split(r"</t[dh]\s*>", row, flags=re.I)]
            cells = [" ".join(c.split()) for c in cells]
            if any(cells):
                rows.append([c for c in cells if c])
    return "\n".join("\t".join(row) for row in rows)


def _block_text(block: Block) -> str:
    """Text of one block as plain text; tables become tab-separated rows."""
    if block.label in _NO_TEXT_LABELS:
        return ""
    if block.label == "table" and "<t" in block.text.lower():
        return _table_text(block.text)
    return block.text.strip()


def plain_text(page: Page, keep_furniture: bool = False) -> str:
    parts = []
    for block in page.blocks:
        if block.label in FURNITURE_LABELS and not keep_furniture:
            continue
        text = _block_text(block)
        if text:
            parts.append(text)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_document.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/__init__.py owlocr/pipeline/document.py tests/samples.py tests/test_document.py
git commit -m "Add Document, Page, Block, Flag and the sidecar JSON" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Parsing model output

**Files:**
- Create: `owlocr/pipeline/parse.py`
- Test: `tests/test_parse.py`, `tests/test_plain_text.py`

**Interfaces:**
- Consumes: `document.Block`.
- Produces (contract): `parse_raw(raw: str) -> list[Block]` (`Block.text == Block.raw_text`, `flags == []`; boxes clamped to 0..999 and ordered; unknown labels become `text`; text before the first tag becomes a `text` block without box; special tokens such as `<｜end▁of▁sentence｜>` removed; the older `<|ref|>…<|/ref|><|det|>[[…]]<|/det|>` form accepted, several boxes merged into one), `html_table_to_rows(html: str) -> list[list[str]] | None` (`None` when any cell has `rowspan` or `colspan`; `[]` when there is no row). Also `KNOWN_LABELS`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_parse.py`:

```python
from owlocr.pipeline.document import Block
from owlocr.pipeline.parse import html_table_to_rows, parse_raw
from tests.conftest import RAW


def test_letter_fixture():
    blocks = parse_raw((RAW / "01_letter_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    assert len(blocks) == 7
    assert all(isinstance(b, Block) for b in blocks)
    assert blocks[0] == Block(label="text", box=(101, 73, 365, 91), text="Vážená paní doktorko Šťastná,",
                              raw_text="Vážená paní doktorko Šťastná,", flags=[])
    assert blocks[-1].text == "Ústí nad Labem, 28. září 2026"
    assert all(b.text == b.raw_text and b.flags == [] for b in blocks)


def test_labels_titles_and_header():
    textbook = parse_raw((RAW / "02_textbook_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    assert [b.label for b in textbook][:2] == ["title", "text"]
    screenshot = parse_raw((RAW / "08_screenshot.gundam.raw.txt").read_text(encoding="utf-8"))
    assert screenshot[0].label == "header" and screenshot[0].text == "Nastavení účtu"


def test_table_fixture():
    blocks = parse_raw((RAW / "04_table_clean.gundam.raw.txt").read_text(encoding="utf-8"))
    table = blocks[1]
    assert table.label == "table" and table.box == (102, 121, 898, 313)
    rows = html_table_to_rows(table.text)
    assert rows[0] == ["Jméno", "Obec", "Částka", "Splatnost"]
    assert len(rows) == 6 and all(len(r) == 4 for r in rows)


def test_blank_page_fixture():
    blocks = parse_raw((RAW / "10_blank_page.gundam.raw.txt").read_text(encoding="utf-8"))
    assert blocks == [Block(label="image", box=(0, 0, 999, 999), text="", raw_text="", flags=[])]


def test_old_form_and_unknown_label():
    raw = ("<|ref|>title<|/ref|><|det|>[[10, 20, 300, 40]]<|/det|>\nNadpis\n"
           "<|ref|>sidebar<|/ref|><|det|>[[5,5,50,50], [60,60,90,999]]<|/det|>Okraj")
    blocks = parse_raw(raw)
    assert [(b.label, b.box, b.text) for b in blocks] == [
        ("title", (10, 20, 300, 40), "Nadpis"),
        ("text", (5, 5, 90, 999), "Okraj"),
    ]


def test_text_without_tags_and_special_tokens():
    assert parse_raw("") == []
    blocks = parse_raw("plain words<｜end▁of▁sentence｜>")
    assert [(b.label, b.box, b.text) for b in blocks] == [("text", None, "plain words")]


def test_coordinates_are_clamped_and_ordered():
    (block,) = parse_raw("<|det|>text [900, 1200, 100, -5]<|/det|>x")
    assert block.box == (100, 0, 900, 999)


def test_multiline_block_text_is_kept():
    (block,) = parse_raw("<|det|>list [1, 2, 3, 4]<|/det|>- jedna\n- dvě\n")
    assert block.text == "- jedna\n- dvě"


def test_html_table_merged_cells_and_entities():
    assert html_table_to_rows('<table><tr><td colspan="2">A</td></tr></table>') is None
    assert html_table_to_rows("<table><tr><td rowspan=2>A</td></tr></table>") is None
    rows = html_table_to_rows("<table><tr><th>a &amp; b</th><td>x<br>y</td></tr><tr><td> c </td></tr></table>")
    assert rows == [["a & b", "x y"], ["c"]]
    assert html_table_to_rows("no table here") == []
```

Create `tests/test_plain_text.py`:

```python
"""plain_text(): the page as plain text (needs parse.html_table_to_rows for tables)."""
from owlocr.pipeline import document
from owlocr.pipeline.document import Block
from tests.samples import sample_document


def test_plain_text():
    page = sample_document().pages[0]
    assert document.plain_text(page) == (
        "Buněčné dýchání\n\nBuňka získává energii.\n\nJméno\tObec\nŽaneta\tTřebíč")
    with_furniture = document.plain_text(page, keep_furniture=True)
    assert with_furniture.startswith("Kapitola 1\n\n")
    assert with_furniture.endswith("Třebíč\n\n7")


def test_plain_text_of_merged_table_and_blank_page():
    doc = sample_document()
    merged = '<table><tr><td colspan="2">Souhrn</td></tr><tr><td>a</td><td>b</td></tr></table>'
    doc.pages[0].blocks = [Block(label="table", box=None, text=merged, raw_text=merged, flags=[])]
    assert document.plain_text(doc.pages[0]) == "Souhrn\na\tb"
    assert document.plain_text(doc.pages[1]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_parse.py tests/test_plain_text.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.pipeline.parse'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/parse.py`:

```python
"""Raw model output -> blocks (design 7.4).

Current form:  <|det|>label [x1, y1, x2, y2]<|/det|>text
Older form:    <|ref|>label<|/ref|><|det|>[[x1, y1, x2, y2]]<|/det|>text
Coordinates are 0..999 relative to the page image. Tables arrive as HTML.
"""
import re
from html.parser import HTMLParser

from owlocr.pipeline.document import Block

KNOWN_LABELS = ("title", "header", "text", "image", "figure", "image_caption", "table",
                "table_caption", "list", "formula", "page_number", "footer")

_NUM = r"\s*(-?\d+)\s*"
_BOX = rf"\[{_NUM},{_NUM},{_NUM},{_NUM}\]"
_TAG = re.compile(
    rf"<\|det\|>\s*(?P<label>[\w-]+)\s*(?P<box>{_BOX})\s*<\|/det\|>"
    rf"|<\|ref\|>\s*(?P<oldlabel>[^<]*?)\s*<\|/ref\|>\s*<\|det\|>\s*\[(?P<oldboxes>.*?)\]\s*<\|/det\|>",
    re.S,
)
_BOX_RE = re.compile(_BOX)
_SPECIAL = re.compile(r"<\|[^|<>]*\|>|<｜[^｜<>]*｜>")


def _clamp(v: int) -> int:
    return max(0, min(999, v))


def _box(numbers: list[int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = (_clamp(n) for n in numbers)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _clean(text: str) -> str:
    return _SPECIAL.sub("", text).strip()


def _label(raw: str) -> str:
    label = raw.strip().lower()
    return label if label in KNOWN_LABELS else "text"


def parse_raw(raw: str) -> list[Block]:
    blocks: list[Block] = []
    matches = list(_TAG.finditer(raw))
    head = _clean(raw[: matches[0].start()] if matches else raw)
    if head:
        blocks.append(Block(label="text", box=None, text=head, raw_text=head, flags=[]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        text = _clean(raw[m.end():end])
        if m.group("label") is not None:
            label = _label(m.group("label"))
            box = _box([int(n) for n in _BOX_RE.match(m.group("box")).groups()])
        else:
            label = _label(m.group("oldlabel"))
            box = _union([_box([int(n) for n in b.groups()]) for b in _BOX_RE.finditer(m.group("oldboxes"))])
        blocks.append(Block(label=label, box=box, text=text, raw_text=text, flags=[]))
    return blocks


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.merged = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._close_row()
            self.row = []
        elif tag in ("td", "th"):
            if any(name in ("rowspan", "colspan") for name, _ in attrs):
                self.merged = True
            self._close_cell()
            if self.row is None:
                self.row = []
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def _close_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
        self.cell = None

    def _close_row(self):
        self._close_cell()
        if self.row:
            self.rows.append(self.row)
        self.row = None


def html_table_to_rows(html: str) -> list[list[str]] | None:
    """Rows of cell texts; None when the table has merged cells (rowspan/colspan)."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    parser._close_row()
    if parser.merged:
        return None
    return parser.rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_parse.py tests/test_plain_text.py tests/test_document.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/parse.py tests/test_parse.py tests/test_plain_text.py
git commit -m "Add parser for the model's tagged output and HTML tables" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Pages from images and PDFs

**Files:**
- Create: `owlocr/pipeline/pages.py`, `tests/pdf_fixtures.py`
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `pypdfium2` (`PdfDocument`, `page.get_bbox()`, `page.get_objects(filter=[pypdfium2.raw.FPDF_PAGEOBJ_IMAGE])`, `obj.get_bounds()`, `page.get_textpage().get_text_range()`, `page.render(scale=dpi / 72).to_pil()`; checked on pypdfium2 5.10.1 and 5.13.0), Pillow.
- Produces (contract): `IMAGE_SUFFIXES`, `SUPPORTED_SUFFIXES`, dataclass `PageSource(index, kind, text_layer)`, `count_pages(path: Path) -> int`, `list_pages(path: Path) -> list[PageSource]`, `render_page(path: Path, index: int, dpi: int, out_png: Path) -> tuple[int, int]`, `find_inputs(paths: list[Path]) -> list[Path]` (resolved, sorted case-insensitively, no repeats, skips `*.ocr.pdf` outputs). A PDF page is `scan` when one image covers at least 80 % of the page. Images keep their pixels (EXIF orientation applied, RGB on white). `tests/pdf_fixtures.py` provides `make_text_pdf(path, pages: list[list[str]])` and `make_scan_pdf(path, pages=1)` (8.5 x 11 inch pages).

- [ ] **Step 1: Write the failing test**

Create `tests/pdf_fixtures.py`:

```python
"""Small PDFs built on the fly for the tests (no PDF library needed)."""
from pathlib import Path

from PIL import Image, ImageDraw


def make_text_pdf(path: Path, pages: list[list[str]]) -> Path:
    """A born-digital PDF: each page shows its lines in Helvetica (plain ASCII only)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = len(objects) + 2 * len(pages) + 1     # the /Pages object comes after all pages
    kids = []
    for lines in pages:
        ops = ["BT", "/F1 14 Tf", "72 740 Td", "18 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({escaped}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                        b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                        % (pages_id, font, content)))
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>"
               % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    Path(path).write_bytes(bytes(out))
    return Path(path)


def make_scan_pdf(path: Path, pages: int = 1) -> Path:
    """A scanned PDF: every page is one full-page image with some dark 'text' bars."""
    images = []
    for n in range(pages):
        im = Image.new("RGB", (850, 1100), "white")
        draw = ImageDraw.Draw(im)
        for row in range(10):
            draw.rectangle([100, 100 + row * 60 + n * 5, 700, 120 + row * 60 + n * 5], fill="black")
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=100)
    return Path(path)
```

Create `tests/test_pages.py`:

```python
from PIL import Image

from owlocr.pipeline import pages
from owlocr.pipeline.pages import PageSource
from tests.conftest import PAGES
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf


def test_suffixes():
    assert pages.IMAGE_SUFFIXES == (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    assert pages.SUPPORTED_SUFFIXES == pages.IMAGE_SUFFIXES + (".pdf",)


def test_born_digital_pdf(tmp_path):
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["Hello world", "second line"], ["Page two"]])
    assert pages.count_pages(pdf) == 2
    listed = pages.list_pages(pdf)
    assert [p.kind for p in listed] == ["born_digital", "born_digital"]
    assert listed[0] == PageSource(index=0, kind="born_digital", text_layer="Hello world\nsecond line")
    assert listed[1].text_layer == "Page two"


def test_scanned_pdf(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf", pages=3)
    assert pages.count_pages(pdf) == 3
    listed = pages.list_pages(pdf)
    assert [(p.index, p.kind, p.text_layer) for p in listed] == [(0, "scan", None), (1, "scan", None), (2, "scan", None)]


def test_render_pdf_page_at_dpi(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf", pages=2)
    size = pages.render_page(pdf, 1, 200, tmp_path / "out" / "p1.png")
    assert size == (1700, 2200)                     # 8.5 x 11 inch at 200 dpi
    with Image.open(tmp_path / "out" / "p1.png") as im:
        assert im.size == size and im.mode == "RGB"


def test_image_file(tmp_path):
    src = PAGES / "08_screenshot.png"
    assert pages.count_pages(src) == 1
    assert pages.list_pages(src) == [PageSource(index=0, kind="image", text_layer=None)]
    assert pages.render_page(src, 0, 200, tmp_path / "p.png") == (1280, 720)


def test_exif_orientation_is_applied(tmp_path):
    im = Image.new("RGB", (400, 100), "white")
    exif = im.getexif()
    exif[0x0112] = 6                                 # rotate 90 degrees clockwise to display
    im.save(tmp_path / "photo.jpg", exif=exif)
    assert pages.render_page(tmp_path / "photo.jpg", 0, 200, tmp_path / "p.png") == (100, 400)


def test_multipage_tiff_and_transparency(tmp_path):
    frames = [Image.new("L", (50, 60), 255), Image.new("L", (70, 80), 0)]
    frames[0].save(tmp_path / "two.tif", save_all=True, append_images=frames[1:])
    assert pages.count_pages(tmp_path / "two.tif") == 2
    assert [p.index for p in pages.list_pages(tmp_path / "two.tif")] == [0, 1]
    assert pages.render_page(tmp_path / "two.tif", 1, 200, tmp_path / "f1.png") == (70, 80)
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(tmp_path / "clear.png")
    pages.render_page(tmp_path / "clear.png", 0, 200, tmp_path / "c.png")
    with Image.open(tmp_path / "c.png") as im:
        assert im.getpixel((5, 5)) == (255, 255, 255)


def test_find_inputs(tmp_path):
    (tmp_path / "a" / "deep").mkdir(parents=True)
    wanted = [tmp_path / "a" / "B.PNG", tmp_path / "a" / "deep" / "c.pdf", tmp_path / "z.jpg"]
    for p in wanted:
        p.write_bytes(b"x")
    (tmp_path / "a" / "notes.txt").write_text("x")
    (tmp_path / "a" / "deep" / "c.ocr.pdf").write_bytes(b"x")
    found = pages.find_inputs([tmp_path / "a", tmp_path / "z.jpg", tmp_path / "z.jpg", tmp_path / "missing.png"])
    assert found == sorted((p.resolve() for p in wanted), key=lambda p: str(p).lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_pages.py -q`
Expected: FAIL — `ImportError: cannot import name 'pages' from 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/pages.py`:

```python
"""Input files -> pages (design 7.1). PDFs are read with pypdfium2 (never PyMuPDF: AGPL).

A PDF page is a 'scan' when one image covers at least 80 % of the page, else 'born_digital'.
Image files are 'image' pages; a multi-page TIFF has one page per frame.
"""
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + (".pdf",)
SCAN_COVERAGE = 0.80
_OUTPUT_SUFFIXES = (".ocr.pdf",)          # our own searchable PDFs are never inputs


@dataclass
class PageSource:
    index: int
    kind: str                  # 'scan' | 'born_digital' | 'image'
    text_layer: str | None     # text of the PDF page, if any


def _is_pdf(path: Path) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def count_pages(path: Path) -> int:
    path = Path(path)
    if _is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    with Image.open(path) as im:
        return getattr(im, "n_frames", 1)


def _image_coverage(page) -> float:
    left, bottom, right, top = page.get_bbox()
    area = max((right - left) * (top - bottom), 1e-6)
    best = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        l, b, r, t = obj.get_bounds()
        w = max(0.0, min(r, right) - max(l, left))
        h = max(0.0, min(t, top) - max(b, bottom))
        best = max(best, w * h / area)
    return best


def _text_layer(page) -> str | None:
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_range()
    finally:
        textpage.close()
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    return text or None


def list_pages(path: Path) -> list[PageSource]:
    path = Path(path)
    if not _is_pdf(path):
        return [PageSource(index=i, kind="image", text_layer=None) for i in range(count_pages(path))]
    pdf = pdfium.PdfDocument(str(path))
    pages = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                kind = "scan" if _image_coverage(page) >= SCAN_COVERAGE else "born_digital"
                pages.append(PageSource(index=i, kind=kind, text_layer=_text_layer(page)))
            finally:
                page.close()
    finally:
        pdf.close()
    return pages


def _flatten(im: Image.Image) -> Image.Image:
    """RGB on white; transparent areas become paper, not black."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        background = Image.new("RGB", im.size, "white")
        background.paste(im, mask=im.getchannel("A"))
        return background
    return im.convert("RGB")


def render_page(path: Path, index: int, dpi: int, out_png: Path) -> tuple[int, int]:
    """Write page `index` as a PNG. PDFs are rendered at `dpi`; images keep their pixels and get
    their EXIF orientation applied. Returns (width, height) in pixels."""
    path, out_png = Path(path), Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if _is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            page = pdf[index]
            try:
                image = page.render(scale=dpi / 72).to_pil()
            finally:
                page.close()
        finally:
            pdf.close()
    else:
        with Image.open(path) as im:
            im.seek(index)
            image = ImageOps.exif_transpose(im)
    image = _flatten(image)
    image.save(out_png, "PNG")
    return image.width, image.height


def find_inputs(paths: list[Path]) -> list[Path]:
    """Files as given plus folders searched recursively; only supported types; sorted, no repeats."""
    found: set[Path] = set()
    for item in paths:
        item = Path(item)
        candidates = item.rglob("*") if item.is_dir() else [item]
        for p in candidates:
            name = p.name.lower()
            if (p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
                    and not name.endswith(_OUTPUT_SUFFIXES)):
                found.add(p.resolve())
    return sorted(found, key=lambda p: str(p).lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_pages.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/pages.py tests/pdf_fixtures.py tests/test_pages.py
git commit -m "Add page listing and rendering with pypdfium2 and Pillow" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 20: Guards: blank page and runaway output

**Files:**
- Create: `owlocr/pipeline/guards.py`
- Test: `tests/test_guards.py`

**Interfaces:**
- Consumes: Pillow; fixture pages and raw output.
- Produces (contract, plan A part): `is_blank(image: Path) -> bool`, `is_runaway(text: str, hit_token_cap: bool) -> bool`, `trim_runaway(text: str) -> str`. Plan C adds `looks_sideways`, `dictionary_hit_rate`, `best_rotation` to this file.

Rules: blank = fewer than 0.2 % dark pixels after a 3 px median filter, where "dark" means at least 80 levels darker than the paper (the median brightness). The design's fixed level 128 was measured on the fixtures and fails: `05_letter_poor_scan` has only 0.05 % pixels under 128 after the median filter and would be skipped as blank (see Contract notes). Runaway = token cap hit, or more than 5,000 characters compressing with zlib to under 5 %. `trim_runaway` cuts the text into 1,000-character windows and keeps everything before the first window from which every later window compresses under 25 %.

- [ ] **Step 1: Write the failing test**

Create `tests/test_guards.py`:

```python
from PIL import Image, ImageDraw

from owlocr.pipeline import guards
from tests.conftest import PAGES, RAW

REAL_TEXT = "\n".join(
    (RAW / f"{name}.gundam.raw.txt").read_text(encoding="utf-8")
    for name in ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
                 "06_textbook_poor_scan")
)


def test_fixture_pages():
    assert guards.is_blank(PAGES / "10_blank_page.png")
    for name in ("01_letter_clean", "03_small_print_clean", "05_letter_poor_scan", "06_textbook_poor_scan",
                 "07_letter_phone_photo", "08_screenshot"):
        assert not guards.is_blank(PAGES / f"{name}.png"), name


def test_speckles_alone_are_blank(tmp_path):
    im = Image.new("L", (1000, 1000), 255)
    for i in range(0, 1000, 37):                    # isolated dark pixels: removed by the median filter
        im.putpixel((i, (i * 7) % 1000), 0)
    im.save(tmp_path / "speckles.png")
    assert guards.is_blank(tmp_path / "speckles.png")


def test_grey_paper_without_text_is_blank(tmp_path):
    Image.new("L", (800, 800), 200).save(tmp_path / "grey.png")
    assert guards.is_blank(tmp_path / "grey.png")


def test_one_line_of_text_is_not_blank(tmp_path):
    im = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(im).rectangle([100, 500, 900, 520], fill="black")   # 1.6 % of the pixels
    im.save(tmp_path / "line.png")
    assert not guards.is_blank(tmp_path / "line.png")


def test_is_runaway():
    assert guards.is_runaway("short", hit_token_cap=True)
    assert not guards.is_runaway(REAL_TEXT, hit_token_cap=False)
    assert len(REAL_TEXT) > 5000
    assert guards.is_runaway("50 or greater, " * 800, hit_token_cap=False)
    assert not guards.is_runaway("abc " * 1000, hit_token_cap=False)      # under 5,000 characters


def test_trim_runaway_keeps_the_real_text():
    loop = "50 or greater, 70 or greater, " * 1500
    trimmed = guards.trim_runaway(REAL_TEXT + "\n" + loop)
    assert trimmed.startswith(REAL_TEXT[:4000])
    assert len(trimmed) < len(REAL_TEXT) + 1000
    assert not guards.is_runaway(trimmed, hit_token_cap=False)


def test_trim_runaway_leaves_normal_text_alone():
    assert guards.trim_runaway(REAL_TEXT) == REAL_TEXT
    assert guards.trim_runaway("") == ""
    table = (RAW / "04_table_clean.gundam.raw.txt").read_text(encoding="utf-8")
    assert guards.trim_runaway(table) == table


def test_trim_runaway_all_loop():
    assert guards.trim_runaway("la " * 5000) == ("la " * 5000)[:200].rstrip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_guards.py -q`
Expected: FAIL — `ImportError: cannot import name 'guards' from 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/guards.py`:

```python
"""Checks before and after OCR (design 7.2, 7.3). Plan A: blank page and runaway output.
Plan C adds looks_sideways, dictionary_hit_rate and best_rotation to this file."""
import zlib
from pathlib import Path

from PIL import Image, ImageFilter

BLANK_DARK_SHARE = 0.002          # fewer than 0.2 % dark pixels = blank
DARK_BELOW_PAPER = 80             # "dark" = at least this much darker than the paper
RUNAWAY_MIN_CHARS = 5000
RUNAWAY_RATIO = 0.05              # whole text compresses to under 5 %
_WINDOW = 1000                    # trim_runaway looks at the text in windows of this size
_WINDOW_RATIO = 0.25              # a window compressing under 25 % is repetition


def is_blank(image: Path) -> bool:
    """Fewer than 0.2 % dark pixels after a 3 px median filter (which removes speckles).
    "Dark" is measured against the paper (the median brightness), not against a fixed 128:
    on a grey, blurred 150 dpi scan the thin strokes never get darker than 128 after the
    median filter, and the fixed level would call a page full of text blank."""
    with Image.open(image) as im:
        gray = im.convert("L").filter(ImageFilter.MedianFilter(3))
    histogram = gray.histogram()
    pixels = gray.width * gray.height
    seen, paper = 0, 255
    for level, count in enumerate(histogram):
        seen += count
        if seen * 2 >= pixels:
            paper = level
            break
    dark = sum(histogram[:max(paper - DARK_BELOW_PAPER, 0)])
    return dark < BLANK_DARK_SHARE * pixels


def _ratio(text: str) -> float:
    data = text.encode("utf-8")
    return len(zlib.compress(data, 9)) / max(len(data), 1)


def is_runaway(text: str, hit_token_cap: bool) -> bool:
    if hit_token_cap:
        return True
    return len(text) > RUNAWAY_MIN_CHARS and _ratio(text) < RUNAWAY_RATIO


def trim_runaway(text: str) -> str:
    """Keep the text up to where it starts repeating itself. The text is cut into windows; the
    repetition starts at the first window from which every later window is repetitive."""
    windows = [text[i:i + _WINDOW] for i in range(0, len(text), _WINDOW)]
    repetitive = []
    for window in windows:
        if len(window) < _WINDOW // 5 and repetitive:
            repetitive.append(repetitive[-1])        # a short tail says nothing on its own
        else:
            repetitive.append(_ratio(window) < _WINDOW_RATIO)
    start = len(windows)
    while start > 0 and repetitive[start - 1]:
        start -= 1
    if start == len(windows):
        return text                                  # no repetition at the end
    if start == 0:
        return text[:_WINDOW // 5].rstrip()          # all of it loops: keep the beginning
    cut = start * _WINDOW
    head = text[:cut]
    newline = head.rfind("\n")
    if newline > cut - _WINDOW // 2:
        head = head[:newline]
    return head.rstrip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_guards.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/guards.py tests/test_guards.py
git commit -m "Add blank-page and runaway-output guards" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 21: Basic layout and the plan C stubs

**Files:**
- Create: `owlocr/pipeline/layout.py`, `owlocr/pipeline/repair.py`, `owlocr/pipeline/spellcheck.py`
- Test: `tests/test_layout_and_stubs.py`

**Interfaces:**
- Consumes: `document.Block`, `paths.data_root()`.
- Produces (contract): `layout.arrange(blocks: list[Block], language: str = "cs") -> list[Block]` (order kept; `word-\nword` joined when the second part starts lower case; tables untouched; changed blocks are new objects with `raw_text` unchanged); `repair.repair_block(block: Block, language: str, personal_words: set[str]) -> Block` (returns the block unchanged); `spellcheck.available(language: str) -> bool` (False), `known(word: str, language: str) -> bool` (True), `flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block` (unchanged), `detect_language(text: str) -> str` ("cs"), `dictionaries_dir() -> Path` (`data_root()/dictionaries`). Plan C replaces the bodies.

- [ ] **Step 1: Write the failing test**

Create `tests/test_layout_and_stubs.py`:

```python
from owlocr.pipeline import layout, repair, spellcheck
from owlocr.pipeline.document import Block


def block(text: str, label: str = "text") -> Block:
    return Block(label=label, box=(0, 0, 10, 10), text=text, raw_text=text, flags=[])


def test_order_is_kept_and_unchanged_blocks_are_the_same_objects():
    blocks = [block("první"), block("druhý", "title"), block("třetí")]
    arranged = layout.arrange(blocks)
    assert [b.text for b in arranged] == ["první", "druhý", "třetí"]
    assert all(a is b for a, b in zip(arranged, blocks))


def test_line_break_hyphen_is_joined():
    (b,) = layout.arrange([block("rostliny kaktu-\nsovitých rostou")])
    assert b.text == "rostliny kaktusovitých rostou"
    assert b.raw_text == "rostliny kaktu-\nsovitých rostou"


def test_hyphen_with_spaces_around_the_break():
    (b,) = layout.arrange([block("děle- \n  ní buněk")])
    assert b.text == "dělení buněk"


def test_capital_after_the_break_keeps_the_hyphen():
    (b,) = layout.arrange([block("Česko-\nSlovensko")])
    assert b.text == "Česko-\nSlovensko"


def test_hyphen_inside_a_line_and_numbers_stay():
    (b,) = layout.arrange([block("ATP-syntáza a 4.-19. září a 12-\n15")])
    assert b.text == "ATP-syntáza a 4.-19. září a 12-\n15"


def test_tables_are_left_alone():
    table = block("<table><tr><td>kaktu-\nsovitý</td></tr></table>", "table")
    assert layout.arrange([table]) == [table]


def test_repair_and_spellcheck_stubs():
    b = block("bud'")
    assert repair.repair_block(b, "cs", set()) is b
    assert spellcheck.flag_suspicious(b, "cs", {"x"}) is b
    assert spellcheck.available("cs") is False
    assert spellcheck.known("slovo", "cs") is True
    assert spellcheck.detect_language("The quick brown fox") == "cs"


def test_dictionaries_dir(owl_env):
    assert spellcheck.dictionaries_dir() == owl_env["home"] / "dictionaries"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_layout_and_stubs.py -q`
Expected: FAIL — `ImportError: cannot import name 'layout' from 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/layout.py`:

```python
"""Reading order and line-break hyphens (design 7.5).

Plan A (basic): the model's block order is kept, and a word split by a hyphen at a line break
(`kaktu-\\nsovitých`) is joined when the second part starts with a lower-case letter.
Plan C adds the caption move and the dictionary-aware join of `kaktu-sovitých` without a line break.
"""
import dataclasses
import re

from owlocr.pipeline.document import Block

_LINE_BREAK_HYPHEN = re.compile(r"([^\W\d_])-[ \t]*\n[ \t]*([^\W\d_])")


def _join(match: re.Match) -> str:
    before, after = match.group(1), match.group(2)
    if after.islower():
        return before + after
    return match.group(0)             # "Česko-\nSlovensko" keeps its hyphen and line break


def _dehyphenate(text: str) -> str:
    return _LINE_BREAK_HYPHEN.sub(_join, text)


def arrange(blocks: list[Block], language: str = "cs") -> list[Block]:
    arranged = []
    for block in blocks:
        if block.label == "table":
            arranged.append(block)
            continue
        text = _dehyphenate(block.text)
        arranged.append(block if text == block.text else dataclasses.replace(block, text=text))
    return arranged
```

Create `owlocr/pipeline/repair.py`:

```python
"""Rule-based corrections (design 9). Plan A: pass-through stub; plan C replaces the body."""
from owlocr.pipeline.document import Block


def repair_block(block: Block, language: str, personal_words: set[str]) -> Block:
    return block
```

Create `owlocr/pipeline/spellcheck.py`:

```python
"""Dictionary checks (design 9.3). Plan A: pass-through stubs; plan C replaces the bodies."""
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Block


def available(language: str) -> bool:
    return False


def known(word: str, language: str) -> bool:
    return True            # no dictionary installed: every word counts as known


def flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block:
    return block


def detect_language(text: str) -> str:
    return "cs"


def dictionaries_dir() -> Path:
    return paths.data_root() / "dictionaries"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_layout_and_stubs.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/layout.py owlocr/pipeline/repair.py owlocr/pipeline/spellcheck.py tests/test_layout_and_stubs.py
git commit -m "Add basic layout and pass-through repair and spellcheck stubs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 22: One page through the pipeline

**Files:**
- Create: `owlocr/pipeline/process.py`
- Test: `tests/test_process.py`

**Interfaces:**
- Consumes: `pages.PageSource`, `pages.render_page`, `guards.is_blank`, `guards.is_runaway`, `guards.trim_runaway`, `parse.parse_raw`, `layout.arrange`, `repair.repair_block`, `spellcheck.detect_language`, `spellcheck.flag_suspicious`, `document.Block`, `document.Page`, any engine with `ocr_page(image, mode, max_new_tokens=..., time_limit_s=..., on_progress=..., cancel=...) -> PageResult`.
- Produces (contract): dataclass `ProcessOptions(mode="quality", dpi=200, use_text_layer="born_digital", language="auto", repairs_enabled=True, time_limit_s=300.0, max_new_tokens=6000, personal_words=frozenset())`, `process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path, on_progress=None, cancel=None) -> Page`, `cleanup(page: Page, options: ProcessOptions) -> Page` (no-op). The page image is written to `scratch/page_<index:04d>.png` and left there. `process_page` never catches `EngineError`: out of memory, a dead worker and all other engine errors reach the caller (plan B's runner and the CLI do the retries of design 5.7). Warning strings it writes: `empty_retried`, `empty`, `runaway`, `time_limit`, `cancelled`; callers add `out_of_memory_fast`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_process.py`:

```python
import threading

import pytest

from owlocr.engine.protocol import EngineError, PageResult
from owlocr.pipeline import process, repair
from owlocr.pipeline.pages import PageSource
from owlocr.pipeline.process import ProcessOptions, cleanup, process_page
from tests.conftest import PAGES, RAW
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf

LETTER_RAW = (RAW / "01_letter_clean.gundam.raw.txt").read_text(encoding="utf-8")
IMAGE_PAGE = PageSource(index=0, kind="image", text_layer=None)


def result(text: str, **changes) -> PageResult:
    values = dict(text=text, seconds=1.0, prefix_tokens=907, output_tokens=len(text) // 3,
                  hit_token_cap=False, cancelled=False, timed_out=False, peak_vram_mib=0)
    values.update(changes)
    return PageResult(**values)


class StubEngine:
    """Answers ocr_page from a list of PageResults or EngineErrors, in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def ocr_page(self, image, mode, max_new_tokens=6000, time_limit_s=300.0, on_progress=None, cancel=None):
        self.calls.append({"image": image, "mode": mode, "max_new_tokens": max_new_tokens,
                           "time_limit_s": time_limit_s, "on_progress": on_progress, "cancel": cancel})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_options_defaults():
    o = ProcessOptions()
    assert (o.mode, o.dpi, o.use_text_layer, o.language, o.repairs_enabled) == ("quality", 200, "born_digital", "auto", True)
    assert (o.time_limit_s, o.max_new_tokens, o.personal_words) == (300.0, 6000, frozenset())


def test_image_page_is_read(tmp_path):
    engine = StubEngine(result(LETTER_RAW))
    progress, cancel = [].append, threading.Event()
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine,
                        ProcessOptions(time_limit_s=120, max_new_tokens=4000), tmp_path,
                        on_progress=progress, cancel=cancel)
    assert (page.index, page.source, page.mode) == (0, "ocr", "quality")
    assert (page.width_px, page.height_px, page.rotation_applied) == (2480, 3508, 0)
    assert len(page.blocks) == 7 and page.blocks[0].text == "Vážená paní doktorko Šťastná,"
    assert page.raw == LETTER_RAW and page.warnings == []
    call = engine.calls[0]
    assert call["image"] == tmp_path / "page_0000.png" and call["image"].is_file()
    assert (call["mode"], call["max_new_tokens"], call["time_limit_s"]) == ("quality", 4000, 120)
    assert call["on_progress"] is progress and call["cancel"] is cancel


def test_blank_page_skips_the_engine(tmp_path):
    engine = StubEngine()
    page = process_page(PAGES / "10_blank_page.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert (page.source, page.mode, page.blocks, page.raw) == ("blank", None, [], "")
    assert engine.calls == []


def test_born_digital_pdf_uses_the_text_layer(tmp_path):
    pdf = make_text_pdf(tmp_path / "doc.pdf", [["First paragraph line"]])
    engine = StubEngine()
    source = PageSource(index=0, kind="born_digital", text_layer="First para-\ngraph\n\nSecond one")
    page = process_page(pdf, source, engine, ProcessOptions(dpi=100), tmp_path / "scratch")
    assert engine.calls == []
    assert (page.source, page.mode, page.width_px, page.height_px) == ("text_layer", None, 850, 1100)
    assert [(b.label, b.box, b.text) for b in page.blocks] == [("text", None, "First paragraph"),
                                                               ("text", None, "Second one")]
    assert page.raw == "First para-\ngraph\n\nSecond one"


def test_text_layer_settings(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    scan_with_old_ocr = PageSource(index=0, kind="scan", text_layer="old hidden text")
    engine = StubEngine(result("<|det|>text [1, 1, 500, 100]<|/det|>fresh text"))
    page = process_page(pdf, scan_with_old_ocr, engine, ProcessOptions(), tmp_path)
    assert page.source == "ocr" and page.blocks[0].text == "fresh text"          # born_digital ignores scans
    page = process_page(pdf, scan_with_old_ocr, StubEngine(), ProcessOptions(use_text_layer="always"), tmp_path)
    assert page.source == "text_layer" and page.blocks[0].text == "old hidden text"
    digital = PageSource(index=0, kind="born_digital", text_layer="layer")
    engine = StubEngine(result("<|det|>text [1, 1, 500, 100]<|/det|>read"))
    page = process_page(pdf, digital, engine, ProcessOptions(use_text_layer="never"), tmp_path)
    assert page.source == "ocr" and len(engine.calls) == 1


@pytest.mark.parametrize("kind", ["out_of_memory", "died", "bad_image", "internal"])
def test_engine_errors_reach_the_caller(tmp_path, kind):
    """process_page never swallows EngineError; the caller (CLI, plan B runner) decides."""
    engine = StubEngine(EngineError(kind, "x"), result(LETTER_RAW))
    with pytest.raises(EngineError) as e:
        process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert e.value.kind == kind
    assert len(engine.calls) == 1


def test_empty_output_is_retried_in_the_other_mode(tmp_path):
    engine = StubEngine(result("<|det|>image [0, 0, 999, 999]<|/det|>"), result(LETTER_RAW))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert [c["mode"] for c in engine.calls] == ["quality", "fast"]
    assert page.mode == "fast" and page.warnings == ["empty_retried"] and len(page.blocks) == 7


def test_still_empty_after_retry(tmp_path):
    engine = StubEngine(result(""), result(""))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(mode="fast"), tmp_path)
    assert [c["mode"] for c in engine.calls] == ["fast", "quality"]
    assert page.warnings == ["empty_retried", "empty"] and page.blocks == []


def test_runaway_output_is_trimmed(tmp_path):
    loop = "<|det|>text [1, 1, 900, 900]<|/det|>" + "50 or greater, 70 or greater, " * 800
    engine = StubEngine(result(LETTER_RAW + "\n" + loop, hit_token_cap=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["runaway"]
    assert page.raw.endswith("or greater, ")                  # raw keeps everything that was read
    assert sum(len(b.text) for b in page.blocks) < len(LETTER_RAW) + 1000
    assert page.blocks[0].text == "Vážená paní doktorko Šťastná,"


def test_cancelled_and_timed_out_pages_keep_their_text_and_are_not_retried(tmp_path):
    engine = StubEngine(result("<|det|>text [1, 1, 9, 9]<|/det|>Vážená", cancelled=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["cancelled"] and page.blocks[0].text == "Vážená"
    engine = StubEngine(result("", timed_out=True))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine, ProcessOptions(), tmp_path)
    assert page.warnings == ["time_limit"] and len(engine.calls) == 1


def test_layout_runs_and_repairs_can_be_switched_off(tmp_path, monkeypatch):
    def boom(*args):
        raise AssertionError("repair must not run")

    monkeypatch.setattr(repair, "repair_block", boom)
    engine = StubEngine(result("<|det|>text [1, 1, 9, 9]<|/det|>kaktu-\nsovitých"))
    page = process_page(PAGES / "01_letter_clean.png", IMAGE_PAGE, engine,
                        ProcessOptions(repairs_enabled=False), tmp_path)
    assert page.blocks[0].text == "kaktusovitých"
    assert page.blocks[0].raw_text == "kaktu-\nsovitých"


def test_cleanup_is_a_no_op():
    from owlocr.pipeline.document import Page
    page = Page(index=0, source="blank", mode=None, width_px=1, height_px=1, rotation_applied=0,
                blocks=[], raw="", warnings=[], seconds=0.0)
    assert cleanup(page, ProcessOptions()) is page
    assert process.cleanup is cleanup
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_process.py -q`
Expected: FAIL — `ImportError: cannot import name 'process' from 'owlocr.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/pipeline/process.py`:

```python
"""One page through the whole pipeline (design 7):

    text layer usable? yes -> blocks from the text layer
                       no  -> blank? -> engine -> guards (empty, runaway) -> parse
    -> layout -> repair -> spellcheck -> cleanup -> Page

EngineError is never caught here: out of memory, a dead worker and every other engine failure
reach the caller. The caller retries (design 5.7): out of memory in Quality -> the page once more
with mode="fast" and the warning "out_of_memory_fast"; a dead worker -> restart once, read again.

Warnings written into Page.warnings (plan B shows them):
    "empty_retried"       the first reading had no text; the page was read again in the other mode
    "empty"               no text even after the retry
    "runaway"             the output repeated itself; it was cut where the repetition starts
    "time_limit"          the page hit time_limit_s; what was read so far is kept
    "cancelled"           reading was cancelled; what was read so far is kept
"""
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from owlocr.engine.protocol import PageResult
from owlocr.pipeline import layout, repair, spellcheck
from owlocr.pipeline.document import Block, Page
from owlocr.pipeline.guards import is_blank, is_runaway, trim_runaway
from owlocr.pipeline.pages import PageSource, render_page
from owlocr.pipeline.parse import parse_raw

_NO_TEXT_LABELS = ("image", "figure")


@dataclass
class ProcessOptions:
    mode: str = "quality"
    dpi: int = 200
    use_text_layer: str = "born_digital"
    language: str = "auto"
    repairs_enabled: bool = True
    time_limit_s: float = 300.0
    max_new_tokens: int = 6000
    personal_words: frozenset[str] = frozenset()


def _use_text_layer(page: PageSource, options: ProcessOptions) -> bool:
    if not page.text_layer:
        return False
    if options.use_text_layer == "always":
        return True
    return options.use_text_layer == "born_digital" and page.kind == "born_digital"


def _text_layer_blocks(text: str) -> list[Block]:
    paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", text) if p.strip()]
    return [Block(label="text", box=None, text=p, raw_text=p, flags=[]) for p in paragraphs]


def _has_text(blocks: list[Block]) -> bool:
    return any(b.text.strip() for b in blocks if b.label not in _NO_TEXT_LABELS)


def _read(engine, png: Path, mode: str, options: ProcessOptions, on_progress, cancel) -> PageResult:
    return engine.ocr_page(png, mode, max_new_tokens=options.max_new_tokens,
                           time_limit_s=options.time_limit_s, on_progress=on_progress, cancel=cancel)


def process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> Page:
    t0 = time.perf_counter()
    png = Path(scratch) / f"page_{page.index:04d}.png"
    width, height = render_page(Path(source), page.index, options.dpi, png)
    warnings: list[str] = []
    mode: str | None = None

    if _use_text_layer(page, options):
        kind, raw = "text_layer", page.text_layer
        blocks = _text_layer_blocks(raw)
    elif is_blank(png):
        blank = Page(index=page.index, source="blank", mode=None, width_px=width, height_px=height,
                     rotation_applied=0, blocks=[], raw="", warnings=[],
                     seconds=round(time.perf_counter() - t0, 3))
        return cleanup(blank, options)
    else:
        kind, mode = "ocr", options.mode
        result = _read(engine, png, mode, options, on_progress, cancel)
        stopped = result.cancelled or result.timed_out
        if not stopped and not _has_text(parse_raw(result.text)):
            warnings.append("empty_retried")
            mode = "fast" if mode == "quality" else "quality"
            result = _read(engine, png, mode, options, on_progress, cancel)
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
        blocks = parse_raw(text)

    if options.language in ("cs", "en"):
        language = options.language
    else:
        language = spellcheck.detect_language("\n".join(b.text for b in blocks))
    personal = set(options.personal_words)
    blocks = layout.arrange(blocks, language)
    if options.repairs_enabled:
        blocks = [repair.repair_block(b, language, personal) for b in blocks]
    blocks = [spellcheck.flag_suspicious(b, language, personal) for b in blocks]
    result_page = Page(index=page.index, source=kind, mode=mode, width_px=width, height_px=height,
                       rotation_applied=0, blocks=blocks, raw=raw, warnings=warnings,
                       seconds=round(time.perf_counter() - t0, 3))
    return cleanup(result_page, options)


def cleanup(page: Page, options: ProcessOptions) -> Page:
    """Slot for the local cleanup add-on (design 14). A no-op in v1."""
    return page
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_process.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/pipeline/process.py tests/test_process.py
git commit -m "Add process_page: text layer, blank, OCR, empty retry, runaway trim" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 23: Plain text export

**Files:**
- Create: `owlocr/export/__init__.py` (docstring only; Task 25 fills it), `owlocr/export/text.py`
- Test: `tests/test_export_text.py`

**Interfaces:**
- Consumes: `document.plain_text`, `paths.unique_path`, `paths.atomic_write_text`.
- Produces (contract): `export_text(doc: Document, out: Path, keep_furniture: bool = False) -> Path` (path actually written after `unique_path`), `document_text(doc: Document, keep_furniture: bool = False) -> str` (pages joined by one blank line, final newline; `""` when there is no text; used for the clipboard).

- [ ] **Step 1: Write the failing test**

Create `tests/test_export_text.py`:

```python
from owlocr.export.text import document_text, export_text
from tests.samples import sample_document


def test_document_text_and_export(tmp_path):
    doc = sample_document()
    assert document_text(doc) == "Buněčné dýchání\n\nBuňka získává energii.\n\nJméno\tObec\nŽaneta\tTřebíč\n"
    assert document_text(doc, keep_furniture=True).startswith("Kapitola 1\n\n")
    first = export_text(doc, tmp_path / "kniha.txt")
    second = export_text(doc, tmp_path / "kniha.txt")
    assert first == tmp_path / "kniha.txt" and second == tmp_path / "kniha_1.txt"
    assert first.read_text(encoding="utf-8") == document_text(doc)


def test_document_text_of_empty_document():
    doc = sample_document()
    doc.pages = doc.pages[1:]
    assert document_text(doc) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_export_text.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.export'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/export/__init__.py` with this single line (Task 25 replaces the file):

```python
"""Exports. Plan A: Markdown and plain text. Plan C adds Word and searchable PDF."""
```

Create `owlocr/export/text.py`:

```python
"""Plain text export (design 11): blocks in order, one blank line between blocks, tables as
tab-separated rows. The same text goes to the clipboard."""
from pathlib import Path

from owlocr import paths
from owlocr.pipeline.document import Document, plain_text


def document_text(doc: Document, keep_furniture: bool = False) -> str:
    pages = [plain_text(page, keep_furniture) for page in doc.pages]
    text = "\n\n".join(p for p in pages if p)
    return text + "\n" if text else ""


def export_text(doc: Document, out: Path, keep_furniture: bool = False) -> Path:
    target = paths.unique_path(Path(out))
    paths.atomic_write_text(target, document_text(doc, keep_furniture))
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_export_text.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/__init__.py owlocr/export/text.py tests/test_export_text.py
git commit -m "Add plain text export" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 24: Markdown export

**Files:**
- Create: `owlocr/export/markdown.py`
- Test: `tests/test_export_markdown.py`

**Interfaces:**
- Consumes: `document.FURNITURE_LABELS`, `Block`, `Document`, `Page`; `pages.render_page`; `parse.html_table_to_rows`; `paths.unique_path`, `paths.atomic_write_text`.
- Produces (contract): `export_markdown(doc: Document, out: Path, page_comments: bool = False, keep_furniture: bool = False, suspicious_appendix: bool = False) -> Path`. Title `#` when its box is at least 1.6 times the typical text-line height, else `##`; lists as `- ` items; tables as pipe tables (HTML kept when cells are merged); formulas as `$$` blocks; captions in italics; `image`/`figure` blocks are cut from the source page (re-rendered from `doc.source_path` at 200 dpi; box coordinates are 0..999 of the page, scaled as `x * width // 999` like the model code) into `<out stem>_images/pageNNN_imgK.png` and linked; no crop when the source file is missing. The appendix lists `suspicious` flags.

- [ ] **Step 1: Write the failing test**

Create `tests/test_export_markdown.py`:

```python
from PIL import Image

from owlocr.export.markdown import export_markdown
from owlocr.pipeline.document import Block, Flag
from tests.pdf_fixtures import make_scan_pdf
from tests.samples import sample_document


def test_markdown(tmp_path):
    doc = sample_document()
    out = export_markdown(doc, tmp_path / "kniha.md")
    assert out == tmp_path / "kniha.md"
    text = out.read_text(encoding="utf-8")
    assert text == ("## Buněčné dýchání\n\n"
                    "Buňka získává energii.\n\n"
                    "| Jméno | Obec |\n|---|---|\n| Žaneta | Třebíč |\n")
    assert not (tmp_path / "kniha_images").exists()          # source PDF does not exist: no crops


def test_markdown_options(tmp_path):
    doc = sample_document()
    doc.pages[0].blocks[2].flags.append(Flag(kind="suspicious", start=0, end=5, original="Buňka", note=""))
    text = export_markdown(doc, tmp_path / "k.md", page_comments=True, keep_furniture=True,
                           suspicious_appendix=True).read_text(encoding="utf-8")
    assert text.startswith("<!-- page 1 -->\n\nKapitola 1\n\n## Buněčné dýchání")
    assert "\n\n7\n\n<!-- page 2 -->\n\n---" in text
    assert text.endswith("**Suspicious words / Podezřelá slova**\n\n- page 1: `Buňka`\n")


def block(label, text, box=(100, 100, 900, 120)):
    return Block(label=label, box=box, text=text, raw_text=text, flags=[])


def test_markdown_block_types(tmp_path):
    doc = sample_document()
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [
        block("title", "Velký nadpis", (100, 50, 900, 90)),              # 40 high vs 20 for a text line
        block("title", "Malý\nnadpis", (100, 100, 900, 125)),
        block("text", "Odstavec.", (100, 130, 900, 150)),
        block("list", "• první\n2) druhá\n- třetí"),
        block("formula", "$$E = mc^2$$"),
        block("image_caption", "Obr. 1  Buňka"),
        block("table_caption", "Tab. 2"),
        block("table", '<table><tr><td colspan="2">a|b</td></tr></table>'),
        block("table", "<table><tr><td>a|b</td><td>c</td></tr><tr><td>d</td></tr></table>"),
        block("footer", "zápatí"),
    ]
    text = export_markdown(doc, tmp_path / "t.md").read_text(encoding="utf-8")
    assert text == ("# Velký nadpis\n\n"
                    "## Malý nadpis\n\n"
                    "Odstavec.\n\n"
                    "- první\n- druhá\n- třetí\n\n"
                    "$$\nE = mc^2\n$$\n\n"
                    "*Obr. 1 Buňka*\n\n"
                    "*Tab. 2*\n\n"
                    '<table><tr><td colspan="2">a|b</td></tr></table>\n\n'
                    "| a\\|b | c |\n|---|---|\n| d |  |\n")


def test_markdown_cuts_images_from_the_source(tmp_path):
    pdf = make_scan_pdf(tmp_path / "scan.pdf")
    doc = sample_document()
    doc.source_path = str(pdf)
    doc.pages = doc.pages[:1]
    doc.pages[0].blocks = [block("text", "Nad obrázkem."), block("figure", "", (0, 0, 499, 499))]
    out = export_markdown(doc, tmp_path / "out" / "scan.md")
    text = out.read_text(encoding="utf-8")
    assert text == "Nad obrázkem.\n\n![](scan_images/page001_img1.png)\n"
    with Image.open(tmp_path / "out" / "scan_images" / "page001_img1.png") as im:
        assert im.size == (849, 1098)            # 499/999 of 1700 x 2200 (letter at 200 dpi)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_export_markdown.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'owlocr.export.markdown'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/export/markdown.py`:

```python
"""Markdown export (design 11).

title -> '#' when its box is at least 1.6 times as tall as the page's typical text line, else '##';
text -> paragraph; list -> list items; table -> pipe table, or the HTML when cells are merged;
formula -> $$ ... $$; image/figure -> cut from the page into <name>_images/ and linked;
captions in italics; page_number/header/footer left out unless keep_furniture.
"""
import re
import statistics
import tempfile
from pathlib import Path

from PIL import Image

from owlocr import paths
from owlocr.pipeline.document import FURNITURE_LABELS, Block, Document, Page
from owlocr.pipeline.pages import render_page
from owlocr.pipeline.parse import html_table_to_rows

_BULLET = re.compile(r"^\s*(?:[-*+•·▪–]|\d+[.)])\s+")
_CROP_DPI = 200


def _line_height(page: Page) -> float | None:
    """Typical height of one text line, from the text blocks' boxes (a block may hold many lines,
    so the smallest boxes are the best estimate)."""
    heights = sorted(b.box[3] - b.box[1] for b in page.blocks if b.label == "text" and b.box)
    if not heights:
        return None
    return statistics.median(heights[: max(1, len(heights) // 2)])


def _heading(block: Block, line: float | None) -> str:
    level = "##"
    if block.box and line:
        if (block.box[3] - block.box[1]) >= 1.6 * line:
            level = "#"
    return f"{level} {' '.join(block.text.split())}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _table(block: Block) -> str:
    rows = html_table_to_rows(block.text) if "<t" in block.text.lower() else None
    if not rows:
        return block.text.strip()
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |",
             "|" + "---|" * width]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _list(block: Block) -> str:
    items = [line.strip() for line in block.text.splitlines() if line.strip()]
    return "\n".join("- " + _BULLET.sub("", item) for item in items)


def _formula(block: Block) -> str:
    body = block.text.strip()
    for opening, closing in (("$$", "$$"), ("\\[", "\\]"), ("$", "$")):
        if body.startswith(opening) and body.endswith(closing) and len(body) > len(opening) + len(closing):
            body = body[len(opening):-len(closing)].strip()
            break
    return f"$$\n{body}\n$$"


class _ImageCutter:
    """Cuts image blocks out of the source pages into <out stem>_images/."""

    def __init__(self, doc: Document, out: Path) -> None:
        self.source = Path(doc.source_path)
        self.folder = out.with_name(out.stem + "_images")
        self.count = 0
        self._rendered: dict[int, Image.Image] = {}

    def link(self, page: Page, block: Block) -> str | None:
        if block.box is None or not self.source.is_file():
            return None
        image = self._page_image(page.index)
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

    def _page_image(self, index: int) -> Image.Image | None:
        if index not in self._rendered:
            with tempfile.TemporaryDirectory() as tmp:
                png = Path(tmp) / "page.png"
                try:
                    render_page(self.source, index, _CROP_DPI, png)
                except (OSError, ValueError, IndexError, EOFError):
                    return None
                with Image.open(png) as im:
                    self._rendered[index] = im.copy()
        return self._rendered[index]


def _page_markdown(page: Page, keep_furniture: bool, images: _ImageCutter) -> list[str]:
    parts = []
    line = _line_height(page)
    for block in page.blocks:
        if block.label in FURNITURE_LABELS and not keep_furniture:
            continue
        if block.label in ("image", "figure"):
            link = images.link(page, block)
            if link:
                parts.append(link)
            continue
        if not block.text.strip():
            continue
        if block.label == "title":
            parts.append(_heading(block, line))
        elif block.label == "table":
            parts.append(_table(block))
        elif block.label == "list":
            parts.append(_list(block))
        elif block.label == "formula":
            parts.append(_formula(block))
        elif block.label in ("image_caption", "table_caption"):
            parts.append(f"*{' '.join(block.text.split())}*")
        else:
            parts.append(block.text.strip())
    return parts


def _appendix(doc: Document) -> str | None:
    lines = []
    for page in doc.pages:
        for block in page.blocks:
            for flag in block.flags:
                if flag.kind == "suspicious":
                    lines.append(f"- page {page.index + 1}: `{flag.original}`")
    if not lines:
        return None
    return "---\n\n**Suspicious words / Podezřelá slova**\n\n" + "\n".join(lines)


def export_markdown(doc: Document, out: Path, page_comments: bool = False,
                    keep_furniture: bool = False, suspicious_appendix: bool = False) -> Path:
    target = paths.unique_path(Path(out))
    images = _ImageCutter(doc, target)
    chunks = []
    for page in doc.pages:
        parts = _page_markdown(page, keep_furniture, images)
        if page_comments:
            parts.insert(0, f"<!-- page {page.index + 1} -->")
        if parts:
            chunks.append("\n\n".join(parts))
    if suspicious_appendix and (appendix := _appendix(doc)):
        chunks.append(appendix)
    text = "\n\n".join(chunks)
    paths.atomic_write_text(target, text + "\n" if text else "")
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_export_markdown.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/markdown.py tests/test_export_markdown.py
git commit -m "Add Markdown export with headings, tables, lists and image crops" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 25: export_all

**Files:**
- Modify: `owlocr/export/__init__.py` (replace)
- Test: `tests/test_export_all.py`

**Interfaces:**
- Consumes: `export_markdown`, `export_text`; settings keys `keep_page_furniture`, `append_suspicious_list`.
- Produces (contract): `FORMATS = ("md", "txt", "docx", "pdf")`, `export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]`. Writes only the requested formats as `<source stem>.md` / `.txt` in `out_dir`; never writes the `.owl.json` sidecar (the caller does). `docx` and `pdf` raise `NotImplementedError` before anything is written (plan C fills them in); unknown formats raise `ValueError`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_export_all.py`:

```python
import pytest

from owlocr import export
from tests.samples import sample_document


def test_export_all(tmp_path):
    doc = sample_document()
    written = export.export_all(doc, tmp_path / "in" / "kniha.pdf", ["md", "txt"], tmp_path / "out",
                                {"keep_page_furniture": True, "append_suspicious_list": False})
    assert written == {"md": tmp_path / "out" / "kniha.md", "txt": tmp_path / "out" / "kniha.txt"}
    assert written["txt"].read_text(encoding="utf-8").startswith("Kapitola 1")
    assert export.FORMATS == ("md", "txt", "docx", "pdf")


def test_export_all_rejects_later_and_unknown_formats(tmp_path):
    doc = sample_document()
    with pytest.raises(NotImplementedError):
        export.export_all(doc, tmp_path / "k.pdf", ["md", "docx"], tmp_path / "out", {})
    assert not (tmp_path / "out" / "k.md").exists()
    with pytest.raises(NotImplementedError):
        export.export_all(doc, tmp_path / "k.pdf", ["pdf"], tmp_path / "out", {})
    with pytest.raises(ValueError):
        export.export_all(doc, tmp_path / "k.pdf", ["html"], tmp_path / "out", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_export_all.py -q`
Expected: FAIL — `AttributeError: module 'owlocr.export' has no attribute 'export_all'`.

- [ ] **Step 3: Write minimal implementation**

Replace the whole content of `owlocr/export/__init__.py`:

```python
"""Exports. Plan A: Markdown and plain text. Plan C adds Word and searchable PDF."""
from pathlib import Path

from owlocr.export.markdown import export_markdown
from owlocr.export.text import export_text
from owlocr.pipeline.document import Document

FORMATS = ("md", "txt", "docx", "pdf")


def export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]:
    """Write every requested format into out_dir, named after the source file (design 10.6).
    Returns format -> path actually written (existing files are never overwritten)."""
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown export formats: {unknown}")
    later = [f for f in formats if f in ("docx", "pdf")]
    if later:                                   # checked before anything is written
        raise NotImplementedError(f"{', '.join(later)} export arrives with plan C")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source).stem
    keep = bool(settings.get("keep_page_furniture", False))
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "md":
            written["md"] = export_markdown(doc, out_dir / f"{stem}.md", keep_furniture=keep,
                                            suspicious_appendix=bool(settings.get("append_suspicious_list", False)))
        elif fmt == "txt":
            written["txt"] = export_text(doc, out_dir / f"{stem}.txt", keep_furniture=keep)
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_export_all.py tests/test_export_text.py tests/test_export_markdown.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/export/__init__.py tests/test_export_all.py
git commit -m "Add export_all for Markdown and text" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 26: Command-line tool

**Files:**
- Create: `owlocr/cli.py` (without the `__main__` block, which Task 29 adds)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `settings.load()`; `hardware.free_vram_mib`, `REQUIRED_FREE_VRAM_MIB`; `client.default_engine`, `sweep_stale_worker`, `SubprocessEngine`; `protocol.MODES`, `EngineError`; `registry.get`; `export.FORMATS`, `export_all`; `document.Document`, `Page`, `save_sidecar`; `pages.PageSource`, `find_inputs`, `list_pages`; `process.ProcessOptions`, `process_page`; `paths.work_dir`, `paths.unique_path`.
- Produces (contract): `python -m owlocr.cli <input> [<input> ...] [--mode quality|fast] [--formats md,txt] [--out DIR] [--pages 1-5,9] [--dpi 200]`; `main(argv: list[str] | None = None) -> int`; exit code 0 on success, 1 when any input failed (or bad arguments), 2 when the engine is not installed. Each input also gets `<stem>.owl.json`. Output paths are printed to stdout, progress to stderr. The engine starts only when a page needs OCR. Retries of design 5.7: out of memory in Quality reads the page again in Fast and adds the warning `out_of_memory_fast`; a dead worker is restarted once and the page read again. Before loading on `cuda` the free VRAM must reach `REQUIRED_FREE_VRAM_MIB[mode]`. Private: `_parse_pages(spec, count) -> list[int]` (0-based).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
"""owlocr.cli, in-process, with tests/fake_worker.py as the engine."""
import json
import shutil
import sys

import pytest

from owlocr import cli, hardware, paths
from owlocr.pipeline.document import load_sidecar
from tests.conftest import FAKE_WORKER, PAGES
from tests.pdf_fixtures import make_scan_pdf, make_text_pdf


def install_fake_engine(flags: str = "", device: str = "cpu") -> None:
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps({
        "engine_id": "unlimited_ocr", "python": sys.executable, "worker_script": str(FAKE_WORKER),
        "device": device, "env": {"FAKE_WORKER": flags}}))


@pytest.fixture
def letter(tmp_path):
    target = tmp_path / "in" / "dopis.png"
    target.parent.mkdir()
    shutil.copy(PAGES / "01_letter_clean.png", target)
    return target


def test_parse_pages():
    assert cli._parse_pages(None, 3) == [0, 1, 2]
    assert cli._parse_pages("1-5,9", 20) == [0, 1, 2, 3, 4, 8]
    assert cli._parse_pages("3, 1-2 ,2", 10) == [0, 1, 2]
    assert cli._parse_pages("5-3", 10) == [2, 3, 4]
    assert cli._parse_pages("2,40", 3) == [1]
    with pytest.raises(ValueError):
        cli._parse_pages("1-", 3)


def test_image_to_markdown_and_text(letter, tmp_path, capsys):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "md,txt", "--out", str(tmp_path / "out")]) == 0
    out = tmp_path / "out"
    assert (out / "dopis.md").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert (out / "dopis.txt").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    doc = load_sidecar(out / "dopis.owl.json")
    assert doc.source_path == str(letter.resolve()) and doc.pages[0].mode == "quality"
    printed = capsys.readouterr().out.splitlines()
    assert printed == [str(out / "dopis.md"), str(out / "dopis.txt"), str(out / "dopis.owl.json")]
    assert not list((paths.data_root() / "work").iterdir())        # scratch folders removed


def test_outputs_go_next_to_the_input_by_default(letter):
    install_fake_engine()
    assert cli.main([str(letter.parent), "--mode", "fast"]) == 0
    assert (letter.parent / "dopis.md").is_file()               # settings default: md only
    assert not (letter.parent / "dopis.txt").exists()
    assert load_sidecar(letter.parent / "dopis.owl.json").pages[0].mode == "fast"


def test_born_digital_pdf_never_starts_ocr(tmp_path):
    install_fake_engine("crash_on_ocr")
    pdf = make_text_pdf(tmp_path / "clanek.pdf", [["Hello from the text layer"]])
    assert cli.main([str(pdf), "--formats", "txt"]) == 0
    assert (tmp_path / "clanek.txt").read_text(encoding="utf-8") == "Hello from the text layer\n"


def test_page_selection(tmp_path):
    install_fake_engine()
    pdf = make_scan_pdf(tmp_path / "sken.pdf", pages=3)
    assert cli.main([str(pdf), "--pages", "2-3", "--dpi", "100"]) == 0
    doc = load_sidecar(tmp_path / "sken.owl.json")
    assert [p.index for p in doc.pages] == [1, 2]
    assert (doc.pages[0].width_px, doc.pages[0].height_px) == (850, 1100)


def test_not_installed_is_exit_code_2(letter):
    assert cli.main([str(letter)]) == 2


def test_bad_arguments_are_exit_code_1(letter, tmp_path):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "html"]) == 1
    assert cli.main([str(letter), "--pages", "x"]) == 1
    assert cli.main([str(tmp_path / "nothing_here")]) == 1


def test_later_formats_fail_the_input(letter):
    install_fake_engine()
    assert cli.main([str(letter), "--formats", "md,docx"]) == 1
    assert not (letter.parent / "dopis.md").exists()


def test_engine_crash_twice_fails_the_input(letter, capsys):
    install_fake_engine("crash_on_ocr")
    assert cli.main([str(letter)]) == 1
    err = capsys.readouterr().err
    assert "restarting" in err and "FAILED" in err


def test_out_of_memory_in_quality_is_read_again_in_fast(letter):
    install_fake_engine("oom_on_quality")
    assert cli.main([str(letter)]) == 0
    page = load_sidecar(letter.parent / "dopis.owl.json").pages[0]
    assert page.mode == "fast" and page.warnings == ["out_of_memory_fast"]


def test_not_enough_graphics_memory(letter, monkeypatch):
    install_fake_engine(device="cuda")
    monkeypatch.setattr(hardware, "free_vram_mib", lambda: 4000)
    assert cli.main([str(letter)]) == 1
    monkeypatch.setattr(hardware, "free_vram_mib", lambda: 8000)
    assert cli.main([str(letter), "--mode", "fast"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'cli' from 'owlocr'`.

- [ ] **Step 3: Write minimal implementation**

Create `owlocr/cli.py`:

```python
"""Command-line use without the window.

    python -m owlocr.cli <input> [<input> ...] [--mode quality|fast] [--formats md,txt]
                         [--out DIR] [--pages 1-5,9] [--dpi 200]

Inputs may be files or folders (searched recursively). Results go next to each input, or into
--out. Every input also gets its sidecar <name>.owl.json. Defaults come from settings.json.
Exit code 0 on success, 1 when any input failed, 2 when the engine is not installed.
"""
import argparse
import dataclasses
import re
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from owlocr import __version__, hardware, paths, settings
from owlocr.engine.client import SubprocessEngine, default_engine, sweep_stale_worker
from owlocr.engine.protocol import MODES, EngineError
from owlocr.engine.registry import get as get_engine_spec
from owlocr.export import FORMATS, export_all
from owlocr.pipeline.document import Document, Page, save_sidecar
from owlocr.pipeline.pages import PageSource, find_inputs, list_pages
from owlocr.pipeline.process import ProcessOptions, process_page

_PAGES_SPEC = re.compile(r"^\s*\d+(\s*-\s*\d+)?(\s*,\s*\d+(\s*-\s*\d+)?)*\s*$")


def _parse_pages(spec: str | None, count: int) -> list[int]:
    """'1-5,9' -> [0, 1, 2, 3, 4, 8] (0-based, only pages that exist, sorted, no repeats)."""
    if not spec:
        return list(range(count))
    if not _PAGES_SPEC.match(spec):
        raise ValueError(f"bad --pages value: {spec!r} (example: 1-5,9)")
    chosen: set[int] = set()
    for part in spec.split(","):
        first, _, last = part.partition("-")
        low, high = int(first), int(last or first)
        chosen.update(range(min(low, high), max(low, high) + 1))
    return sorted(n - 1 for n in chosen if 1 <= n <= count)


class _LazyEngine:
    """Starts and loads the engine only when a page really needs OCR, and again after a crash."""

    def __init__(self, engine: SubprocessEngine) -> None:
        self.engine = engine

    def ocr_page(self, *args, **kwargs):
        if not self.engine.loaded:
            self.engine.load()
        return self.engine.ocr_page(*args, **kwargs)

    def stop(self) -> None:
        self.engine.stop()


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _read_page(path: Path, source: PageSource, engine: _LazyEngine, options: ProcessOptions,
               scratch: Path) -> Page:
    """process_page with the retries of design 5.7: out of memory in Quality -> once more in Fast;
    worker died -> restart it once and read the page again."""
    restarted = False
    while True:
        try:
            return process_page(path, source, engine, options, scratch)
        except EngineError as e:
            if e.kind == "out_of_memory" and options.mode == "quality":
                _say("  out of graphics memory in Quality mode; reading the page in Fast mode")
                page = _read_page(path, source, engine, dataclasses.replace(options, mode="fast"), scratch)
                page.warnings.insert(0, "out_of_memory_fast")
                return page
            if e.kind != "died" or restarted:
                raise
            restarted = True
            _say("  the engine stopped unexpectedly; restarting it and reading the page again")


def _read_document(path: Path, engine: _LazyEngine, options: ProcessOptions, pages_spec: str | None,
                   scratch: Path) -> Document:
    sources = list_pages(path)
    wanted = set(_parse_pages(pages_spec, len(sources)))
    spec = get_engine_spec(engine.engine.engine_id)
    doc = Document(source_path=str(path), engine_id=spec.engine_id, engine_revision=spec.revision,
                   app_version=__version__, created=datetime.now().astimezone().isoformat(timespec="seconds"),
                   pages=[])
    selected = [s for s in sources if s.index in wanted]
    for n, source in enumerate(selected, start=1):
        page = _read_page(path, source, engine, options, scratch)
        doc.pages.append(page)
        notes = f" [{', '.join(page.warnings)}]" if page.warnings else ""
        _say(f"  {path.name}: page {source.index + 1} ({n}/{len(selected)}) {page.source}, {page.seconds:.1f} s{notes}")
    return doc


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    config = settings.load()
    parser = argparse.ArgumentParser(prog="python -m owlocr.cli", description="Owl OCR without the window.")
    parser.add_argument("inputs", nargs="+", help="files or folders")
    parser.add_argument("--mode", choices=MODES, default=config["mode_default"])
    parser.add_argument("--formats", default=",".join(config["formats"]), help="comma-separated: md,txt")
    parser.add_argument("--out", default=None, help="output folder (default: next to each input)")
    parser.add_argument("--pages", default=None, help="page numbers, e.g. 1-5,9")
    parser.add_argument("--dpi", type=int, default=config["pdf_dpi"], help="PDF rendering resolution")
    args = parser.parse_args(argv)

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in FORMATS]
    if not formats or unknown:
        _say(f"unknown formats: {', '.join(unknown) or '(none given)'}; choose from {', '.join(FORMATS)}")
        return 1
    try:
        _parse_pages(args.pages, 1)
    except ValueError as e:
        _say(str(e))
        return 1
    inputs = find_inputs([Path(p) for p in args.inputs])
    if not inputs:
        _say("no supported files found (images: png jpg jpeg webp bmp tif tiff; pdf)")
        return 1
    try:
        engine = default_engine()
    except EngineError as e:
        _say(f"the OCR engine is not installed: {e.message}")
        return 2
    if engine.device == "cuda":
        free = hardware.free_vram_mib()
        need = hardware.REQUIRED_FREE_VRAM_MIB[args.mode]
        if free is not None and free < need:
            _say(f"only {free} MiB of graphics memory is free; {args.mode} mode needs {need} MiB. "
                 "Close games, video or recording software and try again.")
            return 1

    options = ProcessOptions(mode=args.mode, dpi=args.dpi, use_text_layer=config["use_text_layer"],
                             language=config["document_language"], repairs_enabled=config["repairs_enabled"],
                             time_limit_s=float(config["time_limit_s"]),
                             personal_words=frozenset(config["personal_words"]))
    sweep_stale_worker()
    lazy = _LazyEngine(engine)
    failed = 0
    try:
        for path in inputs:
            scratch = paths.work_dir(f"cli-{uuid.uuid4().hex[:12]}")
            t0 = time.perf_counter()
            try:
                doc = _read_document(path, lazy, options, args.pages, scratch)
                out_dir = Path(args.out) if args.out else path.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                sidecar = paths.unique_path(out_dir / f"{path.stem}.owl.json")
                save_sidecar(doc, sidecar)
                written = export_all(doc, path, formats, out_dir, config)
                for target in [*written.values(), sidecar]:
                    print(target)
                _say(f"{path.name}: done in {time.perf_counter() - t0:.1f} s")
            except (EngineError, OSError, ValueError, NotImplementedError) as e:
                failed += 1
                _say(f"{path.name}: FAILED: {e}")
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
    finally:
        lazy.stop()
    return 1 if failed else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_cli.py -q`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```
git add owlocr/cli.py tests/test_cli.py
git commit -m "Add command-line tool with page selection and engine retries" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 27: Development engine configuration

**Files:**
- Create: `scripts/dev_engine.py`
- Test: `tests/test_dev_engine.py`

**Interfaces:**
- Consumes: `registry.UNLIMITED_OCR`, `store.is_ready`, `paths.engine_dir`, `paths.model_dir`, `paths.atomic_write_text`; `tests/store_fakes.py`.
- Produces: `py -3.11 scripts\dev_engine.py [--python PATH] [--data-root PATH]` writes `<data root>\engine\install.json` with `engine_id`, `revision`, `torch`, `torchvision`, `transformers`, `tier: "development"`, `device: "cuda"`, `dtype: "bfloat16"`, `torch_index`, `python` (default `<repo>\spike\.venv\Scripts\python.exe`) and `worker_script` (`<repo>\worker\owl_worker.py`). Default data root `<repo>\engine`, so `default_engine()` works with `OWLOCR_HOME=<repo>\engine` and uses the model in `engine\models\unlimited_ocr`. Refuses (exit 1) when the Python is missing or the model is not ready. Function `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dev_engine.py`:

```python
import importlib.util
import json
import sys
from pathlib import Path

from owlocr import paths
from owlocr.engine.client import default_engine
from tests.conftest import REPO
from tests.store_fakes import FILES, SPEC, manifest_entries


def load_script():
    spec = importlib.util.spec_from_file_location("dev_engine", REPO / "scripts" / "dev_engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_model(root: Path) -> None:
    folder = root / "models" / "unlimited_ocr"
    folder.mkdir(parents=True)
    for rel, data in FILES.items():
        (folder / rel).write_bytes(data)
    (folder / "manifest.json").write_text(json.dumps(
        {"repo": SPEC.repo, "commit": SPEC.revision, "files": manifest_entries()}), encoding="utf-8")


def test_writes_install_json_that_default_engine_accepts(tmp_path, monkeypatch):
    root = tmp_path / "devroot"
    fake_model(root)
    assert load_script().main(["--python", sys.executable, "--data-root", str(root)]) == 0
    data = json.loads((root / "engine" / "install.json").read_text(encoding="utf-8"))
    assert data["python"] == sys.executable
    assert data["revision"] == SPEC.revision and data["device"] == "cuda" and data["dtype"] == "bfloat16"
    monkeypatch.setenv("OWLOCR_HOME", str(root))
    engine = default_engine()
    assert engine.python == Path(sys.executable)
    assert engine.worker_script == REPO / "worker" / "owl_worker.py"
    assert engine.model_dir == root / "models" / "unlimited_ocr"
    assert engine.log_file == paths.logs_dir() / "engine.log"


def test_refuses_without_model_or_python(tmp_path):
    script = load_script()
    assert script.main(["--python", sys.executable, "--data-root", str(tmp_path / "empty")]) == 1
    fake_model(tmp_path / "root")
    assert script.main(["--python", str(tmp_path / "none.exe"), "--data-root", str(tmp_path / "root")]) == 1
    assert not (tmp_path / "root" / "engine" / "install.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_dev_engine.py -q`
Expected: FAIL — `FileNotFoundError` for `scripts\dev_engine.py`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/dev_engine.py`:

```python
"""Development only: make default_engine() work from the repository.

    py -3.11 scripts\\dev_engine.py

Writes <data root>\\engine\\install.json for a development engine:
  data root      <repo>\\engine            (git-ignored; holds the verified model in models\\unlimited_ocr)
  engine Python  <repo>\\spike\\.venv\\Scripts\\python.exe   (torch 2.10.0+cu128, transformers 4.57.1)
  worker         <repo>\\worker\\owl_worker.py (run straight from the repository)

Every shell that then runs the app or the CLI must point Owl OCR at that data root, because tools
started from the Claude desktop app get %APPDATA% and %LOCALAPPDATA% silently redirected:
  PowerShell:  $env:OWLOCR_HOME = "<repo>\\engine"; $env:OWLOCR_CONFIG = "<repo>\\engine\\config"
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", default=str(REPO / "spike" / ".venv" / "Scripts" / "python.exe"),
                        help="Python of the development engine")
    parser.add_argument("--data-root", default=str(REPO / "engine"), help="development data root")
    args = parser.parse_args(argv)

    data_root = Path(args.data_root).resolve()
    os.environ["OWLOCR_HOME"] = str(data_root)           # before anything asks owlocr.paths
    from owlocr import paths
    from owlocr.engine import registry, store

    spec = registry.UNLIMITED_OCR
    python = Path(args.python)
    worker = REPO / "worker" / "owl_worker.py"
    if not python.is_file():
        print(f"no engine Python at {python}", file=sys.stderr)
        return 1
    if not store.is_ready(spec.engine_id):
        print(f"the model in {paths.model_dir(spec.engine_id)} is missing or incomplete "
              "(spike\\download_model.py downloads it)", file=sys.stderr)
        return 1
    install = {
        "engine_id": spec.engine_id,
        "revision": spec.revision,
        "torch": spec.torch,
        "torchvision": spec.torchvision,
        "transformers": spec.transformers,
        "tier": "development",
        "device": "cuda",
        "dtype": "bfloat16",
        "torch_index": "https://download.pytorch.org/whl/cu128",
        "python": str(python),
        "worker_script": str(worker),
    }
    target = paths.engine_dir() / "install.json"
    paths.atomic_write_text(target, json.dumps(install, indent=1) + "\n")
    print(f"wrote {target}")
    print(f'now set:  $env:OWLOCR_HOME = "{data_root}"; $env:OWLOCR_CONFIG = "{data_root / "config"}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_dev_engine.py -q`
Expected: `2 passed`.
Then configure the development engine for real (writes only inside the git-ignored `engine\` folder, loads nothing):
Run: `py -3.11 scripts\dev_engine.py`
Expected: `wrote %USERPROFILE%\Desktop\OCR project\engine\engine\install.json` and the `$env:` line to use.

- [ ] **Step 5: Commit**

```
git add scripts/dev_engine.py tests/test_dev_engine.py
git commit -m "Add development engine configuration script" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 28: Accuracy tests (design 1.3)

**Files:**
- Create: `tests/scoring.py`
- Test: `tests/test_accuracy_recorded.py`, `tests/test_accuracy_gpu.py`

**Interfaces:**
- Consumes: `parse.parse_raw`, `layout.arrange`, `document.Page`, `document.plain_text`, `process.process_page`, `process.ProcessOptions`, `pages.PageSource`, `client.default_engine`, `hardware.free_vram_mib`, `REQUIRED_FREE_VRAM_MIB`; rapidfuzz.
- Produces: `tests/scoring.py` with `CZECH`, `UPRIGHT` (pages 01 to 08), `MAX_CER = 0.03`, `MIN_ACCENTS = 0.95`, `normalize()`, `cer()`, `accents()`, `score(truth_text, ocr_text) -> {"cer", "accents_right", "accents_total"}`. Thresholds: CER at most 3 % on every upright page; accents at least 95 % over all upright pages together (per page is impossible: small print had 141/164 in the spike, see Contract notes).

`test_accuracy_recorded.py` runs the pipeline text path on the Quality output recorded in the spike and reproduces the spike's numbers (letter 0.38 %, small print 2.59 %). `test_accuracy_gpu.py` is marked `gpu` and `slow`, is excluded from normal runs, and skips itself when less than 9500 MiB of VRAM is free or the development engine is not set up. Do NOT run it in this task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_accuracy_recorded.py`:

```python
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
```

Create `tests/test_accuracy_gpu.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_accuracy_recorded.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.scoring'`.

- [ ] **Step 3: Write minimal implementation**

Create `tests/scoring.py`:

```python
"""Accuracy measures for the fixture pages (same method as spike/score.py).

CER = character error rate = edit distance / length of the correct text, after collapsing
whitespace. Accents = share of the Czech accented letters of the correct text that came out right.
"""
import re
import unicodedata

from rapidfuzz.distance import Levenshtein

CZECH = set("ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ")
UPRIGHT = ("01_letter_clean", "02_textbook_clean", "03_small_print_clean", "04_table_clean",
           "05_letter_poor_scan", "06_textbook_poor_scan", "07_letter_phone_photo", "08_screenshot")
MAX_CER = 0.03                 # design 1.3: at most 3 % per page
MIN_ACCENTS = 0.95             # design 1.3: at least 95 % of accented letters, over all pages


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def cer(truth: str, hyp: str) -> float:
    return Levenshtein.distance(truth, hyp) / max(len(truth), 1)


def accents(truth: str, hyp: str) -> tuple[int, int]:
    """(right, total) over the accented letters of the correct text."""
    wrong = set()
    for op, i, _ in Levenshtein.editops(truth, hyp):
        if op in ("replace", "delete"):
            wrong.add(i)
    total = [i for i, c in enumerate(truth) if c in CZECH]
    return sum(1 for i in total if i not in wrong), len(total)


def score(truth_text: str, ocr_text: str) -> dict:
    truth, hyp = normalize(truth_text), normalize(ocr_text)
    right, total = accents(truth, hyp)
    return {"cer": cer(truth, hyp), "accents_right": right, "accents_total": total}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_accuracy_recorded.py tests/test_accuracy_gpu.py -q`
Expected: `4 passed, 1 deselected` (the GPU test is deselected by the default `-m 'not gpu'`).

- [ ] **Step 5: Commit**

```
git add tests/scoring.py tests/test_accuracy_recorded.py tests/test_accuracy_gpu.py
git commit -m "Add accuracy tests: recorded output and GPU acceptance test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 29: End-to-end check

**Files:**
- Modify: `owlocr/cli.py` (append the `__main__` block)
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: everything above; `tests/fake_worker.py` as the engine through `install.json`.
- Produces: `python -m owlocr.cli` runs `main()` and exits with its code.

- [ ] **Step 1: Write the failing test**

Create `tests/test_end_to_end.py`:

```python
"""The command line from start to finish, as a user runs it, with the fake worker as engine."""
import json
import os
import subprocess
import sys

from owlocr import paths
from tests.conftest import FAKE_WORKER, REPO


def test_cli_end_to_end(owl_env, tmp_path):
    paths.atomic_write_text(paths.engine_dir() / "install.json", json.dumps({
        "engine_id": "unlimited_ocr", "python": sys.executable, "worker_script": str(FAKE_WORKER),
        "device": "cpu"}))
    out = tmp_path / "out"
    run = subprocess.run(
        [sys.executable, "-m", "owlocr.cli", "tests/fixtures/pages/01_letter_clean.png",
         "--formats", "md,txt", "--out", str(out)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120, env=dict(os.environ))
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines() == [str(out / "01_letter_clean.md"), str(out / "01_letter_clean.txt"),
                                       str(out / "01_letter_clean.owl.json")]
    assert (out / "01_letter_clean.md").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert (out / "01_letter_clean.txt").read_text(encoding="utf-8") == "fake text for page_0000.png\n"
    assert "01_letter_clean.png: page 1 (1/1) ocr" in run.stderr
    assert not (owl_env["home"] / "engine" / "worker.pid").exists()     # the worker was stopped
    log = (owl_env["home"] / "logs" / "engine.log").read_text(encoding="utf-8")
    assert "engine start" in log
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.11 -m pytest tests/test_end_to_end.py -q`
Expected: FAIL — `AssertionError` on `run.stdout.splitlines() == [...]` (the module runs but never calls `main()`, so it prints nothing).

- [ ] **Step 3: Write minimal implementation**

Append to the end of `owlocr/cli.py`:

```python
if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.11 -m pytest tests/test_end_to_end.py -q`
Expected: `1 passed`.
Run the whole suite: `py -3.11 -m pytest -q`
Expected: `216 passed, 1 deselected` (about 30 s; with no spike venv: `213 passed, 3 skipped, 1 deselected`).

Manual check with the real engine — **uses the graphics card; only when the owner asks for it and at least 9500 MiB of VRAM are free** (check with `nvidia-smi --query-gpu=memory.free --format=csv`). In PowerShell, from the repository root:

```
py -3.11 scripts\dev_engine.py
$env:OWLOCR_HOME = "%USERPROFILE%\Desktop\OCR project\engine"
$env:OWLOCR_CONFIG = "%USERPROFILE%\Desktop\OCR project\engine\config"
py -3.11 -m owlocr.cli tests\fixtures\pages\01_letter_clean.png --formats md,txt --out "%USERPROFILE%\Desktop\OCR project\engine\check"
```

Expected: exit code 0; stdout lists `engine\check\01_letter_clean.md`, `.txt` and `.owl.json`; stderr shows `01_letter_clean.png: page 1 (1/1) ocr, ... s` (about 20 s including 5 s model load); the Markdown starts with `Vážená paní doktorko Šťastná,` and ends with `Ústí nad Labem, 28. září 2026`; afterwards Task Manager shows no `python.exe` of the engine. The acceptance test of design 1.3 on the real engine is then: `py -3.11 -m pytest -m gpu tests/test_accuracy_gpu.py -v -s` (about 3 minutes; prints CER and accents per page).

- [ ] **Step 5: Commit**

```
git add owlocr/cli.py tests/test_end_to_end.py
git commit -m "Make owlocr.cli runnable as a module and add the end-to-end test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Contract notes

Guaranteed for plan B (plan B relies on these; each has a test):

1. `EngineError.kind` is `"died"` when the worker process dies (pending call and later calls until `load()`/`start()`), and `"out_of_memory"` on a CUDA (or CPU) out-of-memory in `load` or `ocr`. `process_page` never catches `EngineError`; it reaches the caller (`test_engine_errors_reach_the_caller`, `test_crash_is_died_and_restart_works`, `test_out_of_memory_is_an_engine_error`). Consequence: the retries of design 5.7 (Quality out of memory -> Fast with warning `out_of_memory_fast`; worker died -> restart once) live in the caller: in plan A in `owlocr/cli.py` (`_read_page`), in plan B in the runner.
2. Constructing `SubprocessEngine(...)` starts no process; only `start()` does (`load()` calls `start()` when the worker is not running). `engine.device` (`"cuda"` or `"cpu"`) and `engine.dtype` are public attributes (`test_constructing_does_not_start_a_process`).
3. The worker gets `os.environ` of the app merged with the `env` argument (the argument wins), so `FAKE_WORKER` set in the app's environment reaches `tests/fake_worker.py` (`test_app_environment_reaches_the_worker`).
4. The fake worker reports its own pid in `ready`; in `slow` mode it checks for cancel every 0.1 s, so `cancel` takes effect within about 0.1 s (`test_cancel_returns_partial_result`).
5. `tests/conftest.py` sets `OWLOCR_HOME` and `OWLOCR_CONFIG` to fresh temp folders for every test (autouse fixture `owl_env`) and removes `FAKE_WORKER` from the environment.
6. `export_all` writes only the requested formats and never the `.owl.json` sidecar (the CLI and the plan B runner write it with `save_sidecar`) (`test_export_all_never_writes_the_sidecar`).
7. `SubprocessEngine.stop()` may be called from any thread at any moment. While `ocr_page` is blocked in another thread, `stop()` sends `shutdown`; the worker (real and fake) cancels the page being read and answers first, so the blocked `ocr_page` **returns a `PageResult` with `cancelled=True`** (partial text). Only when the worker has not exited within `timeout_s` is it killed; then the blocked call raises `EngineError("died")`. Plan B must handle both outcomes (`test_stop_from_another_thread_while_a_page_is_read` asserts the first).

Other notes on the contract and the design:

8. `.gitignore` had a bare `engine/` (and `models/`, `build/`, `output/`) pattern, which also ignored the `owlocr/engine/` package. Task 1 anchors them to the repository root (`/engine/` ...).
9. `is_blank` (design 7.2 says "darker than 128"): measured on the fixtures, `05_letter_poor_scan` has only 0.05 % pixels under 128 after the 3 px median filter (thin 150 dpi strokes on grey paper), so the fixed rule would skip a page full of text. Plan A counts pixels at least 80 levels darker than the paper (median brightness); the 0.2 % share and the median filter are kept. All ten fixtures classify correctly.
10. Design 1.3 "at least 95 % of accented letters": per page it cannot hold (spike small print 141/164 = 86 %), over all upright pages it is 798/834 = 95.7 %. The tests use CER at most 3 % per page and accents at least 95 % over all upright pages together.
11. `EngineError` has the constructor `EngineError(kind: str, message: str = "")` and a `.message` attribute besides the contract's `.kind`. `protocol` also exposes `REQUEST_FIELDS` / `EVENT_FIELDS`.
12. `install.json` is written by plan D; plan A reads `engine_id`, `device`, `dtype` and the optional development overrides `python`, `worker_script`, `model_dir`, `env`. `default_engine()` raises `not_installed` only when `install.json`, the Python or the worker script is missing; it does not check the model (that is `bootstrap.is_installed()` in plan D).
13. The venv's `Scripts\python.exe` is a launcher that runs the real interpreter as a child. The Job Object still covers both (verified), but the pid of `Popen` is not the worker's pid: `EngineInfo.pid` and `worker.pid` hold the pid the worker reports in `ready`. `worker.pid` also stores the process creation time, so `sweep_stale_worker` never kills an unrelated process that reused the pid. `client.py` uses the private helpers `lifetime._process_create_time` and `lifetime._terminate`.
14. The worker must move stdin off the standard handle (`detach_stdin`), otherwise `import torch` deadlocks against the reader thread (verified). Plan D copies `worker\owl_worker.py` unchanged.
15. `CUDA_VISIBLE_DEVICES=""` does not hide the GPU from torch on this PC; tests use `-1`.
16. `export_markdown` has no source parameter; image crops re-render the page from `Document.source_path`. When that file is gone, image blocks are left out.
17. Tall images cut into strips (design 7.1) and orientation handling have no plan A contract item; plan A reads such images whole. Left to plan C.
18. The store keeps the spike's manifest format (`"commit"` key), so the model already in `engine\models\unlimited_ocr` counts as ready without a new download. `download()` reports bytes (`on_progress(done, total)`) and raises `StoreError("cancelled")` on cancel.
19. `fake_worker.py`: besides the listed flags, `shutdown` cancels a page being read (as the real worker does); with `ignore_shutdown` it does not.
20. `export_all` with `docx` or `pdf` raises `NotImplementedError` before writing anything; the CLI then reports that input as failed (exit 1).
21. `find_inputs` skips files ending in `.ocr.pdf` (the app's own searchable PDFs) and, when searching a folder, the Markdown export's image crops (files in a `<stem>_images` folder that sits next to `<stem>.md`).
22. `settings.DEFAULTS["mode_default"]` is `"quality"` until plan D sets it by tier; `language_ui` defaults from the Windows UI language.
23. pytest's `addopts` deselects `gpu` by default; `-m gpu` on the command line overrides it.
24. A page that hits the time limit before its first token (GPU run 2026-09-28): the worker answers the `result` with `timed_out=True` (and `engine_exiting: true`) and exits; the client waits for the exit, so `ocr_page` returns that `timed_out` `PageResult` and the engine is then stopped. The next call raises `EngineError("not_loaded")`, not `"died"`. Callers load the engine again whenever `engine.loaded` is False before a page (plan A's `cli._read_page` and plan B's `_ensure_engine` do).
25. `adopt()` verifies a folder against the file set pinned in the registry (`EngineSpec.files`), never the folder's own manifest; `download()` uses the same pinned set, so it needs no Hugging Face file list and the ModelScope fallback works while Hugging Face is unreachable. The remote list is used only for a spec that pins no files.
26. `worker.pid` also records the owner (the app or CLI process that started the worker) with its creation time. `sweep_stale_worker()` leaves the worker and the file alone while that owner still runs, so a CLI run never kills the app's live worker; a file without the owner fields counts as stale, as before.

## Self-review

| Plan A item of the interface contract | Task |
|---|---|
| `owlocr/__init__.py` `__version__` | 1 |
| `owlocr/paths.py` (all 16 functions) | 3 |
| `owlocr/settings.py` `DEFAULTS`, `load`, `save`, `get`, `update`, `SettingsError` | 4 |
| `owlocr/engine/registry.py` `EngineSpec`, `UNLIMITED_OCR`, `get` | 5 |
| `owlocr/engine/protocol.py` `MODES`, `encode`, `decode`, `ProtocolError`, `EngineInfo`, `PageResult`, `EngineError` | 6 |
| `owlocr/hardware.py` `free_vram_mib`, `REQUIRED_FREE_VRAM_MIB` | 7 |
| `owlocr/engine/lifetime.py` `JobObject` (`__init__`, `assign`, `close`), `process_alive` | 8 |
| `tests/fake_worker.py` (CLI, protocol, 7 flags, raw file answer, default answer) | 9 |
| `owlocr/engine/client.py` `SubprocessEngine` (all methods, `loaded`) | 10 |
| `owlocr/engine/client.py` `sweep_stale_worker`, `default_engine` | 11 |
| Engine lifetime tests (design 5.6: killed app, stdin EOF, watchdog) | 12 (and 8) |
| `owlocr/engine/store.py` `manifest_path`, `is_ready`, `verify`, `StoreError` | 13 |
| `owlocr/engine/store.py` `fetch_remote_manifest`, `download` | 14 |
| `owlocr/engine/store.py` `adopt` | 15 |
| `worker/owl_worker.py` (stdin reader thread, watchdog, StoppingCriteria cancel and time limit, progress, generate wrapper, out of memory, never `save_results`) and `worker/requirements-engine.txt` | 16 |
| `owlocr/pipeline/document.py` `Flag`, `Block`, `Page`, `Document`, `to_json`, `from_json`, `save_sidecar`, `load_sidecar`, `plain_text`, `FURNITURE_LABELS` | 17 (tables in `plain_text`: 18) |
| `owlocr/pipeline/parse.py` `parse_raw`, `html_table_to_rows` | 18 |
| `owlocr/pipeline/pages.py` `IMAGE_SUFFIXES`, `SUPPORTED_SUFFIXES`, `PageSource`, `count_pages`, `list_pages`, `render_page`, `find_inputs` | 19 |
| `owlocr/pipeline/guards.py` `is_blank`, `is_runaway`, `trim_runaway` | 20 |
| `owlocr/pipeline/layout.py` `arrange` (basic) | 21 |
| `owlocr/pipeline/repair.py` `repair_block` stub; `owlocr/pipeline/spellcheck.py` `available`, `known`, `flag_suspicious`, `detect_language`, `dictionaries_dir` stubs | 21 |
| `owlocr/pipeline/process.py` `ProcessOptions`, `process_page`, `cleanup` | 22 |
| `owlocr/export/text.py` `export_text`, `document_text` | 23 |
| `owlocr/export/markdown.py` `export_markdown` | 24 |
| `owlocr/export/__init__.py` `FORMATS`, `export_all` (docx/pdf raise `NotImplementedError`) | 25 |
| `owlocr/cli.py` (arguments and exit codes 0/1/2) | 26, 29 |
| Scaffolding: `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, markers `gpu`/`slow`, `tests/conftest.py` with `OWLOCR_HOME`/`OWLOCR_CONFIG`, `LICENSE` | 1 |
| Fixtures moved from `spike/synthetic`, raw outputs of synthetic pages only | 2 |
| `scripts/dev_engine.py` | 27 |
| GPU accuracy test (design 1.3, skipped under 9500 MiB free) | 28 |
| End-to-end CLI check with the fake worker; manual real-engine command | 29 |

Placeholder check: the plan was searched (case-insensitive) for `TBD`, `TODO`, `add error handling`, `similar to task` and `write tests for the above`; none occur. The only `...` in code blocks are literal sample data (`raw="<|det|>..."` in `tests/samples.py`) and prose in docstrings. Every code step contains the complete file (or the complete appended part), and every test and implementation was run on this PC before it was written into the plan: the full suite gave `216 passed, 1 deselected` (GPU test not run; the real worker was started only with `CUDA_VISIBLE_DEVICES=-1`, the OCR model was never loaded).
