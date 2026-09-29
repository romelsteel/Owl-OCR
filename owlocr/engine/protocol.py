"""JSON-lines protocol between the app and the engine worker (design 5.4).

One JSON object per line, UTF-8. Requests carry "cmd", events carry "event".
worker/owl_worker.py and tests/fake_worker.py speak the same protocol without importing this
module (the worker runs in the engine's own Python, where owlocr is not installed).
"""
import json
from dataclasses import dataclass

MODES = ("quality", "fast")

REQUEST_FIELDS = {
    "load": ("id", "model_dir", "device", "dtype"),
    "ocr": ("id", "image", "mode", "max_new_tokens", "time_limit_s"),
    "cancel": ("id",),
    "unload": ("id",),
    "ping": ("id",),
    "shutdown": ("id",),
}

EVENT_FIELDS = {
    "ready": ("pid", "torch", "transformers", "cuda_available", "gpu_name"),
    "loaded": ("id", "seconds", "vram_mib"),
    "progress": ("id", "tokens"),
    "result": ("id", "text", "seconds", "prefix_tokens", "output_tokens", "hit_token_cap",
               "cancelled", "timed_out", "peak_vram_mib"),
    "error": ("id", "kind", "message"),
    "pong": ("id",),
    "unloaded": ("id",),
    "bye": ("id",),
}


class ProtocolError(ValueError):
    pass


def encode(message: dict) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode(line: str) -> dict:
    try:
        message = json.loads(line)
    except ValueError as e:
        raise ProtocolError(f"not JSON: {line[:200]!r}") from e
    if not isinstance(message, dict):
        raise ProtocolError(f"not a JSON object: {line[:200]!r}")
    if "cmd" in message:
        fields = REQUEST_FIELDS.get(message["cmd"])
        what = f"request {message['cmd']!r}"
    elif "event" in message:
        fields = EVENT_FIELDS.get(message["event"])
        what = f"event {message['event']!r}"
    else:
        raise ProtocolError(f"neither cmd nor event: {line[:200]!r}")
    if fields is None:
        raise ProtocolError(f"unknown {what}")
    missing = [f for f in fields if f not in message]
    if missing:
        raise ProtocolError(f"{what} is missing {', '.join(missing)}")
    return message


@dataclass
class EngineInfo:
    pid: int
    torch: str
    transformers: str
    cuda_available: bool
    gpu_name: str | None


@dataclass
class PageResult:
    text: str
    seconds: float
    prefix_tokens: int
    output_tokens: int
    hit_token_cap: bool
    cancelled: bool
    timed_out: bool
    peak_vram_mib: int


class EngineError(RuntimeError):
    """kind: 'out_of_memory' | 'bad_image' | 'not_loaded' | 'internal' | 'died' | 'not_installed'"""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind
        self.message = message
