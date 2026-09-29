# Owl OCR — interface contract

Binding for all four build plans. Names, parameters and return types here are used **verbatim**.
A plan may add private helpers (leading underscore) but may not rename or reshape anything below.
Design: `2026-09-28-owl-ocr-design.md`. Owner column says which plan creates the item.

All paths are `pathlib.Path`. All text files are UTF-8. All JSON written to disk goes through
`owlocr.paths.atomic_write_text`.

## owlocr/__init__.py — plan A

```python
__version__ = "0.1.0"
```

## owlocr/paths.py — plan A

```python
def config_dir() -> Path            # env OWLOCR_CONFIG, else %APPDATA%\OwlOCR ; created if missing
def data_root() -> Path             # env OWLOCR_HOME, else config_dir()/location.txt, else %LOCALAPPDATA%\OwlOCR
def set_data_root(path: Path) -> None          # writes location.txt
def engine_dir() -> Path            # data_root()/engine
def engine_python() -> Path         # engine_dir()/venv/Scripts/python.exe
def worker_dir() -> Path            # engine_dir()/worker
def models_dir() -> Path            # data_root()/models
def model_dir(engine_id: str = "unlimited_ocr") -> Path
def hf_home() -> Path               # data_root()/hf_home
def work_dir(job_id: str) -> Path   # data_root()/work/<job_id> ; created if missing
def logs_dir() -> Path
def queue_file() -> Path            # data_root()/queue.json
def settings_file() -> Path         # config_dir()/settings.json
def resource_path(rel: str) -> Path # bundled files; honours sys._MEIPASS
def atomic_write_text(path: Path, text: str) -> None   # tmp file in same folder + os.replace
def unique_path(path: Path) -> Path # appends _1, _2 ... before the suffix until free
```

## owlocr/settings.py — plan A (keys), plan B (UI)

```python
DEFAULTS: dict   # exactly the keys and defaults of design section 10.3, plus "personal_words": []
def load() -> dict                  # DEFAULTS overlaid with the file; unknown keys dropped
def save(values: dict) -> None      # validates, then atomic write
def get(key: str)
def update(changes: dict) -> dict   # returns the new full settings
class SettingsError(ValueError)
```

## owlocr/engine/registry.py — plan A

```python
@dataclass(frozen=True)
class EngineSpec:
    engine_id: str            # "unlimited_ocr"
    repo: str                 # "baidu/Unlimited-OCR"
    revision: str             # 40-char commit
    ignore: tuple[str, ...]
    weights_sha256: str
    modelscope_repo: str      # "PaddlePaddle/Unlimited-OCR"
    torch: str                # "2.10.0"
    torchvision: str          # "0.25.0"
    transformers: str         # "4.57.1"
    files: tuple[tuple[str, int, str | None, str | None], ...] = ()
                              # pinned file set: (path, size, sha256 for LFS files, git blob sha1
                              # for the others); adopt() and download() use it when present
UNLIMITED_OCR: EngineSpec
def get(engine_id: str) -> EngineSpec
```

## owlocr/engine/protocol.py — plan A

```python
MODES = ("quality", "fast")
def encode(message: dict) -> str            # one line, ensure_ascii=False, ends with "\n"
def decode(line: str) -> dict               # raises ProtocolError on bad JSON or missing keys
class ProtocolError(ValueError)

@dataclass
class EngineInfo:
    pid: int; torch: str; transformers: str; cuda_available: bool; gpu_name: str | None

@dataclass
class PageResult:
    text: str; seconds: float; prefix_tokens: int; output_tokens: int
    hit_token_cap: bool; cancelled: bool; timed_out: bool; peak_vram_mib: int

class EngineError(RuntimeError):
    kind: str        # 'out_of_memory' | 'bad_image' | 'not_loaded' | 'internal' | 'died' | 'not_installed'
```

Message fields are exactly those of design section 5.4.

## owlocr/engine/lifetime.py — plan A

```python
class JobObject:
    def __init__(self) -> None              # CreateJobObjectW + KILL_ON_JOB_CLOSE
    def assign(self, pid: int) -> None
    def close(self) -> None
def process_alive(pid: int) -> bool
```

## owlocr/engine/client.py — plan A

