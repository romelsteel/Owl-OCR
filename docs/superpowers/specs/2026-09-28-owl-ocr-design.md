# Owl OCR — design

Date: 2026-09-28 · Status: approved direction, written from the planning conversation
Owner: Tomáš (GitHub `romelsteel`) · Repo: `romelsteel/owl-ocr` (private until first release)

Companion documents, read them before building:

- `docs/research/2026-09-27-unlimited-ocr-factsheet.md` — everything known about the model, with sources
- `docs/research/2026-09-28-spike-results.md` — what was measured on the target PC
- `docs/reference/wolfie/` — `app.py`, `index.html`, `build_exe.bat` of the sibling app whose skeleton is reused
- `spike/` — throwaway scripts that produced the measurements; working reference code for download, inference and scoring

---

## 1. What is being built

A Windows desktop app that turns scans, photos, screenshots and PDFs into text, fully offline, using
Baidu's open-source Unlimited-OCR model running on the user's own PC.

### 1.1 Requirements chosen by the owner

| # | Requirement | Decision |
|---|---|---|
| R1 | Inputs | scanned PDFs (mostly Czech), photos of pages, PDFs that already contain text, screenshots and other images |
| R2 | Outputs | Markdown, searchable PDF, plain text and copy to clipboard, Word (.docx) |
| R3 | Audience | public release on GitHub, any Windows 10/11 x64 PC |
| R4 | App shape | separate app; reuse the skeleton of Wolfie (Flask + pywebview) |
| R5 | Batches | queue: drop many files and folders, processed one by one, with progress, pause, resume, cancel |
| R6 | Distribution | Setup installer (.exe) and portable .zip |
| R7 | Identity | name "Owl OCR", pixel-art owl mascot, UI in Czech and English with a switch |
| R8 | Engine download | the engine (PyTorch + model, about 10 GB) is downloaded **once** and never again |
| R9 | Engine lifetime | the background engine process runs **only while the app is running** |
| R10 | Mode switch | the user can switch between **Quality** and **Fast** mode |
| R11 | Faithful OCR | output is what the page says; no AI rewriting in the core app |
| R12 | Cloud | no cloud services. Documents never leave the PC |
| R13 | Code signing | unsigned for v1; README explains the SmartScreen warning |
| R14 | Local cleanup | a later add-on (section 14) that only fixes OCR errors and formatting, never meaning |

### 1.2 Out of scope for v1

Handwriting, languages written in non-Latin scripts, macOS and Linux, one-shot multi-page inference,
automatic updates of the app, code signing, cloud sync, the local cleanup add-on.

### 1.3 Success criteria

1. A user with an NVIDIA card (8 GB VRAM or more) installs the app, completes the wizard once, drops a
   scanned Czech PDF and receives Markdown, text, Word and searchable PDF.
2. Second and later starts perform no download and need no network.
3. After the app window closes, no `python.exe` of the engine remains in Task Manager, including after
   a crash or a forced kill of the app.
4. On the pages in `tests/fixtures/pages/` (upright ones) Quality mode reaches a character error rate
   of at most 3% on every page, and gets at least 95% of accented letters right counted over all
   those pages together. (Per page the accent rule cannot hold: small print measured 86%.)
5. A 215-page book can be processed across several sittings: pause, close the app, reopen, resume.

---

## 2. Measured facts the design rests on

From the spike on the target PC (RTX 4080 SUPER 16 GB, Windows 11, torch 2.10.0+cu128, transformers 4.57.1).

| Fact | Value | Consequence |
|---|---|---|
| Czech accuracy, real scans | about 3 wrong words per 100 | good enough; correction step needed |
| Czech accuracy, generated pages, Quality | CER 0.3 to 2.6% | acceptance threshold in 1.3 |
| Quality vs Fast accuracy | Quality clearly better, especially small print (2.6% vs 6.5%) | Quality is the default |
| Quality vs Fast speed on GPU | the same, 36 to 42 tokens/s | the switch mainly saves VRAM and helps CPU users |
| Peak VRAM | Quality 7.2 to 9.0 GB, Fast 6.9 GB | free-VRAM check before loading |
| Time per book page | 25 to 42 s, dense pages up to 108 s | queue must survive restarts |
| Model load | 5 s | engine can be started lazily and stopped when idle |
| Rotated page | fails (CER 25 to 98%) | orientation must be fixed before OCR |
| Blank page | no invented text, returns one `image` block | still pre-check to save time |
| Multi-page in one pass | no speed gain, wrong number of page marks | page by page only |
| Download 6.68 GB over HTTPS without Xet | 60 s, verified in 5 s | plain HTTPS is the default path |
| Readiness check on later starts | 0.13 s, no network | R8 is achievable |
| GPU load while generating | about 37% | speed is limited by the model's Python code, not hardware |

