import json

from tests.owl_helpers import between, static_text

PALETTE_CHARS = set("kblcwpyf.")


def _frames() -> dict:
    return json.loads(between(static_text("owl.js"), "/*FRAMES-BEGIN*/", "/*FRAMES-END*/"))


def test_frames_cover_every_state():
    assert set(_frames()) == {"sleeping", "awake", "reading_left", "reading_right", "ruffled", "turned"}


def test_frames_are_16_by_16_with_known_colours():
    for name, rows in _frames().items():
        assert len(rows) == 16, name
        for row in rows:
            assert len(row) == 16, (name, row)
            assert set(row) <= PALETTE_CHARS, (name, row)


def test_reading_frames_move_the_eyes():
    frames = _frames()
    assert frames["reading_left"] != frames["reading_right"]
    assert frames["sleeping"] != frames["awake"]


def test_mascot_api_and_easter_egg():
    text = static_text("owl.js")
    assert "window.OwlMascot" in text and "setState" in text and "init" in text
    assert "clicks >= 5" in text and "'turned'" in text
