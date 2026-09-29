"""Plan C: the real dictionaries against the error examples measured in the spike.

Needs the network: run with OWLOCR_NETWORK_TESTS=1 (skipped otherwise)."""
import os

import pytest

from owlocr.pipeline import dictionaries, spellcheck


@pytest.mark.skipif(os.environ.get("OWLOCR_NETWORK_TESTS") != "1",
                    reason="set OWLOCR_NETWORK_TESTS=1 to download the real dictionaries")
def test_real_czech_dictionary_handles_the_spike_examples(no_dicts):
    from owlocr.pipeline import layout, repair
    from owlocr.pipeline.document import Block

    dictionaries.download("cs")
    cases = {
        "Je to bud' pravda, nebo lež.": "Je to buď pravda, nebo lež.",
        "Účet byl uhrazen pojišt’ovnou.": "Účet byl uhrazen pojišťovnou.",
        "Druh kaprad roste v lese.": "Druh kapraď roste v lese.",
        "Je to także dobré.": "Je to takže dobré.",
        "Čeleď kaktu-sovitých roste v poušti.": "Čeleď kaktusovitých roste v poušti.",
    }
    for raw, expected in cases.items():
        block = layout.arrange([Block("text", (0, 0, 999, 999), raw, raw, [])], "cs")[0]
        assert repair.repair_block(block, "cs", set()).text == expected, raw
    text = "Rod Opuntia patří mezi bylinny druh."
    flagged = spellcheck.flag_suspicious(Block("text", None, text, text, []), "cs", set())
    assert [(f.kind, f.original) for f in flagged.flags] == [("suspicious", "bylinny")]
