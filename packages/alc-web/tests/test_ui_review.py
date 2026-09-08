import json

import pytest

from alc_web.store import Store
from alc_web.metrics import Projection, _fold


def test_rename_does_not_change_frozen_request_or_timing_events(tmp_path):
    store = Store(tmp_path)
    job = store.create({"title": "original", "output": "source"})
    store.claim(job["id"])
    before = store.get(job["id"])
    events = store.events(job["id"])
    renamed = store.rename(job["id"], "<b>new title</b>")
    assert renamed["spec"] == before["spec"]
    assert renamed["updated"] == before["updated"]
    assert store.events(job["id"]) == events
    assert renamed["display_title"] == "<b>new title</b>"


@pytest.mark.parametrize("delete_first", [True, False])
def test_delete_and_due_recovery_are_serializable(tmp_path, delete_first):
    store = Store(tmp_path)
    job_id = store.create({"automatic_recovery": True})["id"]
    store.update(job_id, state="needs_input", error={"code": "provider_timeout"})
    assert store.schedule_recovery(job_id, now=0)
    if delete_first:
        store.delete(job_id)
        assert store.resume_due_recoveries(now=60) == 0
        with pytest.raises(ValueError):
            store.control(job_id, "resume")
    else:
        assert store.resume_due_recoveries(now=60) == 1
        with pytest.raises(ValueError):
            store.delete(job_id)
        assert not store.get(job_id)["deleted"]


def test_elapsed_excludes_pause_and_progress_survives_resume():
    projection = Projection()
    for kind, created, data in [
        ("job.started", 10, {}),
        ("job.updated", 15, {"phase": "translation", "detail": {"progress": {
            "phase": "translation", "completed_units": 8, "total_units": 10}}}),
        ("job.updated", 20, {"state": "needs_input"}),
        ("job.started", 100, {}),
        ("job.updated", 101, {"detail": {"progress": {
            "phase": "translation", "completed_units": 0, "total_units": 10}}}),
        ("job.finished", 110, {"state": "completed"}),
    ]:
        _fold(projection, {"kind": kind, "created": created, "data": data})
    assert projection.active_seconds == 20
    assert projection.active_since is None
    assert projection.percent > 80


def test_deleted_rows_do_not_hide_older_visible_job(tmp_path):
    store = Store(tmp_path)
    old = store.create({"title": "still visible"})["id"]
    with store.connect() as db:
        for i in range(500):
            job_id = f"{i:032x}"
            db.execute("INSERT INTO jobs(id,state,created,updated,spec) VALUES(?,?,?,?,?)",
                (job_id, "completed", 9999999999 + i, 9999999999, json.dumps({})))
            db.execute("INSERT INTO job_presentation(job_id,deleted) VALUES(?,1)", (job_id,))
    assert [job["id"] for job in store.summaries()] == [old]
