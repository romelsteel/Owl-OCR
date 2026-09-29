"""worker/owl_worker.py logic that needs neither torch nor the model."""
import importlib.util
import io
import os
import re
import sys

import pytest
from PIL import Image

from tests.conftest import REPO


def _load_worker():
    spec = importlib.util.spec_from_file_location("owl_worker_under_test", REPO / "worker" / "owl_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def saved_env():
    saved = dict(os.environ)                  # the worker module sets HF_* defaults on import
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def worker(monkeypatch, saved_env):
    module = _load_worker()
    sent = []
    monkeypatch.setattr(module, "send", sent.append)
    module.sent = sent
    yield module
    module._remove_scratch()                  # Engine() makes a temp folder; never leave it behind


def test_import_does_not_redirect_stdout(saved_env):
    before = sys.stdout
    module = _load_worker()
    assert module._proto is None
    assert sys.stdout is before


def test_library_prints_do_not_reach_the_protocol_stream(saved_env, monkeypatch):
    """What main() does with stdout: prints of the model code land on stderr, send() on the
    real stdout (as UTF-8 with bare \\n), and the protocol stream carries nothing but JSON lines."""
    worker = _load_worker()
    proto_bytes, err = io.BytesIO(), io.StringIO()
    proto = io.TextIOWrapper(proto_bytes, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", proto)
    monkeypatch.setattr(sys, "stderr", err)
    worker._claim_stdout()
    print("directly resize")                  # what the model code prints
    worker.send({"event": "pong", "id": "č"})
    proto.flush()
    assert sys.stdout is err
    assert proto_bytes.getvalue().decode("utf-8") == '{"event": "pong", "id": "č"}\n'
    assert "directly resize" in err.getvalue()


def test_modes_and_guard_values(worker):
    assert worker.PROMPT == "<image>document parsing."
    assert worker.MODES["quality"] == {"base_size": 1024, "image_size": 640, "crop_mode": True}
    assert worker.MODES["fast"] == {"base_size": 1024, "image_size": 1024, "crop_mode": False}
    assert (worker.NO_REPEAT_NGRAM_SIZE, worker.NGRAM_WINDOW) == (35, 128)


def test_cancel_stops_generation(worker):
    control = worker.Control()
    control.begin("7", time_limit_s=300)
    control.prefix_tokens = 100
    assert control.should_stop(101) is False
    control.cancel("other")
    assert control.should_stop(102) is False
    control.cancel("7")
    assert control.should_stop(103) is True
    assert control.cancelled and not control.timed_out


def test_cancel_before_the_page_starts(worker):
    control = worker.Control()
    control.cancel("8")
    control.begin("8", time_limit_s=300)
    assert control.should_stop(1) is True and control.cancelled


def test_shutdown_cancel_hits_whatever_runs(worker):
    control = worker.Control()
    control.begin("9", time_limit_s=300)
    control.cancel(None)
    assert control.should_stop(1) is True


@pytest.fixture
def clock(worker, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(worker.time, "monotonic", lambda: now[0])
    return now


def test_time_limit(worker, clock):
    control = worker.Control()
    control.begin("1", time_limit_s=300)
    clock[0] += 299
    assert control.should_stop(1) is False
    clock[0] += 2
    assert control.should_stop(2) is True
    assert control.timed_out and not control.cancelled


def test_progress_is_throttled(worker, clock):
    control = worker.Control()
    control.begin("3", time_limit_s=300)
    control.prefix_tokens = 1000
    clock[0] += 0.2
    control.should_stop(1001)                 # too early: no event yet
    clock[0] += 0.4
    control.should_stop(1010)                 # 0.6 s after the start: event
    clock[0] += 0.1
    control.should_stop(1011)                 # 0.1 s after the last event: none
    clock[0] += 0.5
    control.should_stop(1020)
    assert worker.sent == [{"event": "progress", "id": "3", "tokens": 10},
                           {"event": "progress", "id": "3", "tokens": 20}]


def test_out_of_memory_detection(worker):
    assert worker._is_out_of_memory(MemoryError())
    assert worker._is_out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    assert worker._is_out_of_memory(RuntimeError("DefaultCPUAllocator: can't allocate memory"))
    assert not worker._is_out_of_memory(ValueError("out of memory"))
    assert not worker._is_out_of_memory(RuntimeError("shape mismatch"))


def test_check_image(worker, tmp_path):
    good = tmp_path / "good.png"
    Image.new("RGB", (10, 10), "white").save(good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert worker._check_image(str(good)) is None
    assert "cannot read image" in worker._check_image(str(bad))
    assert "no such file" in worker._check_image(str(tmp_path / "missing.png"))


def test_handle_without_model(worker, tmp_path):
    engine = worker.Engine()
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "white").save(image)
    worker.handle(engine, {"cmd": "ping", "id": "1"})
    worker.handle(engine, {"cmd": "ocr", "id": "2", "image": str(image), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    worker.handle(engine, {"cmd": "dance", "id": "3"})
    worker.handle(engine, {"cmd": "unload", "id": "4"})
    assert worker.sent[0] == {"event": "pong", "id": "1"}
    assert worker.sent[1]["kind"] == "not_loaded"
    assert worker.sent[2]["kind"] == "internal"
    assert worker.sent[3] == {"event": "unloaded", "id": "4"}


def test_handle_bad_image_and_bad_mode(worker, tmp_path):
    engine = worker.Engine()
    engine.model = object()                  # pretend a model is loaded; ocr is never reached
    worker.handle(engine, {"cmd": "ocr", "id": "5", "image": str(tmp_path / "x.png"), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    worker.handle(engine, {"cmd": "ocr", "id": "6", "image": "x", "mode": "turbo",
                           "max_new_tokens": 10, "time_limit_s": 5})
    assert worker.sent[0]["kind"] == "bad_image"
    assert worker.sent[1]["kind"] == "internal"


def test_handle_missing_request_field(worker, monkeypatch):
    engine = worker.Engine()
    monkeypatch.setattr(engine, "load", lambda *a: pytest.fail("load must not run"))
    engine.model = object()
    monkeypatch.setattr(engine, "ocr", lambda *a: pytest.fail("ocr must not run"))
    worker.handle(engine, {"cmd": "load", "id": "1", "model_dir": "m", "device": "cpu"})
    worker.handle(engine, {"cmd": "ocr", "id": "2", "image": "x.png", "mode": "quality", "time_limit_s": 5})
    assert worker.sent == [
        {"event": "error", "id": "1", "kind": "internal", "message": "missing field 'dtype'"},
        {"event": "error", "id": "2", "kind": "internal", "message": "missing field 'max_new_tokens'"},
    ]


def test_handle_key_error_inside_the_engine_is_logged(worker, monkeypatch, tmp_path, capsys):
    engine = worker.Engine()
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "white").save(image)

    def broken(*args):
        raise KeyError("input_ids")

    monkeypatch.setattr(engine, "load", broken)
    monkeypatch.setattr(engine, "ocr", broken)
    worker.handle(engine, {"cmd": "load", "id": "1", "model_dir": "m", "device": "cpu", "dtype": "float32"})
    engine.model = object()
    worker.handle(engine, {"cmd": "ocr", "id": "2", "image": str(image), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    assert [(e["id"], e["kind"], e["message"]) for e in worker.sent] == [
        ("1", "internal", "KeyError: 'input_ids'"), ("2", "internal", "KeyError: 'input_ids'")]
    err = capsys.readouterr().err
    assert err.count("Traceback") == 2 and "in broken" in err


def test_exit_removes_the_scratch_folders(worker, monkeypatch):
    first, second = worker.Engine(), worker.Engine()
    (first.scratch / "images").mkdir()
    (first.scratch / "images" / "crop.jpg").write_bytes(b"x")
    codes = []
    monkeypatch.setattr(worker.os, "_exit", codes.append)
    worker._exit(0)
    assert codes == [0]
    assert not first.scratch.exists() and not second.scratch.exists()


def test_worker_never_uses_save_results():
    source = (REPO / "worker" / "owl_worker.py").read_text(encoding="utf-8")
    assert "save_results=True" not in source.replace("NEVER save_results=True", "")
    assert "eval_mode=True" in source
    assert "attn_implementation=" not in source
    assert not re.search(r"^\s*(import|from)\s+owlocr", source, re.M)


def test_worker_env_defaults(worker):
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


def test_engine_requirements_pin_the_design_versions():
    text = (REPO / "worker" / "requirements-engine.txt").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert {"transformers==4.57.1", "tokenizers>=0.22,<0.23", "huggingface_hub>=0.34,<1.0",
            "safetensors>=0.4.3", "accelerate", "Pillow==12.1.1", "einops==0.8.2", "addict==2.4.0",
            "easydict==1.13", "matplotlib==3.10.8", "psutil==7.2.2", "numpy<3"} <= lines
    assert not any(line.lower().startswith(("torch", "pymupdf")) for line in lines)


def test_prefill_check_only_runs_before_the_first_token(worker, clock):
    """Before the first token the forward-pass check ends a page that is out of time or
    cancelled; once tokens exist it leaves the stop to should_stop(), so the text is kept."""
    control = worker.Control()
    assert control.prefill_should_stop() is False              # no page running
    control.begin("1", time_limit_s=300)
    clock[0] += 299
    assert control.prefill_should_stop() is False
    clock[0] += 2
    assert control.prefill_should_stop() is True
    assert control.timed_out and not control.cancelled

    control.begin("2", time_limit_s=300)
    control.cancel("2")
    assert control.prefill_should_stop() is True and control.cancelled

    control.begin("3", time_limit_s=300)
    control.should_stop(1)                                      # the first token exists
    clock[0] += 301
    assert control.prefill_should_stop() is False
    assert control.should_stop(2) is True and control.timed_out


def test_worker_exits_after_answering_when_the_gpu_is_stuck(worker, monkeypatch, tmp_path):
    """A page that timed out before its first token on the GPU leaves queued GPU work that cannot
    be cancelled: the worker sends the result first, then exits."""
    engine = worker.Engine()
    engine.model = object()
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "white").save(image)
    result = {"event": "result", "id": "1", "timed_out": True}

    def stuck_ocr(*args):
        engine.gpu_stuck = True
        return result

    monkeypatch.setattr(engine, "ocr", stuck_ocr)
    monkeypatch.setattr(worker, "_exit", lambda code: worker.sent.append(("exit", code)))
    worker.handle(engine, {"cmd": "ocr", "id": "1", "image": str(image), "mode": "quality",
                           "max_new_tokens": 10, "time_limit_s": 5})
    assert worker.sent == [dict(result, engine_exiting=True), ("exit", 0)]


def test_graphics_memory_cache_is_released_after_every_page(worker, monkeypatch, tmp_path):
    """expandable_segments does not work on Windows, so the allocator cache fragments from page to
    page; on the GPU run of 2026-09-28 the eighth page no longer fit and spilled into shared
    memory. The cache is released after each page, except after a stuck page (that waits for the
    GPU; the worker exits instead)."""
    engine = worker.Engine()
    engine.model = object()
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "white").save(image)
    stuck = [False]

    def ocr(*args):
        engine.gpu_stuck = stuck[0]
        return {"event": "result", "id": args[0]}

    monkeypatch.setattr(engine, "ocr", ocr)
    monkeypatch.setattr(worker, "_free_cuda_cache", lambda: worker.sent.append("freed"))
    monkeypatch.setattr(worker, "_exit", lambda code: worker.sent.append(("exit", code)))
    request = {"cmd": "ocr", "image": str(image), "mode": "quality", "max_new_tokens": 10, "time_limit_s": 5}
    worker.handle(engine, dict(request, id="1"))
    stuck[0] = True
    worker.handle(engine, dict(request, id="2"))
    assert worker.sent == [{"event": "result", "id": "1"}, "freed",
                           {"event": "result", "id": "2", "engine_exiting": True}, ("exit", 0)]


def test_shutdown_before_the_page_begins_is_not_lost(worker):
    """A shutdown read after the ocr was dequeued but before begin() must still stop that page."""
    control = worker.Control()
    control.cancel(None)
    control.begin("x", time_limit_s=300)
    assert control.should_stop(1) is True and control.cancelled