```python
class SubprocessEngine:
    engine_id = "unlimited_ocr"
    def __init__(self, python: Path, worker_script: Path, model_dir: Path,
                 device: str, dtype: str, log_file: Path, env: dict | None = None) -> None
    def start(self) -> EngineInfo
    def load(self) -> float                 # seconds
    def ocr_page(self, image: Path, mode: str, max_new_tokens: int = 6000,
                 time_limit_s: float = 300.0,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> PageResult
    def unload(self) -> None
    def stop(self, timeout_s: float = 5.0) -> None
    def is_running(self) -> bool
    @property
    def loaded(self) -> bool
def sweep_stale_worker() -> None            # reads engine_dir()/worker.pid
def default_engine() -> SubprocessEngine    # built from paths + install.json; raises EngineError('not_installed')
```

## owlocr/engine/store.py — plan A

```python
def manifest_path(engine_id: str = "unlimited_ocr") -> Path
def is_ready(engine_id: str = "unlimited_ocr", deep: bool = False) -> bool
def fetch_remote_manifest(spec: EngineSpec) -> dict[str, dict]   # path -> {size, sha256, git_sha1}
def download(spec: EngineSpec, on_progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None) -> None      # resumable; writes manifest last
def verify(engine_id: str = "unlimited_ocr") -> dict[str, str]   # path -> problem; empty dict = good
def adopt(folder: Path, spec: EngineSpec, move: bool = True) -> None
class StoreError(RuntimeError)
```

## owlocr/engine/bootstrap.py — plan D

```python
STAGES = ("tools", "python", "venv", "torch", "deps", "model", "worker", "patch", "selftest", "mark")
@dataclass
class StageEvent:
    stage: str; state: str      # 'start' | 'progress' | 'done' | 'skipped' | 'failed'
    done: int; total: int; message: str
def install_path() -> Path                       # engine_dir()/install.json
def is_installed() -> bool                       # install.json matches pins and store.is_ready()
def read_install() -> dict | None
def run(tier: "Tier", on_event: Callable[[StageEvent], None],
        cancel: threading.Event | None = None) -> None
def remove_engine() -> None
class BootstrapError(RuntimeError)
```

## owlocr/hardware.py — plan D

```python
@dataclass
class Gpu:
    name: str; driver: str; vram_total_mib: int; vram_free_mib: int; compute_cap: float | None
@dataclass
class Tier:
    name: str            # 'gpu_full' | 'gpu_reduced' | 'cpu' | 'unsupported'
    device: str          # 'cuda' | 'cpu'
    dtype: str           # 'bfloat16' | 'float32'
    default_mode: str    # 'quality' | 'fast'
    torch_index: str     # URL
    reason: str
def probe_gpus() -> list[Gpu]
def ram_total_mib() -> int
def free_vram_mib() -> int | None        # None when there is no NVIDIA GPU
def choose_tier(gpus: list[Gpu], ram_mib: int) -> Tier
REQUIRED_FREE_VRAM_MIB = {"quality": 9500, "fast": 7500}
```

Plan A needs `free_vram_mib` and `REQUIRED_FREE_VRAM_MIB` before plan D exists: plan A creates
`hardware.py` with exactly these two items; plan D adds the rest to the same file.

## owlocr/pipeline/document.py — plan A

`Flag`, `Block`, `Page`, `Document` exactly as in design section 8, plus:

```python
def to_json(doc: Document) -> str
def from_json(text: str) -> Document
def save_sidecar(doc: Document, path: Path) -> None
def load_sidecar(path: Path) -> Document
def plain_text(page: Page, keep_furniture: bool = False) -> str
FURNITURE_LABELS = ("page_number", "header", "footer")
```

## owlocr/pipeline/pages.py — plan A

```python
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + (".pdf",)
@dataclass
class PageSource:
    index: int
    kind: str                  # 'scan' | 'born_digital' | 'image'
    text_layer: str | None     # text of the PDF page, if any
def count_pages(path: Path) -> int
def list_pages(path: Path) -> list[PageSource]
def render_page(path: Path, index: int, dpi: int, out_png: Path) -> tuple[int, int]   # width, height in px
def find_inputs(paths: list[Path]) -> list[Path]   # expands folders recursively, keeps supported files, sorted
```

## owlocr/pipeline/parse.py — plan A

