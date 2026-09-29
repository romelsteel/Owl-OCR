"""Command-line use without the window.

    python -m owlocr.cli <input> [<input> ...] [--mode quality|fast] [--formats md,txt,docx,pdf]
                         [--out DIR] [--pages 1-5,9] [--dpi 200]

Inputs may be files or folders (searched recursively). Results go next to each input, or into
--out. Every input also gets its sidecar <name>.owl.json. Defaults come from settings.json.
Exit code 0 on success, 1 when any input failed (or bad arguments), 2 when the engine is not
installed.
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
from owlocr.export import FORMATS, FORMATS_AVAILABLE, export_all
from owlocr.pipeline.document import Document, Page, save_sidecar
from owlocr.pipeline.pages import PageSource, find_inputs, list_pages
from owlocr.pipeline.process import ProcessOptions, process_page

_PAGES_SPEC = re.compile(r"^\s*\d+(\s*-\s*\d+)?(\s*,\s*\d+(\s*-\s*\d+)?)*\s*$")


class _BadArguments(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse exits with code 2 on bad arguments, but 2 means "engine not installed" here."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        raise _BadArguments(f"{self.prog}: error: {message}")


def _positive_int(text: str) -> int:
    value = int(text)                             # ValueError -> argparse reports "invalid value"
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive whole number, not {text!r}")
    return value


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
    if sources and not selected:                  # checked before anything is written
        raise ValueError(f"no pages in range {pages_spec} (the document has {len(sources)} pages)")
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
    parser = _Parser(prog="python -m owlocr.cli", description="Owl OCR without the window.")
    parser.add_argument("inputs", nargs="+", help="files or folders")
    parser.add_argument("--mode", choices=MODES, default=config["mode_default"])
    parser.add_argument("--formats", default=",".join(config["formats"]), help="comma-separated: md,txt,docx,pdf")
    parser.add_argument("--out", default=None, help="output folder (default: next to each input)")
    parser.add_argument("--pages", default=None, help="page numbers, e.g. 1-5,9")
    parser.add_argument("--dpi", type=_positive_int, default=config["pdf_dpi"],
                        help="PDF rendering resolution")
    try:
        args = parser.parse_args(argv)
    except _BadArguments as e:
        _say(str(e))
        return 1

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    available = [f for f in FORMATS if f in FORMATS_AVAILABLE]
    unknown = [f for f in formats if f not in FORMATS]
    if not formats or unknown:
        _say(f"unknown formats: {', '.join(unknown) or '(none given)'}; choose from {', '.join(available)}")
        return 1
    later = [f for f in formats if f not in FORMATS_AVAILABLE]
    if later:                                     # rejected before any OCR, not after it
        _say(f"{', '.join(later)} export is not available in this build; choose from {', '.join(available)}")
        return 1
    try:
        _parse_pages(args.pages, 1)
    except ValueError as e:
        _say(str(e))
        return 1
    missing = [p for p in args.inputs if not Path(p).exists()]
    for name in missing:
        _say(f"not found: {name}")
    inputs = find_inputs([Path(p) for p in args.inputs if p not in missing])
    if not inputs:
        if not missing:
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
    failed = len(missing)
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
            except Exception as e:                # a damaged file must not stop the other inputs
                failed += 1
                _say(f"{path.name}: FAILED: {e or type(e).__name__}")
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
    finally:
        lazy.stop()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
