"""Known engines and their pinned versions (design 5.1)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    repo: str
    revision: str
    ignore: tuple[str, ...]
    weights_sha256: str
    modelscope_repo: str
    torch: str
    torchvision: str
    transformers: str
    # Every file of the pinned revision: (relative path, size, sha256 for LFS files, git blob sha1
    # for the others). adopt() verifies a folder against this set (never the folder's own manifest)
    # and download() fetches exactly this set. Empty = not pinned (then the remote file list is used).
    files: tuple[tuple[str, int, str | None, str | None], ...] = ()


# From the verified download of revision 07dea83 (engine/models/unlimited_ocr/manifest.json).
_UNLIMITED_OCR_FILES = (
    ("LICENSE", 1061, None, "890d455ae73d1d930eee703ce1e5478783ec9154"),
    ("README.md", 11108, None, "9a9880ab7dac523e66ff68ca9acc2e1235fab662"),
    ("config.json", 2881, None, "51871434df16d1a04dbf190565e1a4e0d5f48037"),
    ("configuration_deepseek_v2.py", 10720, None, "1c28cf39e8b821ec2623d3762f08ffd77050e8f8"),
    ("conversation.py", 9253, None, "65c295e81cd804080ec238b31d1922f33e1f9405"),
    ("deepencoder.py", 38008, None, "de1687dfec3a4a8a00980a8444baba0082ce779b"),
    ("model-00001-of-000001.safetensors", 6672547120,
     "2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6", None),
    ("model.safetensors.index.json", 257611, None, "927d176a228105e796dd2193e33351bef791adcf"),
    ("modeling_deepseekv2.py", 90162, None, "17d5c358a6010e71fa1f3cc2040cd3e5508ccd1b"),
    ("modeling_unlimitedocr.py", 53431, None, "c329779827aa29c4b37d97c5510416aa3a9fde18"),
    ("processor_config.json", 466, None, "6b3c4e7b325d9ec404182a3b0585a988cc883d1f"),
    ("special_tokens_map.json", 801, None, "d59d312be868edc63b195e19e256c730dba685ad"),
    ("tokenizer.json", 9979544, None, "c93a1c4d2ecf31bb5a9ec39eb73dfbf915aaf77e"),
    ("tokenizer_config.json", 165938, None, "ba9d4175d69cde58ad9f68a76a4758df091eaffa"),
)

UNLIMITED_OCR = EngineSpec(
    engine_id="unlimited_ocr",
    repo="baidu/Unlimited-OCR",
    revision="07dea832e22aefee32ad281d4b80551282e1c168",
    ignore=("assets/*", "wheel/*", "*.pdf", "*.gif", ".gitattributes"),
    weights_sha256="2bc48a7a110061ea58fff65d3169367eebe3aee371ca6968dc2219c1b2855fc6",
    modelscope_repo="PaddlePaddle/Unlimited-OCR",
    torch="2.10.0",
    torchvision="0.25.0",
    transformers="4.57.1",
    files=_UNLIMITED_OCR_FILES,
)

_ENGINES = {UNLIMITED_OCR.engine_id: UNLIMITED_OCR}


def get(engine_id: str) -> EngineSpec:
    try:
        return _ENGINES[engine_id]
    except KeyError:
        raise KeyError(f"unknown engine: {engine_id}") from None
