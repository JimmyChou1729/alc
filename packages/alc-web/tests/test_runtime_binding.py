from alc_web.store import Store


def test_only_pristine_job_can_bind_current_runtime(tmp_path):
    store = Store(tmp_path)
    job = store.create({"runtime": {"old": True}})
    assert store.bind_unstarted_runtime(job["id"], {"new": True})
    assert store.get(job["id"])["spec"]["runtime"] == {"new": True}
    root = store.job_directory(job["id"])
    (root / "project").mkdir(parents=True)
    assert not store.bind_unstarted_runtime(job["id"], {"unsafe": True})
    assert store.get(job["id"])["spec"]["runtime"] == {"new": True}


def test_phase_or_saved_detail_prevents_runtime_rebinding(tmp_path):
    store = Store(tmp_path)
    job = store.create({"runtime": {"old": True}})
    store.update(job["id"], phase="translation")
    assert not store.bind_unstarted_runtime(job["id"], {})
    store.update(job["id"], phase="queued", detail={"source": "saved"})
    assert not store.bind_unstarted_runtime(job["id"], {})
