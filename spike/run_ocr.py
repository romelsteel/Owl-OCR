"""THROWAWAY spike: run Unlimited-OCR over the test pages, measure speed and VRAM.

    *** USES THE GPU. Close games / OBS first. ***

Usage:  spike\\.venv\\Scripts\\python.exe spike\\run_ocr.py [options]

  --dry-run        list pages, rasterize PDFs, run the pre-flight checks, then stop (no GPU)
  --load-cpu       with --dry-run: also load the model on the CPU to prove offline loading works
  --force          run even if less than 9 GB of VRAM is free
  --modes a,b      gundam,base (default: both)
  --multi 2,5,10   also measure one-shot multi-page chunks of these sizes
  --pdf-pages N    pages taken from each sample PDF (default 5)
  --only TEXT      only pages whose name contains TEXT

Writes spike/out/<page>.<mode>.raw.txt and spike/out/results.json (updated after every page).
"""
import io
import os
import sys
import json
import time
import pathlib
import argparse
import contextlib
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))
from download_model import APP, MODEL_DIR, is_ready  # one definition of where the engine lives

# Read at import time by huggingface_hub/transformers -> set first. Offline on purpose:
# the finished app must start with no network once the model is downloaded.
os.environ["HF_HOME"] = str(APP / "hf_home")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MODES = {
    "gundam": dict(base_size=1024, image_size=640, crop_mode=True),
    "base": dict(base_size=1024, image_size=1024, crop_mode=False),
}
SINGLE_PAGE_MAX_LENGTH = 8192  # prefix + output; a dense page is 1-2k output tokens
MIN_FREE_VRAM_MIB = 9000
PDF_DPI = 200


def gpu_memory() -> dict:
    q = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip().split(",")
    return dict(zip(("used_mib", "free_mib", "total_mib"), (int(x) for x in q)))


def collect_pages(pdf_pages: int, only: str | None) -> list[dict]:
    """Synthetic pages first (they have exact ground truth), then the user's samples."""
    pages = []
    for p in sorted((HERE / "synthetic").glob("*.png")):
        pages.append({"name": p.stem, "image": p, "kind": "synthetic", "truth": p.with_name(p.stem + ".gt.txt")})

    samples = ROOT / "samples"
    raster = OUT / "pages"
    for p in sorted(samples.rglob("*")) if samples.exists() else []:
        if p.suffix.lower() in IMAGE_EXT:
            pages.append({"name": f"sample_{p.stem}", "image": p, "kind": "sample", "truth": None})
        elif p.suffix.lower() == ".pdf":
            import fitz

            raster.mkdir(parents=True, exist_ok=True)
            with fitz.open(p) as doc:
                # Spread the picks over the whole document; the first pages are title and contents.
                n, k = doc.page_count, min(pdf_pages, doc.page_count)
                picks = range(n) if k == n else sorted({round(2 + j * (n - 5) / max(k - 1, 1)) for j in range(k)})
                for i in picks:
                    name = f"sample_{p.stem}_p{i + 1:03d}"
                    png = raster / f"{name}.png"
                    if not png.exists():
                        doc[i].get_pixmap(matrix=fitz.Matrix(PDF_DPI / 72, PDF_DPI / 72)).save(png)
                    # A born-digital PDF carries its own text: usable as approximate ground truth.
                    text = doc[i].get_text().strip()
                    truth = None
                    if len(text) > 50:
                        truth = raster / f"{name}.pdftext.txt"
                        truth.write_text(text, encoding="utf-8")
                    pages.append({"name": name, "image": png, "kind": "sample_pdf", "truth": truth})
    if only:
        pages = [p for p in pages if only in p["name"]]
    return pages


def load_model(device: str):
    import torch
    from transformers import AutoModel, AutoTokenizer

    d = str(MODEL_DIR.resolve())
    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(d, trust_remote_code=True, local_files_only=True)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    # AutoModel, not the class itself: only AutoModel injects generate() into remote code.
    model = AutoModel.from_pretrained(d, trust_remote_code=True, use_safetensors=True,
                                      dtype=dtype, local_files_only=True).eval()
    if device == "cuda":
        model = model.cuda()
    return tok, model, time.perf_counter() - t0


class GenerateProbe:
    """Wraps model.generate to learn what infer() does not report: prompt size,
    time spent generating, and whether the n-gram loop guard is really called."""

    def __init__(self, model):
        from transformers import LogitsProcessor

        self.stats = {}
        probe = self

        class Counting(LogitsProcessor):
            def __init__(self, inner):
                self.inner = inner

            def __call__(self, input_ids, scores):
                probe.stats["ngram_guard_calls"] += 1
                before = int((scores == float("-inf")).sum())
                scores = self.inner(input_ids, scores)
                probe.stats["ngram_guard_bans"] += int((scores == float("-inf")).sum()) - before
                return scores

        original = model.generate

        def generate(*args, **kw):
            self.stats = {"prefix_tokens": int(kw["input_ids"].shape[1]), "ngram_guard_calls": 0, "ngram_guard_bans": 0}
            if kw.get("logits_processor"):
                kw["logits_processor"] = [Counting(p) for p in kw["logits_processor"]]
            t0 = time.perf_counter()
            out = original(*args, **kw)
            self.stats["generate_s"] = time.perf_counter() - t0
            self.stats["output_tokens"] = int(out.shape[1]) - self.stats["prefix_tokens"]
            self.stats["hit_token_cap"] = int(out.shape[1]) >= kw["max_length"]
            return out

        model.generate = generate