Characteristic errors and how they are handled are listed in section 9.

---

## 3. Architecture

Three parts with hard boundaries.

```
+---------------------------- app process (owlocr.exe) -----------------------------+
|  pywebview window  <-->  Flask server (127.0.0.1)                                 |
|        UI (HTML/JS)          |                                                     |
|                              v                                                     |
|   jobs.queue  -->  jobs.runner  -->  pipeline (pages, guards, parse, repair)       |
|                        |                     |                                     |
|                        v                     v                                     |
|                 engine.client           export (md, txt, docx, pdf)                |
+------------------------|-----------------------------------------------------------+
                         | JSON lines over stdin/stdout, inside a Windows Job Object
+------------------------v---------------------------+
|  engine process: <data root>\engine\venv\python.exe |
|  worker\owl_worker.py  (torch + transformers + model)|
+-----------------------------------------------------+
```

| Part | Contains | Ships in the installer |
|---|---|---|
| App | UI, queue, pipeline, exports, setup wizard, engine client | yes, about 100 MB, no torch |
| Engine | Python 3.11, torch, transformers, model weights, worker script | no, installed by the wizard |
| Worker scripts | `owl_worker.py`, `device_patch.py` | yes, as data files; copied into the data root by the wizard |

Reasons for the split: small installer; app updates never touch the 10 GB engine; an engine crash or
out-of-memory does not take the app down; another engine can be added behind the same interface.

### 3.1 Technology

| Concern | Choice | Note |
|---|---|---|
| Language | Python 3.11 | same as the tested engine |
| Window | pywebview 6.x on WebView2 | as Wolfie |
| Local server | Flask 3.x on 127.0.0.1, random free port | as Wolfie |
| PDF reading and rendering | `pypdfium2` | Apache-2.0/BSD. **Not PyMuPDF**, which is AGPL |
| PDF writing (text layer) | `pikepdf` + `reportlab` | MPL-2.0, BSD |
| Images | Pillow | |
| Word export | `python-docx` | MIT |
| HTML table parsing | standard library `html.parser` | |
| Spell check | `spylls` (pure-Python Hunspell) + Czech dictionary | dictionary licence must be verified, see 9.3 |
| Tests | pytest | |
| Packaging | PyInstaller 6.x **onedir**, Inno Setup 6 | |
| Engine runtime install | `uv` (pinned version and checksum) | |
| App licence | MIT | third-party notices file required |

### 3.2 Source layout

```
owlocr/
  __init__.py            __version__
  __main__.py            entry point; starts server and window
  cli.py                 command-line use without the window
  paths.py               where config and data live
  settings.py            settings.json
  hardware.py            GPU/CPU/RAM probe, tier, torch index
  engine/
    protocol.py          message types of the JSON-lines protocol
    lifetime.py          Windows Job Object
    client.py            SubprocessEngine: start, ocr_page, cancel, stop
    store.py             model download, verification, manifest, adopt
    bootstrap.py         installs uv, Python, torch, dependencies
    registry.py          known engines and their pinned versions
  pipeline/
    document.py          Document, Page, Block dataclasses; sidecar JSON
    pages.py             input file -> page images; text-layer detection
    guards.py            blank page, orientation, runaway output
    parse.py             raw model output -> blocks
    layout.py            reading order, de-hyphenation, paragraphs
    repair.py            rule-based corrections
    spellcheck.py        Czech dictionary flags
    process.py           runs one page through all of the above
  export/
    markdown.py  text.py  docx.py  searchable_pdf.py
  jobs/
    queue.py             persistent queue
    runner.py            worker thread that drives the queue
  web/
    server.py            Flask routes
    bridge.py            pywebview js_api (file dialogs, clipboard, open folder)
    static/              index.html, app.js, wizard.js, style.css, i18n.js, owl sprites
worker/
  owl_worker.py          runs inside the engine venv
  device_patch.py        makes the model code device-agnostic
  requirements-engine.txt
tests/
  fixtures/pages/        the ten generated Czech pages with ground truth (moved from spike/synthetic)
  fake_worker.py         speaks the protocol without torch
packaging/
  owlocr.spec  installer.iss  build.py  THIRD_PARTY_NOTICES.md
```

One responsibility per file. Files that grow past about 300 lines are a signal to split.

---

## 4. Where things live on disk

