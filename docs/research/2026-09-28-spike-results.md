# Spike results: Unlimited-OCR on Czech, measured locally

Date: 2026-09-28. Machine: RTX 4080 SUPER 16 GB, Core Ultra 7 265K, 64 GB RAM, Windows 11.
Stack: Python 3.11, torch 2.10.0+cu128, transformers 4.57.1, huggingface_hub 0.36.2.
Model: `baidu/Unlimited-OCR` at revision `07dea832e22aefee32ad281d4b80551282e1c168`, bf16, offline.
Scripts: `spike/`. Raw outputs: `spike/out/` (not in git).

## Verdict

Czech passes with a caveat. On real scans about 3 words in 100 are wrong, against about 10 in 100
for the OCR layer the test PDF already carried. Most errors are a single wrong or missing accent.
Good enough to build on; a correction step is needed for text that will be quoted.

## Setup facts

| Measure | Value |
|---|---|
| Model download (6.68 GB, plain HTTPS, Xet disabled) | 60 s, about 112 MB/s |
| Checksum verification of all 14 files | 5 s |
| Second run of the downloader | 0.13 s, no network |
| Model load, GPU | 5.1 s |
| Model load, CPU fp32 | 4.8 s |
| VRAM after load | 6,457 MiB |
| Warm-up (first inference) | 5.8 s |
| Offline load with `trust_remote_code` from a local folder whose path contains a space | works |

Loading prints a harmless warning that `model.vision_model.embeddings.position_ids` was newly
initialized. It is a fixed index buffer, not a learned weight.

## Accuracy, generated pages (exact ground truth)

CER = character error rate. "gundam" = high quality (1024 px overview + 640 px tiles), "base" = single 1024 px view.

| Page | CER gundam | CER base | Accents right, gundam |
|---|---|---|---|
| Clean letter, Times 300 dpi | 0.38% | 0.64% | 104/105 |
| Clean textbook page, Georgia | 0.60% | 2.21% | 133/136 |
| Small print, Calibri 30 px | 2.59% | 6.54% | 141/164 |
| Ruled table | 1.50% | 0.75% | 40/43 |
| Poor scan (150 dpi, skew 1.4°, speckle, blur, JPEG 45), letter | 0.26% | 0.64% | 105/105 |
| Poor scan, textbook | 1.30% | 1.91% | 134/136 |
| Phone photo (perspective, 3° rotation, uneven light) | 0.51% | 1.91% | 103/105 |
| Screenshot 1280x720 | 1.31% | 2.62% | 38/40 |
| Page rotated 90° | 25.51% | 97.83% | 37/105 |
| Blank page | outputs only `<|det|>image [0, 0, 999, 999]<|/det|>`, no invented text | same | |

## Accuracy, real scans (Czech botany textbook, 200 dpi greyscale)

No ground truth exists, so Unlimited-OCR (gundam) was compared word by word with the PDF's existing
text layer. Every disagreement was judged against the scan: page 52 by the main session, pages 26,
120 and 190 by one Opus 5.5 proofreader each.

| Page | Content | Words | Unlimited-OCR right / old layer right / both wrong | Unlimited-OCR word error | Old layer word error |
|---|---|---|---|---|---|
| 52 | text wrapped around figures | 350 | 13 / 6 / 0 | about 1.7% | about 4% |
| 120 | dense text | 565 | 69 / 7 / 6 | about 2.5% | much higher, whole phrases garbled |
| 190 | two-column glossary | 736 | 77 / 9 / 16 | about 3.7% | about 13% |
| 26 | dense text, many technical terms | 545 | 49 / 14 / 10 | about 4.5% | about 11% |

Nothing was missing on any page. One invented word was found (page 26).

### Error types

