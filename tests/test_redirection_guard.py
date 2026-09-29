"""The installer under the RedirectionGuard that WebView2 turns on in OwlOCR.exe.

A child process switches on ProcessRedirectionTrustPolicy (EnforceRedirectionTrust) for itself,
proves that a user-created junction can no longer be traversed (os error 448), and then runs the
installer's link handling on an engine folder shaped like the one uv leaves behind.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(sys.platform != "win32", reason="Windows mitigation policy")]

REPO = Path(__file__).resolve().parent.parent

CHILD = textwrap.dedent(r"""
    import ctypes, json, os, subprocess, sys
    from ctypes import wintypes
    from pathlib import Path

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetProcessMitigationPolicy.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
    flags = wintypes.DWORD(1)                       # EnforceRedirectionTrust
    if not kernel32.SetProcessMitigationPolicy(16, ctypes.byref(flags), 4):
        print(json.dumps({"skip": f"policy not available ({ctypes.get_last_error()})"}))
        sys.exit(0)

    from owlocr.engine import install_kit as kit

    real = kit.python_dir() / "cpython-3.11.16-windows-x86_64-none"
    real.mkdir(parents=True)
    (real / "python.exe").write_bytes(b"")
    link = kit.python_dir() / "cpython-3.11-windows-x86_64-none"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], check=True, capture_output=True)
    try:
        os.listdir(link)
        blocked = None
    except OSError as exc:
        blocked = getattr(exc, "winerror", None)
    if blocked != 448:
        print(json.dumps({"skip": f"junction not blocked ({blocked})"}))
        sys.exit(0)
    found = kit.managed_python()
    removed = kit.remove_python_links()
    print(json.dumps({"managed": str(found), "removed": removed, "link_left": os.path.lexists(link),
                      "real_left": (real / "python.exe").is_file()}))
""")


def test_link_handling_works_under_the_redirection_guard(tmp_path):
    env = dict(os.environ)
    env.update(OWLOCR_HOME=str(tmp_path / "data"), OWLOCR_CONFIG=str(tmp_path / "config"),
               PYTHONPATH=str(REPO))
    proc = subprocess.run([sys.executable, "-c", CHILD], env=env, cwd=REPO, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    if "skip" in result:
        pytest.skip(result["skip"])
    python_dir = tmp_path / "data" / "engine" / "python"
    assert result == {"managed": str(python_dir / "cpython-3.11.16-windows-x86_64-none" / "python.exe"),
                      "removed": ["cpython-3.11-windows-x86_64-none"], "link_left": False, "real_left": True}
