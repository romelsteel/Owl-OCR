# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec of Owl OCR. Build with:  py packaging\build.py   (never with a .bat file)
#
# ONEDIR and windowed. torch, transformers and the other engine libraries are EXCLUDED on
# purpose: the engine lives in its own venv that the setup wizard creates. build.py fails the
# build if any of them ends up in the output anyway.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_delvewheel_libs_directory, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "build" / "owl.ico"

EXCLUDES = [
    "torch", "torchvision", "torchaudio", "transformers", "tokenizers", "safetensors",
    "accelerate", "triton", "einops", "easydict", "addict", "matplotlib",
    "tensorflow", "jax", "IPython", "pytest",
    # build tools, not runtime code: cffi's compile helper (cffi._shimmed_dist_utils) would pull in
    # all of setuptools; the app only uses cffi's ABI mode through pythonnet/clr_loader
    "setuptools", "pkg_resources", "distutils", "_distutils_hack",
    # PyInstaller itself (GPL) and its helpers must never ship; they were pulled in by the packages'
    # own build-time hook modules (webview.__pyinstaller, pythonnet._pyinstaller), filtered below too
    "PyInstaller", "altgraph", "pefile", "ordlookup", "win32ctypes",
]


def not_a_pyinstaller_hook(name: str) -> bool:
    """True unless the module name or data path belongs to a package's own PyInstaller hooks."""
    return "_pyinstaller" not in name.replace("\\", "/").lower()

datas = [
    (str(ROOT / "owlocr" / "web" / "static"), "owlocr/web/static"),
    (str(ROOT / "owlocr" / "engine" / "pins.json"), "owlocr/engine"),
    (str(ROOT / "owlocr" / "pipeline" / "dictionaries.json"), "owlocr/pipeline"),
    (str(ROOT / "owlocr" / "export" / "fonts"), "owlocr/export/fonts"),
    (str(ROOT / "worker" / "owl_worker.py"), "worker"),
    (str(ROOT / "worker" / "device_patch.py"), "worker"),
    (str(ROOT / "worker" / "requirements-engine.txt"), "worker"),
    (str(ROOT / "licenses"), "licenses"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "packaging" / "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = collect_submodules("owlocr") + ["clr"]

for package in ("webview", "clr_loader", "pythonnet", "pypdfium2", "pypdfium2_raw", "docx", "pikepdf"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += [entry for entry in package_datas if not_a_pyinstaller_hook(entry[0])]
    binaries += package_binaries
    hiddenimports += [name for name in package_hidden if not_a_pyinstaller_hook(name)]

# code only: no spylls ru/sv/en dictionaries, no reportlab GPL fonts (collect_all would add them)
hiddenimports += collect_submodules("reportlab") + collect_submodules("spylls")
# pikepdf's qpdf and msvcp140 DLLs live in the delvewheel folder pikepdf.libs
datas, binaries = collect_delvewheel_libs_directory("pikepdf", datas=datas, binaries=binaries)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OwlOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="OwlOCR",
)
