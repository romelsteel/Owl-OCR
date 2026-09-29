import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packaging"))
import pin_uv  # noqa: E402

SHA = "a" * 64


def test_parse_sha256_file():
    assert pin_uv.parse_sha256_file(f"{SHA} *uv-x86_64-pc-windows-msvc.zip\n") == SHA
    assert pin_uv.parse_sha256_file(SHA.upper()) == SHA
    with pytest.raises(ValueError):
        pin_uv.parse_sha256_file("<html>Not Found</html>")
    with pytest.raises(ValueError):
        pin_uv.parse_sha256_file("")


def test_digest_from_release():
    release = {"assets": [{"name": "uv-aarch64-apple-darwin.tar.gz", "digest": "sha256:" + "b" * 64},
                          {"name": pin_uv.ASSET, "digest": "sha256:" + SHA}]}
    assert pin_uv.digest_from_release(release) == SHA
    assert pin_uv.digest_from_release({"assets": [{"name": pin_uv.ASSET}]}) is None


def test_build_pins():
    pins = pin_uv.build_pins("0.12.19", SHA)
    assert pins == {"uv": {"version": "0.12.19", "sha256": SHA,
                           "url": "https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-pc-windows-msvc.zip"}}
    with pytest.raises(ValueError):
        pin_uv.build_pins("v0.12.19", SHA)


def test_pin_writes_file(tmp_path, monkeypatch):
    responses = {
        pin_uv.API_LATEST: json.dumps({"tag_name": "0.12.19", "assets": []}).encode(),
        pin_uv.asset_url("0.12.19") + ".sha256": f"{SHA} *{pin_uv.ASSET}\n".encode(),
    }
    monkeypatch.setattr(pin_uv, "_get", lambda url: responses[url])
    out = tmp_path / "pins.json"
    pin_uv.pin(None, out)
    assert json.loads(out.read_text(encoding="utf-8"))["uv"]["version"] == "0.12.19"


def test_pin_refuses_conflicting_digests(tmp_path, monkeypatch):
    responses = {
        pin_uv.API_TAG.format(tag="0.12.19"): json.dumps(
            {"tag_name": "0.12.19", "assets": [{"name": pin_uv.ASSET, "digest": "sha256:" + "c" * 64}]}).encode(),
        pin_uv.asset_url("0.12.19") + ".sha256": f"{SHA} *{pin_uv.ASSET}\n".encode(),
    }
    monkeypatch.setattr(pin_uv, "_get", lambda url: responses[url])
    with pytest.raises(ValueError, match="differs"):
        pin_uv.pin("0.12.19", tmp_path / "pins.json")


def test_committed_pins_file_is_valid():
    pins = json.loads((REPO / "owlocr" / "engine" / "pins.json").read_text(encoding="utf-8"))["uv"]
    assert len(pins["sha256"]) == 64 and int(pins["sha256"], 16) >= 0
    assert pins["url"] == pin_uv.asset_url(pins["version"])
