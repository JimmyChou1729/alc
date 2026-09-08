from __future__ import annotations

from pathlib import Path

import json
from dataclasses import replace
from threading import Event, Lock

import pytest
from ac_document import AcDocumentService, RichDocumentParserService
from ac_jobs import (
    RunContext,
    RunRepository,
    RunSpec,
    RunError,
    StoppedError,
    RunEngine,
    Failed,
    Succeeded,
    RunStatus,
    Paused,
    ResumeReason,
)
from ac_llm import LLMCompleted, LLMFailed, LLMPaused, ProviderFailure, FailureCategory
from alc_translate import (
    TranslationSource,
    TranslationWorkflowService,
    LanguageResult,
    GlossaryResult,
    TranslationResult,
)
from alc_translate.contracts import ExecutionOptions
from alc_translate.prompts import glossary_prompt
from alc_translate.source import block_text
from alc_translate.workflow import _glossary_windows, TranslationWorkflowError


class OrderedTasks:
    def __init__(self, *, block_first=False, failure=None):
        self.block_first = block_first
        self.failure = failure
        self.second_reviewed = Event()
        self.lock = Lock()
        self.calls = []
        self.active = self.peak = 0

    def execute_or_resume(self, context, request, *, input=None, options=None):
        payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
        ordinal = payload["window_ordinal"]
        review = "translations" in payload
        with self.lock:
            self.calls.append((ordinal, review))
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.block_first and ordinal == 0 and not review:
                assert self.second_reviewed.wait(
                    5
                ), "second window never ran concurrently"
                if self.failure == "provider":
                    return LLMFailed(
                        ProviderFailure(
                            "test failure", category=FailureCategory.AUTHENTICATION
                        )
                    )
                if self.failure == "stop":
                    raise StoppedError("test interruption")
                if self.failure == "pause":
                    return LLMPaused(ResumeReason.EXTERNAL_CONDITION, "window-0")
            if review:
                value = {
                    "schema_version": "alc.translate.text_slot_review_result.v1",
                    "translation_patches": {},
                    "summary": "reviewed",
                }
                if ordinal == 1:
                    self.second_reviewed.set()
            else:
                value = {
                    "schema_version": "alc.translate.text_slot_result.v1",
                    "translations": {
                        b["block_id"]: {
                            "text_slots": {
                                part["slot_id"]: "translated: " + part["text"]
                                for parent in b["content"]["parts"]
                                for part in (
                                    parent["parts"]
                                    if parent["kind"] == "link"
                                    else [parent]
                                )
                                if part["kind"] == "text_slot"
                            }
                        }
                        for b in payload["blocks"]
                    },
                }
            return LLMCompleted(value, "fake", "fake", None, None)
        finally:
            with self.lock:
                self.active -= 1


def source_and_options(tmp_path):
    path = tmp_path / "source.md"
    path.write_text(
        "# Long\n\n"
        + "\n\n".join(f"Part {i}. " + "source prose " * 40 for i in range(8))
    )
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(path)
        )
    )
    return source, dict(
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest, source.source_digest, "zh-CN", 1, "e" * 64, ()
        ),
        target_language="zh-CN",
        input_budget_bytes=4800,
    )


def context_for(tmp_path, name):
    repo = RunRepository(tmp_path / "jobs")
    snap = repo.create(RunSpec(name, "test.windows", {}))
    return RunContext(repo, snap, resume_input=None)


def test_parallel_windows_preserve_serial_result_and_bound_concurrency(tmp_path):
    source, kwargs = source_and_options(tmp_path)
    serial_tasks = OrderedTasks()
    serial = TranslationWorkflowService(serial_tasks).translate_blocks(
        context_for(tmp_path, "serial"), source, **kwargs
    )
    tasks = OrderedTasks(block_first=True)
    context = context_for(tmp_path, "parallel")
    result = TranslationWorkflowService(tasks).translate_blocks(
        context, source, window_workers=2, **kwargs
    )
    assert isinstance(result, TranslationResult)
    assert isinstance(serial, TranslationResult)
    assert result.layer == serial.layer
    assert sorted(tasks.calls) == sorted(serial_tasks.calls)
    assert tasks.peak == 2
    assert tasks.calls.index((1, True)) < tasks.calls.index((0, True))
    events = [
        json.loads(line)
        for line in (context.run_directory / "events.jsonl").read_text().splitlines()
    ]
    progress = [
        e["data"]["completed_units"]
        for e in events
        if e["event"] == "translation_progress"
    ]
    assert progress == sorted(progress)
    assert len(progress) > 2


