"""THROWAWAY spike: compare OCR output with the known text.

Usage:  spike\\.venv\\Scripts\\python.exe spike\\score.py [--selftest]

Reads spike/out/results.json + the *.raw.txt files, writes spike/out/report.md.
CPU only.

Numbers reported per page and mode:
  CER            character error rate = edit distance / length of the correct text
  CER no-diacr.  the same after removing diacritics from both texts; if this is much
                 lower than CER, the errors are mostly diacritics
  diacritics     share of Czech accented letters that came out right
"""
import re
import sys
import json
import pathlib
import unicodedata
from collections import Counter

from rapidfuzz.distance import Levenshtein

sys.stdout.reconfigure(encoding="utf-8")

OUT = pathlib.Path(__file__).parent / "out"
CZECH = set("ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ")

TAG_PAIR = re.compile(r"<\|ref\|>.*?<\|/ref\|>|<\|det\|>.*?<\|/det\|>", re.S)
ANY_SPECIAL = re.compile(r"<\|[^|>]*\|>|<PAGE>")
ROW_END = re.compile(r"</tr>|<br\s*/?>", re.I)
HTML = re.compile(r"</?(table|thead|tbody|tr|td|th)[^>]*>", re.I)
MARKDOWN = re.compile(r"^\s{0,3}#{1,6}\s+|\*\*|__|^\s*[-*]\s+|^\s*\|?[-:| ]{3,}\|?\s*$", re.M)


def clean_ocr(raw: str) -> str:
    """Model output -> the plain words a reader would see."""
    t = TAG_PAIR.sub(" ", raw)
    t = ANY_SPECIAL.sub(" ", t)
    t = ROW_END.sub("\n", t)
    t = HTML.sub(" ", t)
    t = MARKDOWN.sub("", t)
    return t.replace("|", " ")


def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t)).strip()


def strip_diacritics(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def cer(truth: str, hyp: str) -> float:
    return Levenshtein.distance(truth, hyp) / max(len(truth), 1)


def diacritics(truth: str, hyp: str) -> tuple[int, int, Counter]:
    """(correct, total, confusions) over the accented letters of the correct text."""
    wrong = {}
    for op, i, j in Levenshtein.editops(truth, hyp):
        if op == "replace":
            wrong[i] = hyp[j]
        elif op == "delete":
            wrong[i] = "∅"
    total = [i for i, c in enumerate(truth) if c in CZECH]
    confusions = Counter(f"{truth[i]}→{wrong[i]}" for i in total if i in wrong)
    return len(total) - sum(confusions.values()), len(total), confusions


def score(truth_raw: str, ocr_raw: str) -> dict:
    truth, hyp = normalize(truth_raw), normalize(clean_ocr(ocr_raw))
    ok, total, conf = diacritics(truth, hyp)
    return {
        "cer": cer(truth, hyp),
        "cer_no_diacritics": cer(strip_diacritics(truth), strip_diacritics(hyp)),
        "diacritics_ok": ok, "diacritics_total": total, "confusions": conf,
        "truth_chars": len(truth), "ocr_chars": len(hyp),
    }


def selftest():
    truth = "Příliš žluťoučký kůň úpěl ďábelské ódy."
    assert score(truth, truth)["cer"] == 0
    s = score(truth, "<|ref|>text<|/ref|><|det|>[[1,2,3,4]]<|/det|>\n## Prilis žluťoučký kůň úpěl ďábelské ódy.")
    assert s["diacritics_total"] == 15 and s["diacritics_ok"] == 12, s
    assert s["confusions"] == Counter({"ř→r": 1, "í→i": 1, "š→s": 1}), s["confusions"]
    assert abs(s["cer"] - 3 / len(truth)) < 1e-9 and s["cer_no_diacritics"] == 0, s
    t = score("Jméno Obec\nŽaneta Třebíč", "<table><tr><td>Jméno</td><td>Obec</td></tr><tr><td>Žaneta</td><td>Třebíč</td></tr></table>")
    assert t["cer"] == 0, t
    print("selftest OK")


def main() -> int:
    if "--selftest" in sys.argv:
        selftest()
        return 0

    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    env, rows, all_conf = results["env"], [], Counter()
    for r in results["pages"]:
        raw_file = OUT / f"{r['name']}.{r['mode']}.raw.txt"
        raw = raw_file.read_text(encoding="utf-8") if raw_file.exists() else ""
        s = None
        if r["truth"] and pathlib.Path(r["truth"]).exists():
            truth = pathlib.Path(r["truth"]).read_text(encoding="utf-8")
            if truth.strip():
                s = score(truth, raw)
                all_conf += s["confusions"]
        rows.append((r, s, len(normalize(clean_ocr(raw)))))

    md = ["# Owl OCR spike — results", "",
          f"GPU: {env['gpu']} · torch {env['torch']} · model load {env.get('load_seconds')} s · "
          f"VRAM after load {env.get('vram_after_load_mib')} MiB · warm-up {env.get('warmup', {}).get('seconds')} s", "",
          "| Page | Mode | CER | CER no-diacr. | Diacritics | s/page | tok/s | Out tok | Peak VRAM | Notes |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r, s, visible in rows:
        notes = []
        if r.get("error"):
            notes.append(r["error"][:40])
        if r.get("hit_token_cap"):
            notes.append("hit token cap (loop?)")
        if s is None and visible and "blank" in r["name"]:
            notes.append(f"INVENTED {visible} chars")
        if not visible and "blank" not in r["name"]:
            notes.append("EMPTY OUTPUT")
        if r.get("ngram_guard_calls") == 0:
            notes.append("n-gram guard never called")
        md.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} MiB | {} |".format(
            r["name"], r["mode"],
            f"{s['cer']:.2%}" if s else "–",
            f"{s['cer_no_diacritics']:.2%}" if s else "–",
            f"{s['diacritics_ok']}/{s['diacritics_total']}" if s else "–",
            r["seconds"], r.get("tokens_per_s", "–"), r.get("output_tokens", "–"),
            r["peak_vram_allocated_mib"], "; ".join(notes)))

    scored = [(r, s) for r, s, _ in rows if s]
    for mode in sorted({r["mode"] for r, _ in scored}):
        sub = [s for r, s in scored if r["mode"] == mode]
        chars = sum(s["truth_chars"] for s in sub)
        md += ["", f"**{mode}** over {len(sub)} pages with known text: "
               f"CER {sum(s['cer'] * s['truth_chars'] for s in sub) / chars:.2%}, "
               f"diacritics {sum(s['diacritics_ok'] for s in sub)}/{sum(s['diacritics_total'] for s in sub)} "
               f"({sum(s['diacritics_ok'] for s in sub) / max(sum(s['diacritics_total'] for s in sub), 1):.1%})"]
    if all_conf:
        md += ["", "Most common mistakes on accented letters: " + ", ".join(f"{k} ({v}×)" for k, v in all_conf.most_common(12))]
    if results.get("multi"):
        md += ["", "## One-shot multi-page", "", "| Pages | s | Peak VRAM | Prefix tok | Out tok | `<PAGE>` marks | Error |", "|---|---|---|---|---|---|---|"]
        for m in results["multi"]:
            md.append(f"| {m['pages']} | {m['seconds']} | {m['peak_vram_allocated_mib']} MiB | {m.get('prefix_tokens', '–')} | "
                      f"{m.get('output_tokens', '–')} | {m.get('page_separators', '–')} | {m.get('error') or ''} |")

    (OUT / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
