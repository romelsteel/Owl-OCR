"""Development only: make default_engine() work from the repository.

    py -3.11 scripts\\dev_engine.py

Writes <data root>\\engine\\install.json for a development engine:
  data root      <repo>\\engine            (git-ignored; holds the verified model in models\\unlimited_ocr)
  engine Python  <repo>\\spike\\.venv\\Scripts\\python.exe   (torch 2.10.0+cu128, transformers 4.57.1)
  worker         <repo>\\worker\\owl_worker.py (run straight from the repository)

Every shell that then runs the app or the CLI must point Owl OCR at that data root, because tools
started from the Claude desktop app get %APPDATA% and %LOCALAPPDATA% silently redirected:
  PowerShell:  $env:OWLOCR_HOME = "<repo>\\engine"; $env:OWLOCR_CONFIG = "<repo>\\engine\\config"
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", default=str(REPO / "spike" / ".venv" / "Scripts" / "python.exe"),
                        help="Python of the development engine")
    parser.add_argument("--data-root", default=str(REPO / "engine"), help="development data root")
    args = parser.parse_args(argv)

    data_root = Path(args.data_root).resolve()
    os.environ["OWLOCR_HOME"] = str(data_root)           # before anything asks owlocr.paths
    from owlocr import paths
    from owlocr.engine import registry, store

    spec = registry.UNLIMITED_OCR
    python = Path(args.python)
    worker = REPO / "worker" / "owl_worker.py"
    if not python.is_file():
        print(f"no engine Python at {python}", file=sys.stderr)
        return 1
    if not store.is_ready(spec.engine_id):
        print(f"the model in {paths.model_dir(spec.engine_id)} is missing or incomplete "
              "(spike\\download_model.py downloads it)", file=sys.stderr)
        return 1
    install = {
        "engine_id": spec.engine_id,
        "revision": spec.revision,
        "torch": spec.torch,
        "torchvision": spec.torchvision,
        "transformers": spec.transformers,
        "tier": "development",
        "device": "cuda",
        "dtype": "bfloat16",
        "torch_index": "https://download.pytorch.org/whl/cu128",
        "python": str(python),
        "worker_script": str(worker),
    }
    target = paths.engine_dir() / "install.json"
    paths.atomic_write_text(target, json.dumps(install, indent=1) + "\n")
    print(f"wrote {target}")
    print(f'now set:  $env:OWLOCR_HOME = "{data_root}"; $env:OWLOCR_CONFIG = "{data_root / "config"}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
