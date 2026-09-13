import json

import pytest
from ac_jobs import RunContext, RunRepository, RunSpec
from ac_llm import LLMCompleted, LLMRequest, JsonOutput, LLMExecutionOptions
from alc_translate.atoms import protected_atom_plan
import alc_translate.workflow as workflow


def block(count=8):
    spans = []
    for index in range(count):
        spans.append({"kind": "text", "text": f"Source clause number {index} has meaning. "})
        if index + 1 < count:
            spans.append({"kind": "math", "tex": f"x_{index}", "text": f"x_{index}"})
    return {"block_id": "b", "kind": "paragraph", "payload": {
        "text": "".join(s["text"] for s in spans), "inline_spans": spans}}


@pytest.mark.parametrize("bad_group", [False, True])
def test_failed_paragraph_groups_preserve_atoms_and_failed_source_slots(tmp_path, monkeypatch, bad_group):
    source = block()
    repo = RunRepository(tmp_path / "jobs")
    ctx = RunContext(repo, repo.create(RunSpec("group", "test", {})), resume_input=None)
    calls = []
    def execute(service, context, request, **kwargs):
        payload = json.loads(request.prompt.split("Input JSON:\n")[1])
        calls.append(payload)
        slots = {key: "译文 " + value for key, value in payload["text_slots"].items()}
        if bad_group and len(calls) == 2:
            slots = {key: "" for key in slots}
        return LLMCompleted({"text_slots": slots}, "fake", "fake", None, None)
    monkeypatch.setattr(workflow, "_execute", execute)
    failed = workflow._InvalidGeneratedOutput(workflow.TranslationWorkflowError("translation_coverage_invalid", "shifted retry"), tmp_path / "candidate", {
        "schema_version": workflow.PROTECTED_ATOM_RESULT_SCHEMA,
        "translations": [{"block_id": "b", "parts": [{"kind": "text", "text": "Wrong merged whole paragraph"}]}]})
    args = dict(window=[source], options=LLMExecutionOptions(), resume_input=None, target_language="zh-CN",
                user_intent="Use formal scientific prose", glossary=[{"term_id":"term1", "term":"Source clause", "aliases":[], "preferred_translation":"源分句", "target_definition":"definition"}])
    request = LLMRequest("repair", "prompt", JsonOutput({"type": "object"}))
    result = workflow._repair_failed_text_slot_groups(None, ctx, request, failed, **args)
    accepted = workflow._validate_protected_atom_window(result.candidate, [source])[0]
    assert len(calls) == 3
    assert all(p["user_intent"] == args["user_intent"] for p in calls)
    assert all(p["glossary"][0]["preferred_translation"] == "源分句" for p in calls)
    assert all(len(p["text_slots"]) <= 3 for p in calls)
    assert "Wrong merged" not in accepted["text"]
    assert all(f"x_{i}" in accepted["text"] for i in range(7))
    ref = ctx.artifacts.find("diagnostics/text-slot-recovery/b")
    diagnostic = json.loads(ctx.artifacts.read_bytes(ref))
    assert len(diagnostic["partial_source_text_slot_ids"]) == (3 if bad_group else 0)
    replay = workflow._repair_failed_text_slot_groups(None, ctx, request, failed, **args)
    assert replay.candidate == result.candidate and len(calls) == 3


def test_slot_groups_cover_whole_block_with_bounded_requests(tmp_path, monkeypatch):
    source = block(30)
    repo = RunRepository(tmp_path / "jobs")
    ctx = RunContext(repo, repo.create(RunSpec("limit", "test", {})), resume_input=None)
    calls = []
    def execute(service, context, request, **kwargs):
        payload = json.loads(request.prompt.split("Input JSON:\n")[1]); calls.append(1)
        return LLMCompleted({"text_slots": payload["text_slots"]}, "fake", "fake", None, None)
    monkeypatch.setattr(workflow, "_execute", execute)
    failed = workflow._InvalidGeneratedOutput(workflow.TranslationWorkflowError("translation_atom_missing", "missing"), tmp_path / "candidate", {})
    result = workflow._repair_failed_text_slot_groups(None, ctx, LLMRequest("r", "p", JsonOutput({"type": "object"})), failed,
        window=[source], options=LLMExecutionOptions(), resume_input=None, target_language="zh-CN")
    assert len(calls) == 8
    diagnostic = json.loads(ctx.artifacts.read_bytes(ctx.artifacts.find("diagnostics/text-slot-recovery/b")))
    assert len(diagnostic["partial_source_text_slot_ids"]) == 0
    workflow._validate_protected_atom_window(result.candidate, [source])


def test_last_retry_error_survives_merger_selecting_old_candidate_and_replay(tmp_path, monkeypatch):
    repo = RunRepository(tmp_path / "jobs")
    ctx = RunContext(repo, repo.create(RunSpec("errors", "test", {})), resume_input=None)
    replies = iter([{"attempt": "first"}, {"attempt": "retry"}])
    calls = []
    def execute(*args, **kwargs):
        calls.append(1)
        return LLMCompleted(next(replies), "fake", "fake", None, None)
    def validate(value):
        code = "translation_atom_missing" if value["attempt"] == "first" else "translation_coverage_invalid"
        raise workflow.TranslationWorkflowError(code, value["attempt"], {"block_id": "b"})
    monkeypatch.setattr(workflow, "_execute", execute)
    kwargs = dict(validator=validate, candidate_id="failed", resume_input=None, options=LLMExecutionOptions(),
                  stopped_message="stopped", retry_candidate_merger=lambda first, second: first)
    request = LLMRequest("r", "p", JsonOutput({"type": "object"}))
    result = workflow._validated_generation(None, ctx, request, **kwargs)
    assert result.error.code == "translation_coverage_invalid"
    assert result.error.details["block_id"] == "b"
    assert result.candidate == {"attempt": "first"}
    replay = workflow._validated_generation(None, ctx, request, **kwargs)
    assert replay.error.code == "translation_coverage_invalid"
    assert len(calls) == 2


def test_authentication_failure_interrupts_group_recovery(tmp_path, monkeypatch):
    from ac_jobs import RunError
    from ac_llm import LLMFailed, ProviderFailure, FailureCategory
    repo = RunRepository(tmp_path / "jobs")
    ctx = RunContext(repo, repo.create(RunSpec("auth", "test", {})), resume_input=None)
    calls = []
    def execute(*args, **kwargs):
        calls.append(1)
        return LLMFailed(ProviderFailure("authentication required", category=FailureCategory.AUTHENTICATION))
    monkeypatch.setattr(workflow, "_execute", execute)
    failed = workflow._InvalidGeneratedOutput(workflow.TranslationWorkflowError("translation_coverage_invalid", "bad"), tmp_path / "candidate", {})
    result = workflow._repair_failed_text_slot_groups(None, ctx, LLMRequest("r", "p", JsonOutput({"type": "object"})), failed,
        window=[block()], options=LLMExecutionOptions(), resume_input=None, target_language="zh-CN")
    assert isinstance(result, RunError)
    assert len(calls) == 1
    assert ctx.artifacts.find("diagnostics/text-slot-recovery/b") is None
