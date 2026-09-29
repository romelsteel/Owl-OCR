import pytest

from owlocr.engine import protocol
from owlocr.engine.protocol import EngineError, EngineInfo, PageResult, ProtocolError


def test_modes():
    assert protocol.MODES == ("quality", "fast")


def test_encode_is_one_utf8_line():
    line = protocol.encode({"event": "result", "text": "žluťoučký\nkůň"})
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert "žluťoučký" in line


def test_round_trip_every_message():
    samples = [
        {"cmd": "load", "id": "1", "model_dir": "C:\\m", "device": "cuda", "dtype": "bfloat16"},
        {"cmd": "ocr", "id": "2", "image": "C:\\p.png", "mode": "quality", "max_new_tokens": 6000,
         "time_limit_s": 300.0},
        {"cmd": "cancel", "id": "2"},
        {"cmd": "unload", "id": "3"},
        {"cmd": "ping", "id": "4"},
        {"cmd": "shutdown", "id": "5"},
        {"event": "ready", "pid": 1, "torch": "2.10.0", "transformers": "4.57.1",
         "cuda_available": True, "gpu_name": "RTX"},
        {"event": "loaded", "id": "1", "seconds": 5.1, "vram_mib": 6457},
        {"event": "progress", "id": "2", "tokens": 120},
        {"event": "result", "id": "2", "text": "x", "seconds": 1.0, "prefix_tokens": 907,
         "output_tokens": 10, "hit_token_cap": False, "cancelled": False, "timed_out": False,
         "peak_vram_mib": 9000},
        {"event": "error", "id": "2", "kind": "out_of_memory", "message": "CUDA OOM"},
        {"event": "pong", "id": "4"},
        {"event": "unloaded", "id": "3"},
        {"event": "bye", "id": "5"},
    ]
    for message in samples:
        assert protocol.decode(protocol.encode(message)) == message


@pytest.mark.parametrize("line", [
    "not json",
    "[1, 2]",
    '{"id": "1"}',
    '{"cmd": "dance", "id": "1"}',
    '{"event": "party"}',
    '{"cmd": "ocr", "id": "1", "image": "x"}',
    '{"event": "result", "id": "1", "text": "x"}',
])
def test_decode_rejects(line):
    with pytest.raises(ProtocolError):
        protocol.decode(line)


def test_protocol_error_is_value_error():
    assert issubclass(ProtocolError, ValueError)


def test_engine_error_kind():
    e = EngineError("out_of_memory", "CUDA out of memory")
    assert isinstance(e, RuntimeError)
    assert e.kind == "out_of_memory"
    assert "CUDA out of memory" in str(e)
    assert EngineError("died").kind == "died"


def test_dataclasses():
    info = EngineInfo(pid=1, torch="2.10.0", transformers="4.57.1", cuda_available=False, gpu_name=None)
    assert info.gpu_name is None
    r = PageResult(text="a", seconds=1.0, prefix_tokens=2, output_tokens=3, hit_token_cap=False,
                   cancelled=False, timed_out=False, peak_vram_mib=0)
    assert r.output_tokens == 3
