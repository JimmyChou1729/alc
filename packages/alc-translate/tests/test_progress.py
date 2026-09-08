from ac_jobs import EventWriter, RunRepository, RunSpec

from alc_translate.service import TranslationService
import pytest


def test_status_exposes_event_progress_before_delivery(tmp_path, capsys):
    import json
    from alc_translate.cli import main
    from alc_translate.project import TranslationProject

    project = TranslationProject.open(tmp_path / "translation")
    repo = RunRepository(project.jobs_root)
    repo.create(RunSpec("blocks-progress", "fixture", {}))
    project.select("blocks", "blocks-progress")
    events = EventWriter(repo.run_directory("blocks-progress") / "events.jsonl",
                         run_id="blocks-progress")
    events.emit("translation_progress", {"completed_units": 3, "total_units": 10})
    assert main(["status", "--project-dir", str(project.root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["data"]["progress"]["completed_units"] == 3
    assert not project.translation_layer.exists()


def test_progress_advances_without_snapshot_or_final_delivery(tmp_path):
    repository = RunRepository(tmp_path / "jobs")
    repository.create(RunSpec("progress-test", "fixture", {}))
    original = repository.inspect("progress-test").snapshot
    events = EventWriter(
        repository.run_directory("progress-test") / "events.jsonl",
        run_id="progress-test",
    )
    events.emit("llm_provider_started", {"call_id": "a", "task_id": "translation-a"})
    events.emit("llm_provider_started", {"call_id": "b", "task_id": "translation-b"})
    events.emit("llm_provider_finished", {"call_id": "b"})
    events.emit("translation_progress", {"completed_units": 4, "total_units": 8})
    events.emit("llm_provider_finished", {"call_id": "a"})
    events.emit("llm_provider_started", {"call_id": "repair", "task_id": "semantic-retry-a"})
    events.emit("llm_pipe_activity", {"call_id": "repair", "stream": "stderr"})
    events.emit("llm_message", {"call_id": "repair", "preview": "private model text"})

    progress = TranslationService(repository).progress("progress-test")
    assert progress["completed_units"] == 4
    assert progress["total_units"] == 8
    assert len(progress["active_calls"]) == 1
    assert progress["active_calls"][0]["phase"] == "repair"
    assert progress["last_activity_at"] == events.read_all()[-1]["emitted_at"]
    assert "private model text" not in str(progress)
    assert repository.inspect("progress-test").snapshot == original

    events.emit("run_attempt_failed", {"attempt": 1, "status": "failed"})
    assert TranslationService(repository).progress("progress-test")["active_calls"] == []


def test_progress_without_events_is_unknown(tmp_path):
    repo = RunRepository(tmp_path / "jobs")
    repo.create(RunSpec("empty", "fixture", {}))
    progress = TranslationService(repo).progress("empty")
    assert progress["completed_units"] is None
    assert progress["last_activity_at"] is None
    assert progress["active_calls"] == []


@pytest.mark.parametrize("terminal", ["llm_usage", "run_paused"])
def test_api_completion_and_pause_clear_active_calls(tmp_path, terminal):
    repo = RunRepository(tmp_path / "jobs")
    repo.create(RunSpec("api-progress", "fixture", {}))
    events = EventWriter(repo.run_directory("api-progress") / "events.jsonl",
                         run_id="api-progress")
    events.emit("llm_provider_started", {"call_id": "api", "task_id": "translation-api"})
    events.emit(terminal, {"call_id": "api"})
    assert TranslationService(repo).progress("api-progress")["active_calls"] == []