def measure(fn) -> tuple:
    import torch

    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    try:
        result, error = fn(), None
    except torch.cuda.OutOfMemoryError as e:
        result, error = None, f"OUT OF MEMORY: {str(e)[:200]}"
        torch.cuda.empty_cache()
    torch.cuda.synchronize()
    return result, error, {
        "seconds": round(time.perf_counter() - t0, 2),
        "peak_vram_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
        "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--load-cpu", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--modes", default="gundam,base")
    ap.add_argument("--multi", default="")
    ap.add_argument("--pdf-pages", type=int, default=5)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    if not is_ready():
        print("Model is not downloaded/verified yet. Run download_model.py first.")
        return 1

    pages = collect_pages(a.pdf_pages, a.only)
    modes = [m for m in a.modes.split(",") if m in MODES]
    multi = [int(x) for x in a.multi.split(",") if x]
    gpu = gpu_memory()
    print(f"{len(pages)} pages x {len(modes)} modes | multi-page chunks: {multi or 'none'}")
    for p in pages:
        print(f"  {p['kind']:11s} {p['name']}")
    print(f"GPU memory: {gpu['used_mib']} MiB used, {gpu['free_mib']} MiB free of {gpu['total_mib']} MiB")

    if a.dry_run:
        if a.load_cpu:
            tok, model, s = load_model("cpu")
            n = sum(p.numel() for p in model.parameters())
            print(f"offline CPU load OK in {s:.1f} s, {n / 1e9:.2f} B parameters, generate() present: {hasattr(model, 'generate')}")
            print("tokenizer round trip:", tok.decode(tok.encode("Příliš žluťoučký kůň úpěl ďábelské ódy.", add_special_tokens=False)))
        print("dry run finished, GPU not used")
        return 0

    if gpu["free_mib"] < MIN_FREE_VRAM_MIB and not a.force:
        print(f"\nOnly {gpu['free_mib']} MiB of VRAM free, need {MIN_FREE_VRAM_MIB}. Close games/OBS, or pass --force.")
        print("(With too little VRAM Windows silently spills into system RAM and timings become meaningless.)")
        return 2

    import torch

    results = {"env": {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0), "gpu_before": gpu,
                       "pdf_dpi": PDF_DPI, "max_length": SINGLE_PAGE_MAX_LENGTH}, "pages": [], "multi": []}
    out_json = OUT / "results.json"

    def flush():
        out_json.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")

    tok, model, load_s = load_model("cuda")
    results["env"].update(load_seconds=round(load_s, 1), vram_after_load_mib=round(torch.cuda.memory_allocated() / 2**20))
    print(f"\nmodel loaded in {load_s:.1f} s, {results['env']['vram_after_load_mib']} MiB VRAM")
    probe = GenerateProbe(model)
    scratch = OUT / "model_scratch"  # infer() insists on a writable output folder

    def ocr_page(image, mode):
        return model.infer(tok, prompt="<image>document parsing.", image_file=str(image), output_path=str(scratch),
                           max_length=SINGLE_PAGE_MAX_LENGTH, no_repeat_ngram_size=35, ngram_window=128,
                           eval_mode=True, **MODES[mode])

    # First call pays for CUDA start-up; keep it out of the per-page numbers.
    warm = next((p for p in pages if "screenshot" in p["name"]), pages[0])
    _, err, m = measure(lambda: ocr_page(warm["image"], "base"))
    results["env"]["warmup"] = {**m, "error": err}
    print(f"warm-up: {m['seconds']} s")
    flush()

    for p in pages:
        for mode in modes:
            text, err, m = measure(lambda: ocr_page(p["image"], mode))
            row = {"name": p["name"], "kind": p["kind"], "mode": mode, "error": err, **m, **probe.stats,
                   "truth": str(p["truth"]) if p["truth"] else None, "chars": len(text or "")}
            if text is not None:
                (OUT / f"{p['name']}.{mode}.raw.txt").write_text(text, encoding="utf-8")
                gen = probe.stats.get("generate_s") or 0
                row["tokens_per_s"] = round(probe.stats["output_tokens"] / gen, 1) if gen else None
            results["pages"].append(row)
            flush()
            print(f"  {p['name']:30s} {mode:7s} {m['seconds']:7.1f} s  {row.get('output_tokens', 0):5d} tok  "
                  f"{m['peak_vram_allocated_mib']:6d} MiB  {'CAP ' if row.get('hit_token_cap') else ''}{err or ''}")

    # One-shot multi-page: how many pages fit into 16 GB? (computed prediction: ~20)
    source = [p["image"] for p in pages if p["kind"] != "synthetic" or "clean" in p["name"]] or [p["image"] for p in pages]
    for k in multi:
        chunk = [str(source[i % len(source)]) for i in range(k)]
        max_length = min(32768, 273 * k + 100 + 1500 * k)

        def run():
            with contextlib.redirect_stdout(io.StringIO()):  # infer_multi always streams to stdout
                return model.infer_multi(tok, prompt="<image>Multi page parsing.", image_files=chunk,
                                         output_path=str(scratch), image_size=1024, max_length=max_length,
                                         no_repeat_ngram_size=35, ngram_window=1024, save_results=False)

        res, err, m = measure(run)
        row = {"pages": k, "max_length": max_length, "error": err, **m, **probe.stats}
        if res is not None:
            text = res[0] if isinstance(res, tuple) else res
            row["page_separators"] = text.count("<PAGE>")
            (OUT / f"multi_{k:02d}.raw.txt").write_text(text, encoding="utf-8")
        results["multi"].append(row)
        flush()
        print(f"  multi {k:2d} pages  {m['seconds']:7.1f} s  {m['peak_vram_allocated_mib']:6d} MiB  {err or ''}")
        if err:
            break  # larger chunks would fail too

    results["env"]["gpu_after"] = gpu_memory()
    flush()
    print("\nresults ->", out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
