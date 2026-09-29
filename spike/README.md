# spike/ — THROWAWAY

Feasibility test from 2026-09-28. Answers one question before the real plan is written:

> Does Baidu Unlimited-OCR read **Czech** well enough, and how fast / how much VRAM
> does it need on this PC (RTX 4080 SUPER, Windows 11, transformers 4.57.1 + torch 2.10.0+cu128)?

Nothing here is app code. It will be deleted or replaced once the plan exists.

| File | What it does | Uses GPU |
|---|---|---|
| `download_model.py` | Downloads the pinned model revision once into `engine\models\unlimited_ocr` (project folder, ignored by git), verifies every file's checksum, writes `manifest.json` last | no |
| `make_synthetic.py` | Renders Czech test pages with known correct text into `spike/synthetic/` | no |
| `run_ocr.py` | Runs the model over `spike/synthetic/` and `samples/`, records seconds per page and peak VRAM into `spike/out/` | **yes** |
| `score.py` | Compares OCR output with the known text: character error rate and accuracy on Czech diacritics | no |

Run order: `download_model.py` → `make_synthetic.py` → `run_ocr.py` → `score.py`, all with `spike\.venv\Scripts\python.exe`.

Real sample documents go into `samples/` in the project root (ignored by git, they may be private).