```python
def parse_raw(raw: str) -> list[Block]      # Block.text == Block.raw_text, flags empty
def html_table_to_rows(html: str) -> list[list[str]] | None   # None when rowspan/colspan present
```

## owlocr/pipeline/guards.py — plan A (blank, runaway, empty), plan C (orientation)

```python
def is_blank(image: Path) -> bool
def is_runaway(text: str, hit_token_cap: bool) -> bool
def trim_runaway(text: str) -> str
def looks_sideways(image: Path) -> bool                      # plan C
def dictionary_hit_rate(text: str, language: str) -> float   # plan C ; 1.0 when no dictionary
def best_rotation(image: Path, engine, language: str) -> int # plan C ; 0, 90, 180 or 270
```

## owlocr/pipeline/layout.py — plan A (basic), plan C (caption move, dictionary-aware de-hyphenation)

```python
def arrange(blocks: list[Block], language: str = "cs") -> list[Block]
```

## owlocr/pipeline/repair.py — plan C

```python
def repair_block(block: Block, language: str, personal_words: set[str]) -> Block
```

## owlocr/pipeline/spellcheck.py — plan C

```python
def available(language: str) -> bool
def known(word: str, language: str) -> bool     # True when no dictionary is installed
def flag_suspicious(block: Block, language: str, personal_words: set[str]) -> Block
def detect_language(text: str) -> str           # 'cs' | 'en'
def dictionaries_dir() -> Path                  # data_root()/dictionaries
```

Plan A ships `repair.py` and `spellcheck.py` as pass-through stubs with these exact signatures
(`repair_block` and `flag_suspicious` return the block unchanged, `available` returns False,
`known` returns True, `detect_language` returns "cs"). Plan C replaces the bodies.

## owlocr/pipeline/process.py — plan A

```python
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

def process_page(source: Path, page: PageSource, engine, options: ProcessOptions, scratch: Path,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> Page
def cleanup(page: Page, options: ProcessOptions) -> Page      # no-op slot for the later add-on
```

## owlocr/export/*.py — plan A (markdown, text), plan C (docx, searchable_pdf)

```python
# markdown.py
def export_markdown(doc: Document, out: Path, page_comments: bool = False,
                    keep_furniture: bool = False, suspicious_appendix: bool = False) -> Path
# text.py
def export_text(doc: Document, out: Path, keep_furniture: bool = False) -> Path
def document_text(doc: Document, keep_furniture: bool = False) -> str      # used for clipboard
# docx.py
def export_docx(doc: Document, out: Path, page_breaks: bool = False, keep_furniture: bool = False) -> Path
# searchable_pdf.py
def export_searchable_pdf(doc: Document, source: Path, out: Path) -> Path
# __init__.py
FORMATS = ("md", "txt", "docx", "pdf")
def export_all(doc: Document, source: Path, formats: list[str], out_dir: Path, settings: dict) -> dict[str, Path]
```

Every exporter returns the path actually written (after `unique_path`). In plan A `export_all`
raises `NotImplementedError` for `docx` and `pdf`; plan C fills them in.

## owlocr/jobs/queue.py — plan B

```python
STATES = ("pending", "running", "paused", "done", "failed", "cancelled")
@dataclass
class Job:
    id: str; source: str; state: str; mode: str | None      # None = use the default
    pages_total: int; pages_done: int
    warnings: int; error: str | None
    outputs: dict[str, str]; seconds: float
    added: str; finished: str | None
class JobQueue:
    def __init__(self, path: Path) -> None     # loads; any 'running' job becomes 'pending'
    def add(self, sources: list[Path]) -> list[Job]
    def get(self, job_id: str) -> Job
    def all(self) -> list[Job]
    def next_pending(self) -> Job | None
    def update(self, job_id: str, **changes) -> Job
    def remove(self, job_id: str) -> None
    def reorder(self, ids: list[str]) -> None
    def clear_finished(self) -> None
```

## owlocr/jobs/runner.py — plan B