| What | Path | Override |
|---|---|---|
| Config dir (small files) | `%APPDATA%\OwlOCR\` | env `OWLOCR_CONFIG` |
| `settings.json`, `location.txt` | in the config dir | |
| Data root (large files) | path stored in `location.txt`; default `%LOCALAPPDATA%\OwlOCR\` | env `OWLOCR_HOME` wins over everything |
| Engine runtime | `<data root>\engine\` with `tools\uv.exe`, `python\`, `venv\`, `worker\` | |
| Model | `<data root>\models\unlimited_ocr\` | |
| Hugging Face caches | `<data root>\hf_home\` | |
| Queue | `<data root>\queue.json` | |
| Sidecars of unfinished jobs | `<data root>\work\<job id>\` | |
| Logs | `<data root>\logs\` | |

Rules:

- The folder name of the model must stay `unlimited_ocr`. transformers caches remote code by folder
  basename, and two folders with the same basename would collide.
- All Hugging Face environment variables are set **before** the first import of `huggingface_hub` or
  `transformers`, because they are read at import time.
- The engine never writes inside the installation folder.

### 4.1 Development trap: redirected AppData

Tools started from the Claude desktop app get writes to `%LOCALAPPDATA%` and `%APPDATA%` redirected
into `AppData\Local\Packages\Claude_...\LocalCache\`. A program the user starts normally does not see
those files. During development and in every test, set `OWLOCR_HOME` and `OWLOCR_CONFIG` to real
paths. The repository uses `engine\` in the project root as the development data root (ignored by
git); it already holds the verified model in `engine\models\unlimited_ocr\`.

---

## 5. Engine

### 5.1 Pinned versions

| Item | Value |
|---|---|
| Model repo | `baidu/Unlimited-OCR` |
| Revision | `07dea832e22aefee32ad281d4b80551282e1c168` |
| Weights file | `model-00001-of-000001.safetensors`, 6,672,547,120 bytes, sha256 `2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6` |
| Python | 3.11 |
| torch / torchvision | 2.10.0 / 0.25.0 |
| transformers | 4.57.1 exactly. 5.x breaks the model's imports |
| tokenizers | `>=0.22,<0.23` |
| huggingface_hub | `>=0.34,<1.0` |
| Others | Pillow 12.1.1, einops 0.8.2, addict 2.4.0, easydict 1.13, matplotlib 3.10.8, psutil 7.2.2, numpy `<3`, safetensors `>=0.4.3`, accelerate |

Download skips `assets/*`, `wheel/*`, `*.pdf`, `*.gif`, `.gitattributes`. Payload 6.68 GB in 14 files.

### 5.2 Calling the model

```python
tok = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True, local_files_only=True)
model = AutoModel.from_pretrained(model_dir, trust_remote_code=True, use_safetensors=True,
                                  dtype=torch.bfloat16, local_files_only=True).eval().cuda()
text = model.infer(tok, prompt="<image>document parsing.", image_file=png_path,
                   output_path=scratch_dir, max_length=8192,
                   no_repeat_ngram_size=35, ngram_window=128, eval_mode=True,
                   base_size=1024, image_size=640, crop_mode=True)      # Quality
#                  base_size=1024, image_size=1024, crop_mode=False     # Fast
```

Facts the worker must respect:

- Use `AutoModel`. Only it injects `generate()` into the remote code.
- Never pass `attn_implementation`.
- `eval_mode=True` returns the text. Never use `save_results=True`: that path calls Python `eval()` on
  model output, which a crafted document could abuse.
- The n-gram values default to 0 in the model code. Always pass 35 and 128.
- `max_length` counts prompt plus output. The worker converts the app's `max_new_tokens` into
  `prefix_tokens + max_new_tokens`, where the prefix is learned by wrapping `generate`.
- `output_path` must be a writable folder even though nothing useful is written there.
- `image_file` must be a file path.
- The model code is hard-wired to CUDA (17 `.cuda()` calls, 3 autocast blocks, 4 forced bf16 casts).
  On CPU it needs `device_patch.py` and fp32.

### 5.3 Modes (R10)

| Mode | Model settings | Peak VRAM | Default for |
|---|---|---|---|
| **Quality** | 1024 px overview + 640 px tiles | up to 9.0 GB | GPUs with 10 GB VRAM or more |
| **Fast** | single 1024 px view | 6.9 GB | GPUs with 8 to 10 GB, and CPU |

The mode is a global setting with a per-job override in the queue. The UI states honestly what the
switch does: on a graphics card both modes take about the same time; Fast needs less memory and is
less accurate on small print; on a processor Fast is expected to be markedly quicker.

### 5.4 Protocol

One JSON object per line, UTF-8. The app writes requests to the worker's stdin and reads events from
its stdout. The worker writes nothing else to stdout; library output goes to stderr, which the app
appends to `logs\engine.log`.

Requests:

| `cmd` | Fields | Meaning |
|---|---|---|
| `load` | `id`, `model_dir`, `device` (`cuda`/`cpu`), `dtype` (`bfloat16`/`float32`) | load the model |
| `ocr` | `id`, `image`, `mode` (`quality`/`fast`), `max_new_tokens`, `time_limit_s` | read one page |
| `cancel` | `id` (of the running `ocr`) | stop generating |
| `unload` | `id` | free the model, keep the process |
| `ping` | `id` | liveness |
| `shutdown` | `id` | exit |

Events:

| `event` | Fields |
|---|---|
| `ready` | `pid`, `torch`, `transformers`, `cuda_available`, `gpu_name` — sent once after start |
| `loaded` | `id`, `seconds`, `vram_mib` |
| `progress` | `id`, `tokens` — at most every 0.5 s |
| `result` | `id`, `text`, `seconds`, `prefix_tokens`, `output_tokens`, `hit_token_cap`, `cancelled`, `timed_out`, `peak_vram_mib`; optional `engine_exiting` (see below) |
| `error` | `id`, `kind` (`out_of_memory`, `bad_image`, `not_loaded`, `internal`), `message` |
| `pong`, `unloaded`, `bye` | `id` |

Cancel and the time limit are implemented with a `StoppingCriteria` that checks a flag set by the
thread reading stdin. A cancelled or timed-out page still returns a `result` with what was generated.
The criteria run only once a token exists, so the same check also runs before every module of the
model: a page still in its first forward pass (vision encoder + prompt) is ended there with empty
text. A page that hits the time limit before its first token on the GPU means the GPU is far behind
(VRAM spilled into shared memory; found in the GPU run of 2026-09-28). Queued GPU work cannot be
cancelled, so the worker adds `engine_exiting: true` to that `result` and exits; the client waits
for the exit and the engine is then stopped (the caller loads it again for the next page).

### 5.5 Engine interface

```python
class Engine(Protocol):
    engine_id: str
    def start(self) -> EngineInfo: ...
    def load(self) -> None: ...
    def ocr_page(self, image: Path, mode: str, max_new_tokens: int, time_limit_s: float,
                 on_progress: Callable[[int], None] | None = None,
                 cancel: threading.Event | None = None) -> PageResult: ...
    def unload(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
```

`SubprocessEngine` is the only implementation in v1. Tests use it with `tests/fake_worker.py`.

### 5.6 Engine lifetime (R9)

The engine process exists only while the app runs. Four independent safeguards:

| # | Safeguard | Covers |
|---|---|---|
| 1 | The worker is started inside a **Windows Job Object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The app holds the only handle. When the app process ends for any reason, Windows closes the handle and kills the worker | crash, Task Manager kill, power-user mistakes |
| 2 | The worker exits when **stdin reaches end of file** | normal exit where the pipe closes |
| 3 | The worker runs a **parent watchdog** thread that checks every 2 s whether the app's process id is still alive and exits if not | anything that defeats 1 and 2 |
| 4 | On window close the app sends `shutdown`, waits up to 5 s, then terminates the process | clean shutdown |

Additional rules:

- **Lazy start.** The engine is started when the first job begins, not when the app opens.
- **Idle stop.** After `idle_stop_minutes` (default 10) without work the app stops the engine and the
  graphics memory is free again. Setting 0 keeps it loaded.
- **Manual stop.** A "Stop engine" button in the header stops the engine at once and frees the
  graphics memory, without waiting for the idle timer. When the engine is idle it simply stops. When
  a job is running the app asks for confirmation, then pauses the queue, cancels the page being read
  (it is read again on resume, finished pages are kept) and stops the engine. The engine starts
  again by itself the next time the queue is started.
- **Single instance.** A second launch of the app focuses the existing window.
- **Stale process sweep.** On start the app reads `<data root>\engine\worker.pid`; if that process is
  alive and is the worker, and the app or CLI process that started it (also recorded there) is no
  longer running, it is terminated.
- The worker is started with `CREATE_NO_WINDOW`.

### 5.7 Memory and failures

- Before `load` on a GPU the app reads free VRAM with `nvidia-smi`. Needed: 9,500 MiB for Quality,
  7,500 MiB for Fast. If less is free the job does not start and the UI says which amount is missing
  and suggests closing games or recording software. Without this check Windows silently spills into
  system RAM and pages take minutes.
- `out_of_memory` in Quality mode: retry the page once in Fast mode and mark the page with a warning.
  This retry lives in the caller (queue runner and command-line tool); `process_page` lets engine
  errors pass through.
- Worker died: restart it once and retry the page; a second death fails the job, not the queue.
- Environment for the worker: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, `HF_HOME`,
  `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `PYTHONIOENCODING=utf-8`, `PYTHONUNBUFFERED=1`.
- `expandable_segments` is not supported on Windows (torch logs a warning and ignores it), so it
  does not prevent fragmentation of the allocator cache. The worker therefore releases the CUDA
  cache (`torch.cuda.empty_cache()`) after every page; without it the eighth test page of the GPU run
  of 2026-09-28 grew past the dedicated VRAM and spilled into shared memory.

---

## 6. Setup wizard and one-time installation (R8)

Shown on first start and whenever the engine is not ready.

### 6.1 Steps the user sees

| Step | Content |
|---|---|
| 1 Welcome | what will happen, how much is downloaded (about 10 GB) and needed on disk (about 16 GB) |
| 2 Hardware | detected graphics card, VRAM, RAM, the tier chosen, expected speed |
| 3 Location | data root, free space on that drive, "Choose another folder", **"I already have the engine"** |
| 4 Install | stage list with progress and speed; can be paused; survives closing the app |
| 5 Self-test | reads a built-in test page and shows seconds per page |
| 6 Dictionaries | optional: Czech pre-ticked, English unticked, size and licence shown, can be skipped |
| 7 Done | |

### 6.2 Stages

| Stage | Action | Verified by |
|---|---|---|
| tools | download `uv` (pinned version) | sha256 |
| python | `uv python install 3.11` into `<data root>\engine\python` | runs `python --version` |
| venv | `uv venv` | |
| torch | `uv pip install torch==2.10.0 torchvision==0.25.0 --index-url <index>` | import test |
| deps | `uv pip install -r requirements-engine.txt` | import test |
| model | download the 14 files | size of every file, sha256 of LFS files, git blob sha1 of the others |
| worker | copy `worker\*.py` into `<data root>\engine\worker\` | |
| patch | only on CPU tier: run `device_patch.py` | sentinel line present |
| selftest | start the engine, read the test page | non-empty text containing the expected words |
| mark | write `install.json` | |

Each stage is idempotent and is skipped when its check already passes, so an interrupted installation
continues where it stopped.

### 6.3 Download once

1. `models\unlimited_ocr\manifest.json` is written **after** all files verify. It stores the revision
   and size and hash of every file.
2. `engine\install.json` is written after the self-test. It stores tier, torch index, versions.
3. On every start the app checks only: both files exist, revision and versions match the app's pins,
   every file in the manifest exists with the recorded size. No hashing, no network.
4. "Verify engine" in Settings re-hashes everything on request.
5. Downloads are resumable. Order of sources: huggingface.co over plain HTTPS with Range, then
   ModelScope (`PaddlePaddle/Unlimited-OCR`, identical weights). `HF_HUB_DISABLE_XET=1` is set.
6. Free space is checked before starting: 16 GB on the data drive.
7. **Adopt.** "I already have the engine" accepts a folder that contains `models\unlimited_ocr` or is
   itself that folder; the files are verified by hash, and the folder becomes or is moved into the
   data root. This is how the owner's existing download is reused.
8. An app update whose pins are unchanged reuses the engine untouched. When a pin changes, only the
   affected stage runs again.

### 6.4 Hardware tiers

| Tier | Condition | Device, dtype | Default mode | torch index |
|---|---|---|---|---|
| `gpu_full` | NVIDIA, compute capability 8.0 or higher, VRAM 10 GB or more | cuda, bf16 | Quality | cu128 |
| `gpu_reduced` | NVIDIA, compute capability 7.5 or higher, VRAM 8 to 10 GB | cuda, bf16 | Fast | cu128 |
| `cpu` | anything else with 16 GB RAM or more | cpu, fp32 | Fast | cpu |
| `unsupported` | less than 16 GB RAM and no usable GPU | | | |

Graphics cards and memory modules report slightly less than their nominal size, so the limits in
code are 9,984 MiB for "10 GB", 7,936 MiB for "8 GB" and 15,360 MiB for "16 GB RAM".

Driver rule: cu128 needs NVIDIA driver 570.65 or newer. With an older driver the wizard asks the user
to update it and offers the CPU tier meanwhile. Detection uses `nvidia-smi
--query-gpu=name,driver_version,memory.total,memory.free,compute_cap --format=csv,noheader,nounits`;
`compute_cap` is absent on old drivers, so a name table is the fallback; WMI `AdapterRAM` saturates
at 4 GB and must not be used for VRAM.

CPU speed and correctness are **unmeasured**. The build plan contains a CPU acceptance test before
release. Expected from other people's reports: about a minute per page with fp32.

---

## 7. Processing pipeline

For every input file:

```
input file -> pages.py -> for each page:
    text layer usable?  yes -> blocks from the text layer
                        no  -> guards (blank? rotated?) -> engine -> parse -> guards (runaway? empty?)
    -> layout -> repair -> spellcheck -> Page
-> Document -> sidecar JSON -> exports
```

### 7.1 Pages

| Input | Handling |
|---|---|
| PDF page with a full-page image (scan), with or without hidden text | render at 200 dpi, OCR. The hidden text of an earlier OCR is ignored: measured about 10 wrong words per 100 |
| PDF page that is born-digital (text, no full-page image) | take the text layer directly; exact and instant |
| Image file (png, jpg, jpeg, webp, bmp, tif, tiff) | EXIF orientation applied, then OCR |
| Multi-page TIFF | each frame is a page |

A page counts as a scan when one image covers at least 80% of the page area. Setting
`use_text_layer`: `born_digital` (default), `never`, `always`.

Images longer than 3.5 times their width (tall screenshots) are cut into overlapping strips, each
read separately, results joined.

### 7.2 Guards before OCR

| Guard | Rule | Action |
|---|---|---|
| Blank page | after a 3 px median filter, fewer than 0.2% of pixels clearly darker than the paper's own brightness. A fixed threshold such as 128 is wrong: a grey, low-contrast scan has almost no pixels that dark and would be skipped | skip OCR, page is empty |
| Rotated 90° or 270° | row-projection variance clearly lower than column-projection variance | rotate, then resolve 90 vs 270 by the post-OCR check |
| Upside down | cannot be seen before OCR | post-OCR check |

### 7.3 Guards after OCR

| Guard | Rule | Action |
|---|---|---|
| Empty | no text blocks on a non-blank page | retry once in the other mode |
| Runaway | token cap hit, or more than 5,000 characters compressing to under 5% with zlib | keep text up to the repetition, warn |
| Wrong orientation | share of words found in the dictionary under 50% | probe the three other rotations with a 120-token limit in Fast mode, take the best, re-read if another rotation wins |
| Time | `time_limit_s` exceeded (default 300) | keep what was generated, warn |

### 7.4 Parsing

Model output is a sequence of blocks: `<|det|>label [x1, y1, x2, y2]<|/det|>text`, coordinates 0 to
999 relative to the page image. The older form `<|ref|>label<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>`
is accepted as well. Known labels: `title`, `header`, `text`, `image`, `figure`, `image_caption`,
`table`, `table_caption`, `list`, `formula`, `page_number`, `footer`. Unknown labels are treated as
`text`. Tables arrive as HTML. Raw output is always kept in the sidecar.

### 7.5 Layout

- A caption block that the model placed in the middle of a sentence (previous block ends without
  sentence punctuation and the following block starts in lower case) is moved after the paragraph.
- Words split across lines are joined: `kaktu-\nsovitých` and `kaktu-sovitých` become `kaktusovitých`
  when the joined word is in the dictionary and the hyphenated form is not.
- `page_number`, `header` and `footer` blocks are kept in the sidecar and left out of Markdown, text
  and Word unless the setting `keep_page_furniture` is on.

---

## 8. Data model

```python
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
```

The sidecar `<name>.owl.json` stores the Document. It makes re-export possible without reading the
pages again, and it is what resume continues from. Written atomically (temporary file, then
`os.replace`).

---

## 9. Correction (part of the core app)

Measured error types and what the app does about each.

| Error | Example | Handling |
|---|---|---|
| `ď`, `ť` as letter plus apostrophe | `bud'`, `pojišt’ovnou` | rule R1 |
| `ď`, `ť` as plain letter | `kaprad` | dictionary: if the word is unknown and the variant with `ď`/`ť` is known, repair. `bud` for "buď" stays unrepaired: `bud` is itself in the Czech dictionary, so the rule of 9.1 forbids the change |
| Letter from another language | `także` | rule R2: flag; repair when replacing with the Czech look-alike gives a known word |
| Line-break hyphen left in | `kaktu-sovitých` | layout step 7.5 |
| Accent wrong, letter swapped, space lost, scrambled phrase | `bylinny`, `sporořyly`, `křápíku` | dictionary flags the word as suspicious; **no automatic change** |
| Dash type | `-` for `–` | rule R3: a hyphen between spaces becomes an en dash |
| Real word replaced by another real word | `významcové` for `výtrusnice` | cannot be detected. Addressed by the review view (section 10.4) and the unverified notice |

### 9.1 Principles

1. A repair is applied only when the result is a dictionary word and the original is not.
2. Every repair is recorded as a `Flag` with the original text. Repairs can be switched off.
3. Words in italics cannot be recognised, so Latin names are protected differently: a word is never
   flagged or repaired if it starts with a capital letter inside a sentence, or appears in the user's
   personal word list.
4. Suspicious words are marked in the review view and listed at the end of exports as an optional
   appendix. They are not marked inside the exported text.

### 9.2 Rules

| Rule | Pattern | Replacement |
|---|---|---|
| R1 | `d'`, `d’`, `t'`, `t’` inside or at the end of a word | `ď`, `ť` |
| R2 | letters outside the Czech alphabet and basic Latin (`ż ł ą ę ő ű ß ñ` ...) | flag; repair by look-alike map when the result is a known word |
| R3 | ` - ` between word characters | ` – ` |
| R4 | `,,` | `„` |
| R5 | ligatures `ﬁ ﬂ ﬀ ﬃ ﬄ` | plain letters |

### 9.3 Dictionary

Czech Hunspell dictionary (`cs_CZ.dic`, `cs_CZ.aff`) read with `spylls`. Licences were checked while
the plans were written: Czech is GPL, English is under the SCOWL licence. Both are therefore **never
bundled**. The app downloads them on demand from pinned commits of the LibreOffice dictionaries
project, verifies sha256, and keeps them in `<data root>\dictionaries\`. The wizard offers the Czech
one as an optional, pre-ticked step; Settings can install or remove either. Without a dictionary the rules that need one are skipped and the app still
works. English dictionary the same way. Language of a document: setting `document_language` with
values `auto`, `cs`, `en`; `auto` picks the dictionary with the higher hit rate on the first page.

---

## 10. User interface

Single window, 1100 x 820, minimum 760 x 560. Czech and English, switch in the header, choice
remembered. Text is kept in `i18n.js`; nothing visible is hard-coded in HTML.

### 10.1 Screens

| Screen | Content |
|---|---|
| Wizard | section 6.1 |
| Queue (main) | drop zone, list of jobs with progress, controls |
| Review | scan on the left, recognised text on the right |
| Settings | see 10.3 |
| About | versions, licences, engine state, data location, "Open logs" |

### 10.2 Queue screen

- Drop files or folders anywhere, or use the buttons "Add files" and "Add folder". Folders are
  searched recursively for supported types.
- Each job shows: name, pages done of total, state, estimated time left, mode, warnings count.
- Controls: start, pause, resume, cancel, remove, retry failed, clear finished, reorder by dragging.
- Header shows engine state: not installed, stopped, loading, ready, busy; with VRAM in use.
- **"Stop engine" button** beside the engine state, enabled while the state is loading, ready or
  busy (section 5.6, manual stop).
- **Mode switch** (R10): a two-position control "Quality / Fast" in the header sets the default; each
  job has its own override in its menu. Changing the default does not change jobs already running.
- Output formats: four checkboxes (Markdown, Text, Word, Searchable PDF), remembered.
- Finished job: buttons "Open folder", "Copy text", "Review".
- Pause takes effect after the current page. Cancel stops generating at once.
- Time left is estimated from the measured seconds per page of the pages already done.

### 10.3 Settings

| Setting | Values | Default |
|---|---|---|
| `language_ui` | `cs`, `en` | system language |
| `mode_default` | `quality`, `fast` | by tier |
| `output_location` | `next_to_source`, `folder` | `next_to_source` |
| `output_folder` | path | |
| `formats` | subset of `md`, `txt`, `docx`, `pdf` | `md` |
| `use_text_layer` | `born_digital`, `never`, `always` | `born_digital` |
| `document_language` | `auto`, `cs`, `en` | `auto` |
| `repairs_enabled` | bool | true |
| `append_suspicious_list` | bool | false |
| `keep_page_furniture` | bool | false |
| `idle_stop_minutes` | 0 to 120 | 10 |
| `time_limit_s` | 60 to 1800 | 300 |
| `pdf_dpi` | 150 to 300 | 200 |
| personal word list | text file | empty |

Engine actions in Settings: verify, reinstall, move to another folder, remove.

### 10.4 Review screen

Page by page: the scan with the block boxes drawn, the text beside it, suspicious words underlined,
repaired words marked with the original on hover. Clicking a block highlights its box. The text is
editable; edits are saved in the sidecar and used by the next export. A notice states that the text
was read by a machine and has not been checked.

### 10.5 Mascot

Pixel-art owl, in the style of Wolfie's wolf, drawn as SVG pixel grid. States: sleeping (engine
stopped), awake (ready), reading with moving eyes (busy), ruffled (error). One easter egg: clicking
the owl five times makes it hoot and turn its head.

### 10.6 Names of files written

`<source name>.md`, `.txt`, `.docx`, `<source name>.ocr.pdf`, `<source name>.owl.json`. Existing files
are never overwritten: `_1`, `_2` is appended. Images cut out of pages go to `<source name>_images\`.

---

## 11. Exports

| Format | Rules |
|---|---|
| Markdown | `title` -> `#`/`##` by size of the box height relative to body text; `text` -> paragraphs; `list` -> list items; `table` -> pipe table when the HTML has no `rowspan`/`colspan`, otherwise the HTML is kept; `formula` -> `$$ ... $$`; `image`/`figure` -> cut from the page image into the images folder and linked; captions in italics; pages separated by a blank line, optional `<!-- page N -->` comments |
| Text | blocks in order, one blank line between blocks, tables as tab-separated rows |
| Word | headings, paragraphs, real tables, images inline, page break between pages optional |
| Searchable PDF | the original page (or the image) stays exactly as it is; every block's text is added invisibly (text render mode 3) inside the block's box, font size fitted to the box, one line per estimated text line |

Searchable PDF positions text by **block**, not by word, because the model reports block boxes only.
Search and copy work; highlighting of a found word covers roughly the right area. This limit is
stated in the README.

Copy to clipboard uses the Text export.

---

## 12. Packaging and release

| Item | Decision |
|---|---|
| Build | `py packaging\build.py`; PyInstaller onedir; never run `.bat` files on the owner's PC |
| Installer | Inno Setup, per-user install into `%LOCALAPPDATA%\Programs\OwlOCR`, no administrator rights, Start Menu shortcut, uninstaller that offers to remove the engine and data |
| Portable | the same onedir folder zipped |
| GitHub release limit | 2 GiB per file; both artefacts are far below |
| Windowed build | `sys.stdout` and `sys.stderr` are `None`; replace with a null stream at start, as Wolfie does |
| Smoke test | every build is started once, must show the window and answer `/api/health` |
| Licences | `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md` listing every bundled package; the model folder keeps Baidu's MIT `LICENSE` and gets the Apache-2.0 text because `modeling_deepseekv2.py` carries an Apache header; a patched model file is marked as modified |
| README | what it does, hardware table, first-run download size, SmartScreen explanation with screenshots, accuracy numbers with the honest caveat, privacy statement |
| Going public | the repository history contains a research file with local paths and the owner's Windows user name. Before the repository becomes public, publish from a fresh history or rewrite it |
| Versioning | `0.1.0` first public release |

---

## 13. Testing

| Layer | How |
|---|---|
| Unit | pytest; everything except the worker runs without torch |
| Engine client | against `tests/fake_worker.py`, which speaks the protocol, can delay, crash, ignore shutdown, and emit out-of-memory |
| Lifetime | a test starts a helper "app" process that starts the fake worker, kills the helper, and asserts the worker is gone within 5 s |
| Pipeline | recorded raw outputs from the spike are fixtures for parse, layout, repair |
| Accuracy | marked `gpu`; reads `tests/fixtures/pages`, asserts the thresholds of 1.3; skipped when less than 9.5 GB VRAM is free |
| UI | browser smoke test through the Flask server with the fake worker |
| Build | smoke test of the packaged app |

Rule for anything run from a Claude session: set `OWLOCR_HOME` and `OWLOCR_CONFIG` to folders inside
the repository (section 4.1).

---

## 14. Local cleanup add-on (later, separate plan)

Goal: fix remaining OCR errors with a second local model. It is planned after the core app works.

Fixed constraints:

1. Runs locally. No cloud.
2. May change **only** words the dictionary flagged as suspicious, within their sentence as context.
3. Never touches words starting with a capital inside a sentence, Latin names, numbers, or anything
   in the personal word list.
4. A change is accepted only if the edit distance to the original is at most 2 characters and the
   result is a dictionary word. Otherwise the original stays.
5. Every change is a `Flag` and can be undone in the review screen.
6. Never runs at the same time as the OCR model; the engine unloads one before loading the other.

The core app leaves the slot ready: `pipeline/process.py` calls an optional `cleanup` stage after
`spellcheck`, which is a no-op in v1.

Open questions for its own spike: which model, its VRAM need, its Czech quality, speed.

---

## 15. Build plans

The work is divided into four plans. Each ends with software that works and can be tested.

| Plan | Delivers | File |
|---|---|---|
| A Foundation | engine worker, protocol, lifetime, client, model store, pipeline core, Markdown and text export, command-line tool | `docs/superpowers/plans/2026-09-28-plan-a-foundation.md` |
| B App | window, queue with pause and resume, settings, mode switch, review screen, Czech/English, mascot | `...-plan-b-app.md` |
| C Correction and exports | rules, dictionary, orientation and other guards, Word, searchable PDF | `...-plan-c-correction-exports.md` |
| D Installation and release | hardware probe, wizard, engine bootstrap, CPU tier, packaging, release | `...-plan-d-install-release.md` |

Order: A, then B and C in either order, then D.

## 16. Risks

| Risk | Mitigation |
|---|---|
| Undetectable word swaps in the output | review screen, unverified notice, README caveat |
| Upstream model is unmaintained | everything pinned; engine interface allows a replacement |
| CPU tier unmeasured | acceptance test in plan D; if it fails, v1 ships GPU-only and says so |
| Dictionary licence | checked in plan C; optional download as fallback |
| transformers 4.57.1 ages | engine has its own venv, isolated from the app |
| SmartScreen warning scares users | README with screenshots; signing can be added later |
| A page that loops for minutes | token cap, time limit, cancel |