@pytest.mark.parametrize("failure", ["provider", "stop"])
@pytest.mark.parametrize("resume_workers", [1, 2])
def test_sparse_completed_windows_survive_failure_and_resume(
    tmp_path, failure, resume_workers
):
    source, kwargs = source_and_options(tmp_path)
    context = context_for(tmp_path, "recover")
    tasks = OrderedTasks(block_first=True, failure=failure)
    workflow = TranslationWorkflowService(tasks)
    if failure == "stop":
        with pytest.raises(StoppedError):
            workflow.translate_blocks(context, source, window_workers=2, **kwargs)
    else:
        result = workflow.translate_blocks(context, source, window_workers=2, **kwargs)
        assert isinstance(result, RunError)
    assert context.artifacts.find("translation/windows/0001/accepted") is not None
    assert context.artifacts.find("translation/windows/0000/accepted") is None
    snapshot = replace(
        context.repository.inspect(context.run_id).snapshot, recovery_epoch=1
    )
    resumed = RunContext(context.repository, snapshot, resume_input=None)
    healthy = OrderedTasks()
    result = TranslationWorkflowService(healthy).translate_blocks(
        resumed, source, window_workers=resume_workers, **kwargs
    )
    assert isinstance(result, TranslationResult)
    assert (0, False) in healthy.calls
    assert not any(ordinal == 1 for ordinal, review in healthy.calls)


def test_glossary_plans_complete_prompt_and_rejects_unfit_requirement():
    terms = [
        {"term_id": str(i), "term": "Example", "matched_sentences": ["x" * 1200]}
        for i in range(2)
    ]
    intent = "保持术语一致。" * 60
    windows = _glossary_windows(
        terms, target_language="zh-CN", budget_bytes=5000, user_intent=intent
    )
    assert len(windows) == 2
    assert [t for w in windows for t in w] == terms
    assert all(
        len(
            glossary_prompt(
                terms=w, target_language="zh-CN", window_ordinal=i, user_intent=intent
            ).encode()
        )
        <= 5000
        for i, w in enumerate(windows)
    )
    with pytest.raises(TranslationWorkflowError, match="exceeds"):
        _glossary_windows(
            terms,
            target_language="zh-CN",
            budget_bytes=5000,
            user_intent="保持术语一致。" * 300,
        )


@pytest.mark.parametrize("failure", ["provider", "pause"])
def test_failed_parallel_group_resumes_through_run_engine(tmp_path, failure):
    source, kwargs = source_and_options(tmp_path)
    tasks = OrderedTasks(block_first=True, failure=failure)

    class Handler:
        name = "test.parallel_translation"

        def execute(self, context):
            outcome = TranslationWorkflowService(tasks).translate_blocks(
                context, source, window_workers=2, **kwargs
            )
            if isinstance(outcome, RunError):
                return Failed(outcome)
            if isinstance(outcome, Paused):
                return outcome
            assert isinstance(outcome, TranslationResult)
            return Succeeded(
                context.artifacts.publish_json("test/result", outcome.to_document())
            )

    repo = RunRepository(tmp_path / "engine-jobs")
    engine = RunEngine(repo)
    first = engine.execute(RunSpec("engine-resume", Handler.name, {}), Handler())
    assert first.status is (
        RunStatus.FAILED if failure == "provider" else RunStatus.PAUSED
    )
    tasks = OrderedTasks()
    recovered = engine.resume(first.run_id, Handler())
    assert recovered.status is RunStatus.SUCCEEDED
    if failure == "provider":
        assert recovered.recovery_epoch > first.recovery_epoch
    assert (0, False) in tasks.calls
    assert not any(ordinal == 1 for ordinal, review in tasks.calls)


