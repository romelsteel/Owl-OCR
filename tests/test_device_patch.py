import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "worker"))
import device_patch  # noqa: E402

REAL_MODEL = Path(os.environ.get("OWLOCR_TEST_MODEL_DIR", REPO / "engine" / "models" / "unlimited_ocr"))
FILES = ("modeling_unlimitedocr.py", "modeling_deepseekv2.py", "deepencoder.py", "manifest.json")

pytestmark = pytest.mark.skipif(not (REAL_MODEL / "modeling_unlimitedocr.py").is_file(),
                                reason=f"real model code not found in {REAL_MODEL}")


@pytest.fixture
def model_copy(tmp_path):
    d = tmp_path / "unlimited_ocr"
    d.mkdir()
    for name in FILES:
        shutil.copy2(REAL_MODEL / name, d / name)
    return d


def git_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_copies_are_pristine(model_copy):
    manifest = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))
    for name in FILES[:3]:
        assert git_sha1(model_copy / name) == manifest["files"][name]["git_sha1"]


def test_patch_removes_every_cuda_call_and_compiles(model_copy):
    assert device_patch.apply(model_copy, "cpu", "float32") == "patched"
    for name in FILES[:3]:
        text = (model_copy / name).read_text(encoding="utf-8")
        assert text.count(".cuda()") == 0, name
        assert 'autocast("cuda"' not in text, name
        assert ".to(torch.bfloat16)" not in text, name
        py_compile.compile(str(model_copy / name), cfile=str(model_copy / (name + "c")), doraise=True)
    target = (model_copy / "modeling_unlimitedocr.py").read_text(encoding="utf-8")
    assert device_patch.SENTINEL in target
    assert target.startswith("# NOTICE: this file was modified by Owl OCR")
    assert "images_seq_mask[idx].unsqueeze(-1).to(inputs_embeds.device)" in target   # forward()
    assert target.count("torch.autocast(_OWL_DEVICE_TYPE, dtype=_OWL_DTYPE, enabled=_OWL_AUTOCAST)") == 3
    assert '_OWL_DEVICE = _owl_os.environ.get("OWLOCR_DEVICE", "cpu")' in target
    assert '_OWL_DTYPE = getattr(_owl_torch, _owl_os.environ.get("OWLOCR_DTYPE", "float32"))' in target


def test_patch_keeps_backup_and_updates_manifest(model_copy):
    before = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))["files"]["modeling_unlimitedocr.py"]
    device_patch.apply(model_copy, "cpu", "float32")
    backup = model_copy / "modeling_unlimitedocr.py.orig"
    assert git_sha1(backup) == before["git_sha1"]
    files = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert files["modeling_unlimitedocr.py.orig"] == before
    patched = (model_copy / "modeling_unlimitedocr.py").read_bytes()
    assert files["modeling_unlimitedocr.py"]["size"] == len(patched)
    assert files["modeling_unlimitedocr.py"]["sha256"] == hashlib.sha256(patched).hexdigest()
    assert files["modeling_unlimitedocr.py"]["git_sha1"] is None


def test_other_two_files_are_not_modified(model_copy):
    before = {n: (model_copy / n).read_bytes() for n in FILES[1:3]}
    device_patch.apply(model_copy, "cpu", "float32")
    assert {n: (model_copy / n).read_bytes() for n in FILES[1:3]} == before
    assert not (model_copy / "modeling_deepseekv2.py.orig").exists()


def test_second_run_is_a_no_op(model_copy):
    device_patch.apply(model_copy, "cpu", "float32")
    snapshot = {p.name: p.read_bytes() for p in model_copy.iterdir() if p.is_file()}
    assert device_patch.apply(model_copy, "cpu", "float32") == "already patched"
    assert {p.name: p.read_bytes() for p in model_copy.iterdir() if p.is_file()} == snapshot


def test_tampered_input_is_refused_and_left_alone(model_copy):
    target = model_copy / "modeling_unlimitedocr.py"
    text = target.read_text(encoding="utf-8")
    tampered = text.replace("input_ids.unsqueeze(0).cuda().shape[1]", "input_ids.unsqueeze(0).shape[1]", 1)
    assert tampered != text
    target.write_text(tampered, encoding="utf-8", newline="")
    with pytest.raises(device_patch.PatchRefused, match="expected upstream code"):
        device_patch.apply(model_copy, "cpu", "float32")
    assert target.read_text(encoding="utf-8") == tampered
    assert not (model_copy / "modeling_unlimitedocr.py.orig").exists()


def test_cuda_code_appearing_in_a_checked_file_is_refused(model_copy):
    other = model_copy / "deepencoder.py"
    other.write_text(other.read_text(encoding="utf-8") + "\nx = y.cuda()\n", encoding="utf-8", newline="")
    with pytest.raises(device_patch.PatchRefused, match="deepencoder.py"):
        device_patch.apply(model_copy, "cpu", "float32")


def test_restore_puts_the_original_back(model_copy):
    original = (model_copy / "modeling_unlimitedocr.py").read_bytes()
    manifest_before = json.loads((model_copy / "manifest.json").read_text(encoding="utf-8"))
    device_patch.apply(model_copy, "cpu", "float32")
    assert device_patch.restore(model_copy) == "restored"
    assert (model_copy / "modeling_unlimitedocr.py").read_bytes() == original
    assert not (model_copy / "modeling_unlimitedocr.py.orig").exists()
    assert json.loads((model_copy / "manifest.json").read_text(encoding="utf-8")) == manifest_before
    assert device_patch.restore(model_copy) == "not patched"


def test_patch_does_not_write_through_a_hard_link(model_copy, tmp_path):
    shared = tmp_path / "shared.py"
    shutil.copy2(model_copy / "modeling_unlimitedocr.py", shared)
    (model_copy / "modeling_unlimitedocr.py").unlink()
    os.link(shared, model_copy / "modeling_unlimitedocr.py")
    before = shared.read_bytes()
    device_patch.apply(model_copy, "cpu", "float32")
    assert shared.read_bytes() == before


def test_command_line_exit_codes(model_copy):
    script = str(REPO / "worker" / "device_patch.py")
    run = lambda *a: subprocess.run([sys.executable, script, "--model-dir", str(model_copy), *a],
                                    capture_output=True, text=True)
    assert run("--check").returncode == 3
    done = run("--device", "cpu", "--dtype", "float32")
    assert done.returncode == 0 and "patched" in done.stdout
    assert run("--check").returncode == 0
    assert run("--restore").returncode == 0
    target = model_copy / "modeling_unlimitedocr.py"
    target.write_text(target.read_text(encoding="utf-8").replace(".cuda()", "", 1), encoding="utf-8", newline="")
    refused = run()
    assert refused.returncode == 2 and "REFUSED" in refused.stdout
