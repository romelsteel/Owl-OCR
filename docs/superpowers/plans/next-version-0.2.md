# Owl OCR 0.2 — what comes next

Backlog agreed with the owner on 2026-09-29, after his first real install of 0.1.0. Not a build plan
yet: each item starts with a measurement on real documents, then gets a plan like A–D.

## 1. Math and tables in PDFs that already have a text layer (owner's request, top priority)

**Problem.** A born-digital PDF (example: the owner's "Rovnice a nerovnice", lecture notes full of
equations and small tables) goes through the PDF text layer by default
(`use_text_layer = "born_digital"`). The text layer has no structure for math or tables: fractions fall
apart into numerator and denominator on separate lines, exponents drop to the next line (`x` / `2`),
alignment bars and multi-line derivations turn into scattered single characters, table cells run
together, and headings and pictures are lost.

**What already exists.** When the engine reads a page, plan A/C export already writes formula blocks as
`$$ … $$` (LaTeX from the model), tables as Markdown pipe tables (HTML when cells are merged), headings
as `#`/`##`, and pictures cut out and linked in place (Markdown or Obsidian links). None of this reaches
the user when the text layer is taken instead.

**Plan.**
1. Measure first: run the owner's math notes and one textbook page with tables through the engine
   (`use_text_layer = never`) and score formulas (display and inline), tables and headings.
2. Smarter text-layer decision per page: detect pages where the text layer destroys structure (share of
   one- or two-character lines, math symbols such as `= ± √ ≤ ≥ ∈ ⇒`, broken superscripts, ruled table
   areas from the PDF drawing commands) and send those pages to the engine; plain-text pages keep the
   fast text layer. Setting stays available (`born_digital` / `never` / `always`).
3. Inline math: formulas inside sentences come back as ordinary text today. Depending on step 1, either
   post-process the model's inline LaTeX into `$…$`, or ask the model for inline formula marks, or leave
   it and document the limit.
4. Tables: verify the HTML → pipe-table conversion on real Czech tables (merged cells, header rows,
   tables continuing over a page break); Obsidian renders both pipe tables and HTML.
5. Check that the searchable PDF and Word exports keep formulas readable (at least as the LaTeX text).

## 2. Items deferred from the plan D final review (fix when touching the area)

- Adopt ("I already have the engine") has no free-space check before copying 6.7 GB.
- A dictionary download can run while the data folder is being moved.
- Upgrades: remove stale files of an older version from `{app}\_internal` (`[InstallDelete]`).
- Recovery after an interrupted torch install (half-written venv).
- Uninstaller: an exit code of 1 caused only by the stale-worker sweep shows a data warning although
  the data was deleted.
- A data folder chosen through a junction would fail under WebView2's RedirectionGuard (see contract
  note 33): reject such a folder with a clear message.
- Several UI tests only check that strings exist in the source; replace the important ones with
  behaviour tests.

## 3. Still open from before

- Local AI cleanup (design section 14): starts with a test, not a plan.
