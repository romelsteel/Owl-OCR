# Owl OCR — build plans

Four plans, built in this order. Each ends with software that works and is tested.

| Order | Plan | Tasks | Delivers |
|---|---|---|---|
| 1 | [A Foundation](2026-09-28-plan-a-foundation.md) | 29 | engine worker, protocol, lifetime protection, engine client, model store (download once), pipeline core, Markdown and text export, command-line tool |
| 2 | [B App](2026-09-28-plan-b-app.md) | 14 | window, queue with pause/resume/cancel, Stop engine button, Quality/Fast switch, settings, review screen, Czech/English, owl mascot |
| 3 | [C Correction and exports](2026-09-28-plan-c-correction-exports.md) | 19 | repair rules, dictionary check, orientation fix, tall-image strips, Word, searchable PDF |
| 4 | [D Installation and release](2026-09-28-plan-d-install-release.md) | 31 | hardware detection, setup wizard, engine bootstrap, processor-only tier, dictionaries download, installer, portable zip, README, release |

B and C both depend only on A and may be built in either order. D depends on all three.

## Read before building

1. [Design](../specs/2026-09-28-owl-ocr-design.md) — what and why
2. [Interface contract](../specs/2026-09-28-owl-ocr-interfaces.md) — names and signatures shared by the plans
3. [Spike results](../../research/2026-09-28-spike-results.md) — what was measured
4. The plan being built, including its **Contract notes** section at the end. Contract notes of an
   earlier plan are binding for the later ones.

Where a plan's Contract notes differ from the interface contract, the Contract notes win: they were
written after the code was run.

## How the plans were verified

Every plan's code was built and run in a scratch copy by its author before the plan was written.

| Plan | Tests passing in the scratch build | Not verified |
|---|---|---|
| A | 216 | real GPU inference through the new worker (the GPU accuracy test is run during the build) |
| B | 86, plus the UI clicked through in a browser | the real WebView2 window |
| C | 338 (335 without network) | |
| D | 212, plus the wizard and dictionary screens clicked through in a browser | downloading uv and torch, PyInstaller, Inno Setup, the processor-only acceptance test |

Packaging (plan D) is the least proven part and the most likely to need fixes during the build.

## Rules for whoever builds

| Rule | Reason |
|---|---|
| Set `OWLOCR_HOME` and `OWLOCR_CONFIG` to folders inside the repository for every run and test | tools started from the Claude desktop app get AppData writes redirected into a private folder |
| Never run a GPU test with less than 9,500 MiB of VRAM free, and never while the owner is using the graphics card | results are meaningless and the owner's game stutters |
| Never commit anything from `samples/` or text copied from it | copyrighted textbook |
| The clipboard test is opt-in (`OWLOCR_TEST_CLIPBOARD=1`) and needs the owner's agreement | it overwrites the real clipboard |
| Subagents run on Opus 5.5 or Sonnet; ask the owner before using a larger model | owner's rule |
| Push, publish, make public, release: only on the owner's explicit instruction at that moment | outward-facing |
| Never run `.bat` files on the owner's PC; build with `py packaging\build.py` | owner's rule |
| The model already in `engine\models\unlimited_ocr` is verified and counts as installed | never download it again |
| Explain to the owner in plain language; report progress as a short table | the owner is a student, near-beginner coder |
| After each batch of subagents, report them in a table: agent, model, tokens, time, result | owner's rule |

## Later

Local AI cleanup (design section 14) has no plan yet. It starts with a test, not a plan, once the
core app works.

The backlog for the next version (math and tables first) is in [next-version-0.2.md](next-version-0.2.md).
