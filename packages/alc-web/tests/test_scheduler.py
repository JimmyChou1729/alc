import sqlite3
import threading

import pytest

from alc_web.scheduler import Scheduler
from alc_web.store import Store


@pytest.mark.parametrize("report_fails", [False, True])
def test_scheduler_admits_job_after_database_recovers(tmp_path, monkeypatch, report_fails):
    store = Store(tmp_path)
    job_id = store.create({})["id"]
    scheduler = Scheduler(store, None)
    entered = threading.Event()
    recovered = threading.Event()
    launched = threading.Event()
    original_setting = store.setting
    attempts = []
    admissions = []

    def setting(*args, **kwargs):
        attempts.append(True)
        if not recovered.is_set():
            entered.set()
            raise sqlite3.OperationalError("disk I/O error")
        return original_setting(*args, **kwargs)

    def save_setting(*args, **kwargs):
        if report_fails:
            raise sqlite3.OperationalError("disk I/O error")

    def launch(job):
        admissions.append(job["id"])
        launched.set()

    monkeypatch.setattr(store, "setting", setting)
    monkeypatch.setattr(store, "save_setting", save_setting)
    monkeypatch.setattr(scheduler, "launch", launch)
    scheduler.start()
    try:
        assert entered.wait(2)
        assert scheduler.thread.is_alive()
        assert store.get(job_id)["state"] == "queued"
        recovered.set()
        assert launched.wait(3)
        assert scheduler.thread.is_alive()
        assert len(attempts) >= 2
        assert admissions == [job_id]
        assert store.get(job_id)["state"] == "running"
    finally:
        scheduler.close()
    assert not scheduler.thread.is_alive()


def test_scheduler_stops_during_persistent_database_failure(tmp_path, monkeypatch):
    scheduler = Scheduler(Store(tmp_path), None)
    reported = threading.Event()

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    def fail_report(*args, **kwargs):
        reported.set()
        fail()

    monkeypatch.setattr(scheduler.store, "setting", fail)
    monkeypatch.setattr(scheduler.store, "save_setting", fail_report)
    scheduler.start()
    try:
        assert reported.wait(2)
        assert scheduler.thread.is_alive()
    finally:
        scheduler.close()
    assert not scheduler.thread.is_alive()
