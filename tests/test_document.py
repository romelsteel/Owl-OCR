import json

from owlocr.pipeline import document
from owlocr.pipeline.document import Flag
from tests.samples import sample_document


def test_furniture_labels():
    assert document.FURNITURE_LABELS == ("page_number", "header", "footer")


def test_json_round_trip():
    doc = sample_document()
    text = document.to_json(doc)
    assert "Buněčné dýchání" in text                   # UTF-8, not \u escapes
    back = document.from_json(text)
    assert back == doc
    assert isinstance(back.pages[0].blocks[0].box, tuple)
    assert isinstance(back.pages[0].blocks[2].flags[0], Flag)
    assert json.loads(text)["pages"][1]["source"] == "blank"


def test_sidecar(tmp_path):
    doc = sample_document()
    path = tmp_path / "kniha.owl.json"
    document.save_sidecar(doc, path)
    assert document.load_sidecar(path) == doc


def test_block_without_box_round_trips():
    doc = sample_document()
    doc.pages[0].blocks[1].box = None
    assert document.from_json(document.to_json(doc)).pages[0].blocks[1].box is None
