"""Shared test setup.

Every test gets its own OWLOCR_HOME and OWLOCR_CONFIG inside pytest's tmp folder, so no test
ever reads or writes the real %APPDATA% / %LOCALAPPDATA% (design 4.1: tools started from the
Claude desktop app get those folders silently redirected).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
PAGES = FIXTURES / "pages"
RAW = FIXTURES / "raw"
FAKE_WORKER = REPO / "tests" / "fake_worker.py"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def owl_env(tmp_path, monkeypatch):
    home = tmp_path / "owl_home"
    config = tmp_path / "owl_config"
    home.mkdir()
    config.mkdir()
    monkeypatch.setenv("OWLOCR_HOME", str(home))
    monkeypatch.setenv("OWLOCR_CONFIG", str(config))
    monkeypatch.delenv("FAKE_WORKER", raising=False)
    return {"home": home, "config": config}


# ---- plan C: tiny offline Hunspell dictionaries --------------------------------------------
import pytest  # noqa: E402  (repeated on purpose: this block must work on its own)

TINY_CS_WORDS = """
a i v ve k s z o u na je to se byl byla buď nebo také takže list listy listu rostlina
rostliny kapraď kapradí pojišťovnou uhrazen účet kaktusovitých čeleď rod druh bylinný
stonek květ dřevitý dnes pacient lékař zpráva řapík řapíku ťukat dub buk strom roste
mají jsou pro velký malý dopis česko slovenský stránka text obrázek viz dole nahoře
Praha Brno
""".split()

TINY_EN_WORDS = """
a the and is of to in this page text house water tree green leaf leaves letter doctor
report it was on for with
""".split()

TINY_AFF = "SET UTF-8\nTRY aeiouyáéíóúůýěčďňřšťžbcdfghjklmnpqrstvwxz\n"


def _write_tiny_dictionary(folder, name, words):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.aff").write_text(TINY_AFF, encoding="utf-8")
    unique = sorted(set(words))
    (folder / f"{name}.dic").write_text(f"{len(unique)}\n" + "\n".join(unique) + "\n",
                                        encoding="utf-8")


@pytest.fixture
def tiny_dicts(tmp_path, monkeypatch):
    """OWLOCR_HOME with a tiny Czech and English dictionary; returns the dictionaries folder."""
    from owlocr.pipeline import spellcheck
    home = tmp_path / "owl_home_dicts"
    monkeypatch.setenv("OWLOCR_HOME", str(home))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "owl_config_dicts"))
    folder = home / "dictionaries"
    _write_tiny_dictionary(folder, "cs_CZ", TINY_CS_WORDS)
    _write_tiny_dictionary(folder, "en_US", TINY_EN_WORDS)
    spellcheck._reset_cache()
    yield folder
    spellcheck._reset_cache()


@pytest.fixture
def no_dicts(tmp_path, monkeypatch):
    """OWLOCR_HOME without any dictionary."""
    from owlocr.pipeline import spellcheck
    monkeypatch.setenv("OWLOCR_HOME", str(tmp_path / "owl_home_empty"))
    monkeypatch.setenv("OWLOCR_CONFIG", str(tmp_path / "owl_config_empty"))
    spellcheck._reset_cache()
    yield
    spellcheck._reset_cache()
