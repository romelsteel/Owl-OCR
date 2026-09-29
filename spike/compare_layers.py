"""THROWAWAY spike: real scans have no guaranteed-correct text, so compare two OCRs.

  A = the text layer the PDF already carries (some earlier OCR program)
  B = Unlimited-OCR output

Where A and B agree, the text is almost certainly right (two independent programs).
Where they disagree, somebody has to look at the scan. This script lists the
disagreements and cuts the page into legible strips for that proofreader.

Usage:  spike\\.venv\\Scripts\\python.exe spike\\compare_layers.py [--mode gundam]

Writes spike/out/compare/<page>.json and <page>_strip<N>.png. CPU only.
"""
import re
import sys
import json
import pathlib
import difflib
import unicodedata

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from score import clean_ocr  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

OUT = pathlib.Path(__file__).parent / "out"
CMP = OUT / "compare"
STRIPS, OVERLAP = 4, 80
PUNCT = str.maketrans({"’": "'", "‘": "'", "‚": ",", "„": '"', "“": '"', "”": '"', "–": "-", "—": "-", "…": "..."})


def words(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text).translate(PUNCT)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # word split across two lines
    return t.split()


def disagreements(a: list[str], b: list[str]) -> tuple[list[dict], int]:
    """Short local differences are word-level disagreements; long one-sided blocks are
    reported separately, since they are usually reading order or a skipped block."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out, agreed = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            agreed += i2 - i1
            continue
        kind = "word" if max(i2 - i1, j2 - j1) <= 6 else "block"
        out.append({
            "id": len(out) + 1, "kind": kind,
            "before": " ".join(a[max(0, i1 - 6):i1]),
            "A": " ".join(a[i1:i2]), "B": " ".join(b[j1:j2]),
            "after": " ".join(a[i2:i2 + 6]),
        })
    return out, agreed


def cut_strips(image: pathlib.Path, stem: str) -> list[str]:
    img = Image.open(image)
    h = img.height // STRIPS
    files = []
    for n in range(STRIPS):
        top, bottom = max(0, n * h - OVERLAP), min(img.height, (n + 1) * h + OVERLAP)
        f = CMP / f"{stem}_strip{n + 1}.png"
        img.crop((0, top, img.width, bottom)).save(f)
        files.append(str(f))
    return files


def main() -> int:
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "gundam"
    CMP.mkdir(parents=True, exist_ok=True)
    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    print(f"{'page':14s} {'words A':>8s} {'words B':>8s} {'agree':>7s} {'word diffs':>11s} {'block diffs':>12s}")
    for r in results["pages"]:
        if r["kind"] != "sample_pdf" or r["mode"] != mode or not r["truth"]:
            continue
        raw = OUT / f"{r['name']}.{mode}.raw.txt"
        if not raw.exists():
            continue
        a = words(pathlib.Path(r["truth"]).read_text(encoding="utf-8"))
        b = words(clean_ocr(raw.read_text(encoding="utf-8")))
        diffs, agreed = disagreements(a, b)
        image = OUT / "pages" / f"{r['name']}.png"
        page = {
            "page": r["name"], "mode": mode, "image": str(image), "strips": cut_strips(image, r["name"]),
            "words_A": len(a), "words_B": len(b), "words_agreed": agreed, "disagreements": diffs,
            "text_B": " ".join(b),
        }
        (CMP / f"{r['name']}.json").write_text(json.dumps(page, indent=1, ensure_ascii=False), encoding="utf-8")
        nw, nb = sum(d["kind"] == "word" for d in diffs), sum(d["kind"] == "block" for d in diffs)
        print(f"{r['name'][-14:]:14s} {len(a):8d} {len(b):8d} {agreed / max(len(a), 1):7.1%} {nw:11d} {nb:12d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