@pytest.mark.parametrize("workers", [0, 33, True, 1.5])
def test_invalid_window_limits_rejected(workers):
    with pytest.raises(ValueError, match="window_workers"):
        ExecutionOptions(window_workers=workers)


@pytest.mark.parametrize("workers", [1, 2])
def test_one_failed_window_does_not_abandon_later_windows(
    tmp_path, workers, monkeypatch
):
    source, kwargs = source_and_options(tmp_path)
    healthy = OrderedTasks()
    TranslationWorkflowService(healthy).translate_blocks(
        context_for(tmp_path, "healthy"), source, window_workers=workers, **kwargs
    )
    expected = {ordinal for ordinal, review in healthy.calls if not review}
    assert len(expected) > 2

    class FailFirst(OrderedTasks):
        def execute_or_resume(self, context, request, **options):
            payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
            if payload["window_ordinal"] == 0:
                self.calls.append((0, False))
                return LLMFailed(
                    ProviderFailure(
                        "isolated failure", category=FailureCategory.AUTHENTICATION
                    )
                )
            return super().execute_or_resume(context, request, **options)

    tasks = FailFirst()
    result = TranslationWorkflowService(tasks).translate_blocks(
        context_for(tmp_path, "collect"), source, window_workers=workers, **kwargs
    )
    assert not isinstance(result, TranslationResult)
    assert {ordinal for ordinal, review in tasks.calls if not review} == expected
    assert {ordinal for ordinal, review in tasks.calls if review} == expected - {0}

    from alc_translate.service import TranslationService
    from alc_translate.project import TranslationProject
    from alc_translate.partial import render_partial_translation

    service = TranslationService(tmp_path / "jobs")
    monkeypatch.setattr(service, "request_source", lambda run_id: source)
    project = TranslationProject.open(tmp_path / "partial-project")
    project.select("blocks", "collect")
    html = render_partial_translation(
        project, service, service.repository.inspect("collect").snapshot
    )
    assert html is not None
    assert "translated:" in Path(html).read_text()
    assert "部分结果" in Path(html).read_text()
    state = json.loads((Path(html).parent / "state.json").read_text())
    assert 0 < state["completed_chapters"] < state["total_chapters"]


@pytest.mark.parametrize("kind", ["source_text", "review_skipped"])
def test_partial_translation_preserves_saved_quality_provenance(tmp_path, kind):
    from alc_render import decode_fragment_revision

    source, kwargs = source_and_options(tmp_path)

    class MixedFailure(OrderedTasks):
        def execute_or_resume(self, context, request, **options):
            payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
            ordinal = payload["window_ordinal"]
            if ordinal == 0:
                return LLMFailed(
                    ProviderFailure(
                        "fixture failure", category=FailureCategory.AUTHENTICATION
                    )
                )
            if ordinal == 1 and kind == "review_skipped" and "translations" in payload:
                return LLMCompleted(
                    {
                        "translation_patches": [
                            {
                                "block_id": "unknown-block",
                                "replacement": "invalid patch",
                            }
                        ],
                        "summary": "fixture invalid review",
                    },
                    "fake",
                    "fake",
                    None,
                    None,
                )
            if ordinal == 1 and kind == "source_text":
                return LLMCompleted({"translations": []}, "fake", "fake", None, None)
            return super().execute_or_resume(context, request, **options)

    context = context_for(tmp_path, "partial-quality")
    result = TranslationWorkflowService(MixedFailure()).translate_blocks(
        context, source, window_workers=1, **kwargs
    )
    assert isinstance(result, RunError)
    saved = context.working.read_candidate_json("translation/partial-result.json")
    partial = TranslationResult.from_document(saved["result"])
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode(),
            filename=Path(item.revision.path).name,
        )
        for item in partial.revision_artifacts
    ]
    assert any(
        r.provenance.get("translation_fallback", {}).get("kind") == kind
        for r in revisions
    )
