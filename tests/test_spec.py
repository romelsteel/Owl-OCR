import re

from tests.conftest import REPO

SPEC = (REPO / "packaging" / "owlocr.spec").read_text(encoding="utf-8")
ENGINE_LIBRARIES = ("torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors",
                    "accelerate")


def test_spec_compiles_and_is_onedir_windowed():
    compile(SPEC, "owlocr.spec", "exec")
    assert "exclude_binaries=True" in SPEC and "COLLECT(" in SPEC      # onedir, never onefile
    assert "console=False" in SPEC and "upx=False" in SPEC


def test_spec_excludes_engine_libraries():
    excludes = re.search(r"EXCLUDES = \[(.*?)\]", SPEC, re.S).group(1)
    for name in ENGINE_LIBRARIES:
        assert f'"{name}"' in excludes, name


def test_spec_collects_what_the_app_needs():
    for package in ("webview", "clr_loader", "pythonnet", "pypdfium2", "pypdfium2_raw", "reportlab", "docx", "spylls"):
        assert f'"{package}"' in SPEC, package
    for data in ('"owlocr" / "web" / "static"', '"pins.json"', '"owl_worker.py"', '"device_patch.py"',
                 '"requirements-engine.txt"', '"licenses"', '"LICENSE"', '"THIRD_PARTY_NOTICES.md"'):
        assert data in SPEC, data
    assert 'packaging" / "launcher.py"' in SPEC


# ---- every data file the code reads is bundled at the path the code expects ------------------
DATA_ENTRY = re.compile(r'\(str\(ROOT((?:\s*/\s*"[^"]+")+)\),\s*"([^"]+)"\)')
READS = (
    re.compile(r'resource(?:_path)?\(\s*(f?)"([^"]*)"'),                    # paths.resource_path, Deps.resource
    re.compile(r'_REL\s*=\s*()"([^"]+)"'),                                   # *_REL constants
)
BESIDE_MODULE = (
    re.compile(r'Path\(__file__\)(?:\.resolve\(\))?\.with_name\(\s*"([^"]+)"\)'),
    re.compile(r'Path\(__file__\)(?:\.resolve\(\))?\.parent\s*/\s*"([^"]+)"'),
)


def bundled_entries() -> list[tuple[str, str]]:
    entries = []
    for parts, dest in DATA_ENTRY.findall(SPEC):
        src = "/".join(re.findall(r'"([^"]+)"', parts))
        entries.append((src, dest))
    return entries


def files_the_code_reads() -> set[str]:
    wanted: set[str] = set()
    for source in sorted((REPO / "owlocr").rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for pattern in READS:
            for is_f, value in pattern.findall(text):
                if is_f:                                     # f"worker/{name}": every file of that folder
                    folder = value.split("{", 1)[0].rstrip("/")
                    wanted |= {p.relative_to(REPO).as_posix() for p in (REPO / folder).iterdir()
                               if p.is_file() and p.suffix != ".pyc"}
                elif value:
                    wanted.add(value)
        module_dir = source.parent.relative_to(REPO).as_posix()
        for pattern in BESIDE_MODULE:
            wanted |= {f"{module_dir}/{name}" for name in pattern.findall(text)}
    return wanted


def bundle_path(rel: str, entries) -> str | None:
    for src, dest in entries:
        if rel == src:                      # a folder's contents go into dest, a file into dest/<name>
            path = dest if (REPO / src).is_dir() else f"{dest}/{src.rsplit('/', 1)[-1]}"
        elif rel.startswith(src + "/"):
            path = f"{dest}{rel[len(src):]}"
        else:
            continue
        return path[2:] if path.startswith("./") else path
    return None


def test_the_code_reads_the_expected_data_files():
    wanted = files_the_code_reads()
    for rel in ("owlocr/web/static", "owlocr/engine/pins.json", "owlocr/pipeline/dictionaries.json",
                "owlocr/export/fonts", "worker/owl_worker.py", "worker/requirements-engine.txt",
                "licenses/Apache-2.0.txt", "owlocr/web/static/selftest.png"):
        assert rel in wanted, rel


def test_every_data_file_the_code_reads_is_bundled_where_the_code_looks():
    entries = bundled_entries()
    problems = []
    for rel in sorted(files_the_code_reads()):
        if not (REPO / rel).exists():
            problems.append(f"{rel}: read by the code but missing in the repository")
        elif bundle_path(rel, entries) != rel:
            problems.append(f"{rel}: bundled as {bundle_path(rel, entries)}")
    assert problems == []


def test_spec_keeps_unwanted_data_out():
    loop = re.search(r"for package in \((.*?)\):", SPEC, re.S).group(1)
    assert '"reportlab"' not in loop and '"spylls"' not in loop
    assert 'collect_delvewheel_libs_directory("pikepdf"' in SPEC