| Type | Examples | Handling |
|---|---|---|
| `ď` / `ť` as plain letter or letter + apostrophe | `bud`, `bud'`, `pojišt’ovnou`, `kaprad` | rule |
| Accent dropped, added or changed | `bylinny`, `dosáhlý`, `zárodečněho`, `vajičko` | dictionary check flags it |
| Letter confusion | `sporořyly` (f→ř), `differencovaným` | dictionary check flags it |
| Line-break hyphen left in | `kaktu-sovitých` | rule |
| Space lost | `křápíku` for "k řapíku" | dictionary check flags it |
| Letter from another language | `także` | rule: letter does not exist in Czech |
| Dash type | `–` written as `-` | cosmetic |
| Real word replaced by another real word | `významcové` for "výtrusnice", `půlová` for "pólová", `připomínající` for "připomínají" | **not detectable automatically** |
| Figure caption inserted mid-sentence | page 52 | layout post-processing using the box coordinates |
| Scrambled phrase | `pronikáníy plové l Decocky` | dictionary check flags it |

## Speed and memory

| Measure | Value |
|---|---|
| Generation speed | 36 to 42 tokens/s, same in both modes |
| GPU utilisation while generating | about 36 to 39%, about 65 W: the limit is the model's Python code |
| Generated page, 800 to 1,300 characters | 11 to 14 s |
| Typical book page, 2,700 to 4,400 characters | 25 to 42 s |
| Densest pages (index, bibliography, 7,000 to 10,500 characters) | 68 to 108 s |
| Peak VRAM gundam | 7,217 to 9,035 MiB depending on tile count |
| Peak VRAM base | 6,930 MiB |
| Prefix tokens | base 277; gundam 907 to 3,117 |
| Runaway loops, token cap hits | none in 40 runs |
| n-gram loop guard | called on every token, so it does work under transformers 4.57.1; it never had to ban anything |

## One-shot multi-page (`infer_multi`, base mode)

| Pages | Seconds | Peak VRAM | Prefix tokens | Output tokens | `<PAGE>` marks |
|---|---|---|---|---|---|
| 2 | 23 | 6,940 MiB | 551 | 932 | 2 |
| 5 | 78 | 7,607 MiB | 1,370 | 3,144 | 5 |
| 10 | 282 | 8,729 MiB | 2,735 | 11,379 | 11 |
| 20 | 635 | 10,975 MiB | 5,465 | 25,299 | 21 |

- 20 pages fit into 16 GB. The earlier estimate of 9 to 10 GB was close.
- No speed gain: about 32 s per page at 20 pages, the same as page by page.
- The 10- and 20-page runs returned one `<PAGE>` mark more than there were pages, so output cannot
  be mapped back to pages reliably.
- Multi-page forces base mode, which is the less accurate one.

Conclusion: process page by page in gundam mode.

## Answers to the open questions from the fact sheet

| # | Question | Answer |
|---|---|---|
| 1 | Czech accuracy | see above |
| 2 | Tokenizer round trip of the Czech pangram | exact |
| 5 | gundam or base as default | gundam |
| 7 | Seconds per page and VRAM on this card | see above |
| 8 | VRAM of multi-page chunks | see above |
| 11 | Does `eval_mode=True` output keep the tags | yes, as `<|det|>label [x1, y1, x2, y2]<|/det|>text`, coordinates 0 to 999, one box per block |
| 13 | Does the n-gram guard fire | yes |
| 17 | Whole-page rotation | fails; must be corrected before OCR |
| 19 | Native Windows + Python 3.11 + cu128 | works |
| 22 | Offline `trust_remote_code` from a local folder | works |
| 26 | Download without Xet | fast and reliable here |

Not tested: CPU inference speed, tables in real scans, formulas, handwriting, cu130, PyInstaller.

## Environment trap found

Tools started from the Claude desktop app get writes to `%LOCALAPPDATA%` redirected into
`AppData\Local\Packages\Claude_...\LocalCache\Local\`. A normally started program does not see
those files. The model therefore lives in `engine\` inside the project. Any test of "is the engine
already installed" run from a Claude session must use a real path.
