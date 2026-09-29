"""The real worker in the engine's Python (torch + transformers), with CUDA hidden.

Never loads the OCR model and never touches the GPU: CUDA_VISIBLE_DEVICES=-1 hides every GPU.
Skipped when no engine Python is available. Uses OWLOCR_TEST_ENGINE_PYTHON, else the spike venv.
"""
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from owlocr.engine import lifetime
from owlocr.engine.client import SubprocessEngine
from owlocr.engine.protocol import EngineError
from tests.conftest import REPO

ENGINE_PYTHON = Path(os.environ.get("OWLOCR_TEST_ENGINE_PYTHON")
                     or REPO / "spike" / ".venv" / "Scripts" / "python.exe")
WORKER = REPO / "worker" / "owl_worker.py"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ENGINE_PYTHON.is_file(), reason=f"no engine Python at {ENGINE_PYTHON}"),
]


def worker_env(tmp_path) -> dict:
    """GPU hidden, and the worker's temp folder inside tmp_path so the test can see it."""
    temp = tmp_path / "temp"
    temp.mkdir(exist_ok=True)
    return {"CUDA_VISIBLE_DEVICES": "-1", "TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp)}


def scratch_folders(tmp_path) -> list[Path]:
    return sorted((tmp_path / "temp").glob("owl_worker_*"))


def make_engine(tmp_path) -> SubprocessEngine:
    return SubprocessEngine(python=ENGINE_PYTHON, worker_script=WORKER, model_dir=tmp_path / "no_model",
                            device="cpu", dtype="float32", log_file=tmp_path / "engine.log",
                            env=worker_env(tmp_path))


def test_real_worker_protocol_without_model(tmp_path):
    engine = make_engine(tmp_path)
    try:
        info = engine.start()
        assert info.torch.startswith("2.")
        assert info.transformers == "4.57.1"
        assert info.cuda_available is False and info.gpu_name is None
        assert len(scratch_folders(tmp_path)) == 1
        with pytest.raises(EngineError) as e:
            engine.ocr_page(REPO / "tests" / "fixtures" / "pages" / "01_letter_clean.png", "quality")
        assert e.value.kind == "not_loaded"
        with pytest.raises(EngineError) as e:
            engine.load()                     # the model folder does not exist
        assert e.value.kind == "internal"
        assert engine.is_running()
    finally:
        engine.stop()
    assert not lifetime.process_alive(info.pid)
    assert scratch_folders(tmp_path) == []    # shutdown removed the worker's scratch folder
    log = (tmp_path / "engine.log").read_text(encoding="utf-8", errors="replace")
    assert "Traceback" in log                 # the failed load was logged to stderr, not stdout


def test_real_worker_exits_on_stdin_eof(tmp_path):
    env = dict(os.environ, **worker_env(tmp_path))
    p = subprocess.Popen([str(ENGINE_PYTHON), str(WORKER), "--parent-pid", str(os.getpid())],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    try:
        assert b'"ready"' in p.stdout.readline()
        assert len(scratch_folders(tmp_path)) == 1
        p.stdin.close()
        assert p.wait(timeout=10) == 0
    finally:
        p.kill()
        p.wait(timeout=10)
    assert scratch_folders(tmp_path) == []


def test_generate_wrapper_on_a_tiny_model(tmp_path):
    """The generate() wrapper with a 1-layer random GPT-2 on the CPU: max_new_tokens becomes
    max_length, the prefix is learned, the token cap is reported, and cancel stops generation."""
    script = textwrap.dedent(f"""
        import importlib.util, json, sys
        import torch
        from transformers import GPT2Config, GPT2LMHeadModel
        spec = importlib.util.spec_from_file_location("w", r"{WORKER}")
        w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
        events = []
        w.send = events.append
        torch.manual_seed(0)
        model = GPT2LMHeadModel(GPT2Config(n_layer=1, n_head=2, n_embd=16, vocab_size=50,
                                           n_positions=64)).eval()
        engine = w.Engine()
        engine._wrap_generate(model)
        ids = torch.tensor([[1, 2, 3, 4, 5, 6, 7]])
        engine.max_new_tokens = 5
        w.CONTROL.begin("a", 300)
        out = model.generate(input_ids=ids, max_length=60, do_sample=False, eos_token_id=None,
                             pad_token_id=0)
        first = dict(engine.last, length=int(out.shape[1]))
        engine.max_new_tokens = 40
        w.CONTROL.begin("b", 300)
        w.CONTROL.cancel("b")
        try:
            model.generate(input_ids=ids, max_length=60, do_sample=False, eos_token_id=None,
                           pad_token_id=0)
            raised = False
        except w.PageStopped:
            raised = True
        second = dict(engine.last, raised=raised, cancelled=w.CONTROL.cancelled)
        w._remove_scratch()
        print(json.dumps([first, second]))
    """)
    env = dict(os.environ, **worker_env(tmp_path))
    out = subprocess.run([str(ENGINE_PYTHON), "-c", script], capture_output=True, text=True, env=env,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    first, second = json.loads(out.stdout.strip().splitlines()[-1])
    assert first == {"prefix_tokens": 7, "output_tokens": 5, "hit_token_cap": True, "length": 12}
    assert second["cancelled"] is True
    # cancelled before the first token: the forward-pass check ends it before anything is generated
    assert second["raised"] is True
    assert second["output_tokens"] == 0 and second["hit_token_cap"] is False
    assert scratch_folders(tmp_path) == []



def test_time_limit_ends_a_slow_first_pass(tmp_path):
    """The time limit must also end a page whose first forward pass (vision encoder + prompt) is
    slow. The stopping criteria run only once a token exists, so a page stuck before its first
    token never timed out (GPU run 2026-09-28: 08_screenshot spilled out of VRAM and sat in the
    vision encoder for over 7 minutes). The page must also leave infer() without its decode step,
    which on the GPU waits for all queued work. Here: an 8-layer GPT-2 whose first pass sleeps
    0.25 s per layer (2 s in all), a 0.3 s limit, and an infer() that records its decode step."""
    image = tmp_path / "page.png"
    Image.new("RGB", (10, 10), "white").save(image)
    script = textwrap.dedent(f"""
        import importlib.util, json, sys, time
        import torch
        from transformers import GPT2Config, GPT2LMHeadModel
        spec = importlib.util.spec_from_file_location("w", r"{WORKER}")
        w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
        events, exits, decoded = [], [], []
        w.send = events.append
        w._exit = exits.append
        torch.manual_seed(0)
        model = GPT2LMHeadModel(GPT2Config(n_layer=8, n_head=2, n_embd=16, vocab_size=50,
                                           n_positions=64)).eval()
        model.config.sliding_window = 128

        def slow_first_pass(module, args, kwargs):
            hidden = args[0] if args else kwargs["hidden_states"]
            if hidden.shape[1] > 1:
                time.sleep(0.25)

        for block in model.transformer.h:
            block.register_forward_pre_hook(slow_first_pass, with_kwargs=True)

        def infer(tokenizer, **kwargs):          # the shape of the model's own infer()
            model.config.sliding_window = None
            out = model.generate(input_ids=torch.tensor([[1, 2, 3, 4, 5, 6, 7]]), max_length=60,
                                 do_sample=False, eos_token_id=None, pad_token_id=0)
            model.config.sliding_window = 128
            decoded.append(int(out.shape[1]))    # stands for the decode that syncs with the GPU
            return "text"

        model.infer = infer
        engine = w.Engine()
        engine._wrap_generate(model)
        engine.model, engine.device = model, "cpu"
        request = {{"cmd": "ocr", "image": r"{image}", "mode": "quality", "max_new_tokens": 5}}
        w.handle(engine, dict(request, id="slow", time_limit_s=0.3))
        stuck = engine.gpu_stuck
        w.handle(engine, dict(request, id="next", time_limit_s=300))
        w._remove_scratch()
        print(json.dumps({{"events": events, "exits": exits, "decoded": decoded, "stuck": stuck,
                          "sliding_window": model.config.sliding_window}}))
    """)
    env = dict(os.environ, **worker_env(tmp_path))
    out = subprocess.run([str(ENGINE_PYTHON), "-c", script], capture_output=True, text=True, env=env,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    run = json.loads(out.stdout.strip().splitlines()[-1])
    slow, following = [e for e in run["events"] if e["event"] != "progress"]
    assert slow["event"] == "result" and slow["id"] == "slow"
    assert slow["timed_out"] is True and slow["cancelled"] is False
    assert slow["seconds"] < 1.0, slow               # not the whole 2 s first pass
    assert slow["text"] == "" and slow["output_tokens"] == 0 and slow["prefix_tokens"] == 7
    assert slow["hit_token_cap"] is False
    assert run["decoded"] == [12]                    # only the second page reached the decode step
    assert run["sliding_window"] == 128              # infer() cleared it; the worker put it back
    assert run["stuck"] is False and run["exits"] == []   # on the CPU nothing is left queued
    assert "engine_exiting" not in slow
    assert following["id"] == "next" and following["text"] == "text" and following["timed_out"] is False
    assert following["output_tokens"] == 5
    assert scratch_folders(tmp_path) == []
