from tests.conftest import REPO

EN = (REPO / "README.md").read_text(encoding="utf-8")
CS = (REPO / "README.cs.md").read_text(encoding="utf-8")


def test_english_readme_covers_the_required_topics():
    for needle in ("570.65", "16 GB", "10 GB", "6.7 GB", "2.9 GB", "SmartScreen", "Run anyway",
                   "3 wrong words in 100", "another real word", "block by block", "## Privacy",
                   "## Uninstalling", "MIT License", "Apache", "I already have the engine",
                   "README.cs.md",
                   "LibreOffice dictionaries", "GNU GPL", "SCOWL", "only these checks are",
                   "Settings → Image links", "Open images folder", "creates an `OwlOCR` subfolder",
                   "raw.githubusercontent.com", "build\\venv", "not measured separately"):
        assert needle in EN, needle


def test_czech_readme_covers_the_required_topics():
    for needle in ("570.65", "16 GB", "10 GB", "6,7 GB", "2,9 GB", "SmartScreen", "Přesto spustit",
                   "3 chybná slova ze 100", "jiným skutečným slovem", "po blocích", "## Soukromí",
                   "## Odinstalace", "MIT", "Apache", "Engine už mám",
                   "README.md",
                   "LibreOffice dictionaries", "GNU GPL", "SCOWL", "jen tyto kontroly vynechá",
                   "Odkazy na obrázky", "Otevřít složku s obrázky", "podsložku `OwlOCR`",
                   "raw.githubusercontent.com", "build\\venv", "zvlášť neměřeno",
                   "## Jak přesný je Owl OCR?"):
        assert needle in CS, needle


def test_hardware_tables_have_the_same_rows():
    rows = lambda text: [l for l in text.splitlines() if l.startswith("| ") and "---" not in l]
    assert len(rows(EN)) == len(rows(CS))


def test_no_unmeasured_speed_or_impossible_hardware():
    """I-3: the memory-saving tier has no measured speed; no GTX 16 card has 8 GB."""
    for text in (EN, CS):
        assert "GTX 16" not in text
        assert "30 to 70" not in text and "30 až 70" not in text


def test_privacy_list_mentions_redirect_servers():
    """M-5: the host list is not presented as complete."""
    assert "and the servers these redirect to" in EN
    assert "a servery, na které tyto adresy přesměrují" in CS
