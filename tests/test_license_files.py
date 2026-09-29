import hashlib

from tests.conftest import REPO

APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_apache_text_is_the_official_one():
    data = (REPO / "licenses" / "Apache-2.0.txt").read_bytes()
    assert hashlib.sha256(data).hexdigest() == APACHE_SHA256


def test_engine_requirements_keep_the_pins():
    text = (REPO / "worker" / "requirements-engine.txt").read_text(encoding="utf-8")
    assert "transformers==4.57.1" in text
    assert "torch" not in [line.split("=")[0].strip() for line in text.splitlines()]
