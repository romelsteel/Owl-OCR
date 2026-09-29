import json

import pytest

from owlocr.jobs.queue import STATES, Job, JobQueue, seconds_left
from tests.owl_helpers import make_tiff


def test_add_counts_pages_and_persists(tmp_path):
    src = make_tiff(tmp_path / "in" / "book.tif", pages=3)
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([src])
    assert job.state == "pending" and job.pages_total == 3 and job.pages_done == 0
    assert job.mode is None and job.outputs == {} and job.finished is None
    again = JobQueue(tmp_path / "queue.json")
    assert [j.id for j in again.all()] == [job.id]
    assert again.get(job.id).source == str(src)


def test_unreadable_file_becomes_failed_job(tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([bad])
    assert job.state == "failed" and job.error


def test_running_becomes_pending_on_load(tmp_path):
    src = make_tiff(tmp_path / "a.tif")
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([src])
    q.update(job.id, state="running", pages_done=0)
    reloaded = JobQueue(tmp_path / "queue.json")
    assert reloaded.get(job.id).state == "pending"
    on_disk = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert on_disk["jobs"][0]["state"] == "pending"


def test_paused_stays_paused_on_load(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    q.update(job.id, state="paused")
    assert JobQueue(tmp_path / "queue.json").get(job.id).state == "paused"


def test_update_validates(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    with pytest.raises(ValueError):
        q.update(job.id, state="exploded")
    with pytest.raises(ValueError):
        q.update(job.id, mode="turbo")
    with pytest.raises(ValueError):
        q.update(job.id, id="other")
    with pytest.raises(KeyError):
        q.update("missing", state="done")
    assert q.update(job.id, mode="fast").mode == "fast"
    assert q.update(job.id, mode=None).mode is None


def test_returned_jobs_are_copies(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    job.outputs["md"] = "x"
    job.state = "done"
    assert q.get(job.id).outputs == {} and q.get(job.id).state == "pending"


def test_next_pending_reorder_remove_clear(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    a, b, c = q.add([make_tiff(tmp_path / f"{n}.tif") for n in "abc"])
    assert q.next_pending().id == a.id
    q.reorder([c.id, "unknown", a.id])
    assert [j.id for j in q.all()] == [c.id, a.id, b.id]
    q.update(c.id, state="done")
    assert q.next_pending().id == a.id
    q.update(a.id, state="failed")
    q.update(b.id, state="cancelled")
    q.clear_finished()
    assert q.all() == []
    [d] = q.add([make_tiff(tmp_path / "d.tif")])
    q.remove(d.id)
    assert q.all() == [] and q.next_pending() is None
    with pytest.raises(KeyError):
        q.remove(d.id)


def test_clear_keeps_unfinished(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    a, b = q.add([make_tiff(tmp_path / "a.tif"), make_tiff(tmp_path / "b.tif")])
    q.update(a.id, state="paused")
    q.update(b.id, state="done")
    q.clear_finished()
    assert [j.id for j in q.all()] == [a.id]


def test_corrupt_file_is_set_aside(tmp_path):
    (tmp_path / "queue.json").write_text("{not json", encoding="utf-8")
    q = JobQueue(tmp_path / "queue.json")
    assert q.all() == []
    assert not (tmp_path / "queue.json").exists()
    assert any(p.name.startswith("queue.json") for p in tmp_path.iterdir())


def test_seconds_left():
    job = Job(id="x", source="s", state="running", mode=None, pages_total=10, pages_done=4,
              warnings=0, error=None, outputs={}, seconds=40.0, added="", finished=None)
    assert seconds_left(job) == pytest.approx(60.0)
    job.pages_done = 0
    assert seconds_left(job) is None


def test_states_constant():
    assert STATES == ("pending", "running", "paused", "done", "failed", "cancelled")


def test_merge_outputs_keeps_entries_written_since_a_read(tmp_path):
    q = JobQueue(tmp_path / "queue.json")
    [job] = q.add([make_tiff(tmp_path / "a.tif")])
    stale = q.get(job.id)                                   # outputs == {} in this snapshot
    q.update(job.id, outputs={"md": "a.md", "owl": "a.owl.json"})
    merged = q.merge_outputs(stale.id, {"txt": "a.txt", "md": "a_1.md"})
    assert merged.outputs == {"md": "a_1.md", "owl": "a.owl.json", "txt": "a.txt"}
    assert JobQueue(tmp_path / "queue.json").get(job.id).outputs == merged.outputs
    with pytest.raises(KeyError):
        q.merge_outputs("nope", {})


def test_relocate_saves_to_the_new_path(tmp_path):
    src = make_tiff(tmp_path / "in" / "a.tif")
    q = JobQueue(tmp_path / "old" / "queue.json")
    [job] = q.add([src])
    q.relocate(tmp_path / "new" / "queue.json")
    assert (tmp_path / "new" / "queue.json").is_file()
    assert [j.id for j in JobQueue(tmp_path / "new" / "queue.json").all()] == [job.id]
    q.update(job.id, state="paused")          # later writes go to the new file too
    assert JobQueue(tmp_path / "new" / "queue.json").get(job.id).state == "paused"
