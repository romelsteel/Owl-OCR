import pytest
from tests.owl_helpers import FAKE_WORKER

from owlocr.engine.protocol import EngineError
from owlocr.jobs import engines


def test_worker_override_builds_engine_that_runs_that_worker(monkeypatch):
    monkeypatch.setenv(engines.WORKER_ENV, str(FAKE_WORKER))
    engines.forget_installed()
    engine = engines.engine_factory()
    assert engines.engine_installed() is True
    assert not engine.is_running()  # building an engine never starts it
    try:
        info = engine.start()
        assert info.torch == "fake"  # only tests/fake_worker.py reports torch "fake"
        assert engine.is_running()
    finally:
        engine.stop()
    engines.forget_installed()


def test_not_installed_without_override(monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)

    monkeypatch.setattr(engines.bootstrap, "is_installed", lambda: False)
    engines.forget_installed()
    assert engines.engine_installed() is False
    engines.forget_installed()


def test_answer_is_cached_until_forgotten(monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)
    calls = []

    def fine():
        calls.append(1)
        return True
    monkeypatch.setattr(engines.bootstrap, "is_installed", fine)
    engines.forget_installed()
    assert engines.engine_installed() and engines.engine_installed()
    assert len(calls) == 1
    engines.forget_installed()
    engines.engine_installed()
    assert len(calls) == 2
    engines.forget_installed()


def test_factory_refuses_when_not_installed(monkeypatch):
    monkeypatch.delenv(engines.WORKER_ENV, raising=False)
    monkeypatch.setattr(engines.bootstrap, "is_installed", lambda: False)
    with pytest.raises(EngineError) as caught:
        engines.engine_factory()
    assert caught.value.kind == "not_installed"