```python
class Runner:
    def __init__(self, queue: JobQueue, engine_factory: Callable[[], object],
                 settings_get: Callable[[], dict]) -> None
    def start(self) -> None          # begins or continues processing pending jobs
    def pause(self) -> None          # takes effect after the current page
    def cancel(self, job_id: str) -> None
    def stop_engine(self) -> None    # manual stop: pauses the queue, cancels the current page
                                     # (not counted as done), stops the engine; thread stays alive
    def shutdown(self) -> None       # stops the thread and the engine
    def status(self) -> dict         # {'engine': 'not_installed'|'stopped'|'loading'|'ready'|'busy',
                                     #  'running': bool, 'paused': bool, 'current_job': str | None,
                                     #  'current_page_tokens': int, 'vram_used_mib': int | None}
```

## HTTP API — plan B (all), plan D (wizard routes)

JSON in, JSON out. Errors: status 4xx/5xx with `{"error": "<message>"}`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{"ok": true, "version": "..."}` |
| GET | `/api/status` | | `Runner.status()` plus `{"installed": bool}` |
| GET | `/api/settings` | | settings |
| POST | `/api/settings` | changes | settings |
| GET | `/api/jobs` | | `{"jobs": [Job]}` |
| POST | `/api/jobs` | `{"paths": [str]}` | `{"jobs": [Job]}` |
| POST | `/api/jobs/<id>` | `{"mode": ...}` | Job |
| DELETE | `/api/jobs/<id>` | | `{}` |
| POST | `/api/jobs/<id>/cancel` | | Job |
| POST | `/api/jobs/<id>/retry` | | Job |
| POST | `/api/jobs/reorder` | `{"ids": [str]}` | `{}` |
| POST | `/api/jobs/clear` | | `{}` |
| POST | `/api/run/start` | | status |
| POST | `/api/run/pause` | | status |
| GET | `/api/jobs/<id>/document` | | Document JSON |
| POST | `/api/jobs/<id>/document` | `{"page": int, "block": int, "text": str}` | Block |
| GET | `/api/jobs/<id>/page/<n>.png` | | image |
| POST | `/api/jobs/<id>/export` | `{"formats": [str]}` | `{"outputs": {...}}` |
| GET | `/api/jobs/<id>/text` | | `{"text": str}` |
| GET | `/api/wizard/probe` | | `{"gpus": [...], "ram_mib": int, "tier": Tier, "data_root": str, "free_bytes": int}` |
| POST | `/api/wizard/location` | `{"path": str}` | `{"data_root": str, "free_bytes": int}` |
| POST | `/api/wizard/adopt` | `{"path": str}` | `{"ok": true}` |
| POST | `/api/wizard/install` | | `{"started": true}` |
| POST | `/api/wizard/cancel` | | `{}` |
| GET | `/api/wizard/progress` | | `{"events": [StageEvent], "running": bool, "error": str | None}` |
| POST | `/api/engine/stop` | | status — **plan B** (manual stop, calls `Runner.stop_engine()`) |
| POST | `/api/engine/verify` | | `{"problems": {...}}` |
| POST | `/api/engine/remove` | | `{}` |

## owlocr/web/server.py, bridge.py — plan B

```python
def create_app(runner: Runner, queue: JobQueue) -> flask.Flask
class Bridge:                                   # pywebview js_api
    def pick_files(self) -> list[str]
    def pick_folder(self) -> str | None
    def open_folder(self, path: str) -> None
    def copy_text(self, text: str) -> None
```

## owlocr/cli.py — plan A

```
python -m owlocr.cli <input> [<input> ...] [--mode quality|fast] [--formats md,txt]
                     [--out DIR] [--pages 1-5,9] [--dpi 200]
```

Exit code 0 on success, 1 when any input failed, 2 when the engine is not installed.

## worker/owl_worker.py — plan A

```
python owl_worker.py --parent-pid <pid>
```

Reads requests from stdin, writes events to stdout, per design 5.4. Exits on stdin EOF, on
`shutdown`, and when the parent process is gone.

## tests/fake_worker.py — plan A

Same command line and protocol as the real worker, no torch. Behaviour is chosen through the
environment variable `FAKE_WORKER`, a comma-separated list of:
`slow` (2 s per page, progress events), `crash_on_ocr`, `oom_on_quality`, `ignore_shutdown`,
`ignore_stdin_eof`, `empty`, `runaway`. It answers `ocr` with the content of
`<image path>.raw.txt` when that file exists, else with
`<|det|>text [100, 100, 900, 200]<|/det|>fake text for <image name>`.
