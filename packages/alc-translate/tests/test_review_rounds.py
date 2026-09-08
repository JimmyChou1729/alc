"""Explicit content review policy and durable round checkpoints."""

import json

import pytest
from ac_jobs import Paused, ResumeReason
from ac_llm import LLMCompleted, LLMPaused
from alc_translate import TranslationResult, TranslationWorkflowService
from alc_translate.contracts import (
    GenerationRecipe,
    recipe_from_document,
    recipe_to_document,
)
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_helpers_spec = spec_from_file_location(
    "translation_window_helpers", Path(__file__).with_name("test_window_execution.py")
)
_helpers = module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)
OrderedTasks = _helpers.OrderedTasks
context_for = _helpers.context_for
source_and_options = _helpers.source_and_options


class ReviewTasks(OrderedTasks):
    def __init__(self, *, change=False, pause_second=False):
        super().__init__()
        self.change = change
        self.pause_second = pause_second
        self.reviews = []

    def execute_or_resume(self, context, request, **kwargs):
        payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
        if "translations" not in payload:
            return super().execute_or_resume(context, request, **kwargs)
        self.reviews.append(request.task_id)
        if self.pause_second and len(self.reviews) == 2:
            return LLMPaused(ResumeReason.EXTERNAL_CONDITION, "round-two")
        patches = {}
        if self.change and len(self.reviews) == 1:
            item = payload["translations"][0]
            slots = dict(item["content"]["text_slots"])
            first_slot = next(iter(slots))
            slots[first_slot] += " revised"
            patches = {item["block_id"]: {"text_slots": slots}}
        return LLMCompleted(
            {
                "schema_version": "alc.translate.text_slot_review_result.v1",
                "translation_patches": patches,
                "summary": "checked",
            },
            "fake",
            "fake",
            None,
            None,
        )


@pytest.mark.parametrize(
    "rounds,change,expected",
    [(None, True, 1), (0, True, 0), (1, True, 1), (2, False, 1), (2, True, 2)],
)
def test_review_round_limit_and_early_exit(tmp_path, rounds, change, expected):
    source, options = source_and_options(tmp_path)
    options["input_budget_bytes"] = 32000
    tasks = ReviewTasks(change=change)
    context = context_for(tmp_path, "rounds")
    workflow = TranslationWorkflowService(tasks)
    result = workflow.translate_blocks(context, source, review_rounds=rounds, **options)
    assert isinstance(result, TranslationResult)
    assert len(tasks.reviews) == expected
    assert len(set(tasks.reviews)) == expected
    again = workflow.translate_blocks(context, source, review_rounds=rounds, **options)
    assert again == result
    assert len(tasks.reviews) == expected
    assert context.artifacts.find("translation/windows/0000/fallback") is None


def test_resume_second_round_keeps_first_round_checkpoint(tmp_path):
    source, options = source_and_options(tmp_path)
    options["input_budget_bytes"] = 32000
    tasks = ReviewTasks(change=True, pause_second=True)
    context = context_for(tmp_path, "resume-rounds")
    workflow = TranslationWorkflowService(tasks)
    result = workflow.translate_blocks(context, source, review_rounds=2, **options)
    assert isinstance(result, Paused)
    assert len(tasks.reviews) == 2
    resumed = workflow.translate_blocks(context, source, review_rounds=2, **options)
    assert isinstance(resumed, TranslationResult)
    assert tasks.reviews[0] != tasks.reviews[1]
    assert tasks.reviews[1] == tasks.reviews[2]
    assert len(tasks.calls) == 1  # Translation generation is also checkpointed.


@pytest.mark.parametrize("rounds", [0, 1, 2])
def test_recipe_freezes_review_policy_and_preserves_legacy(rounds):
    legacy = recipe_to_document(GenerationRecipe())
    assert legacy["schema_version"] == "alc.translate.generation_recipe.v1"
    assert "review_rounds" not in legacy
    assert recipe_to_document(recipe_from_document(legacy)) == legacy
    recipe = GenerationRecipe(review_rounds=rounds)
    document = recipe_to_document(recipe)
    assert document["schema_version"] == "alc.translate.generation_recipe.v4"
    assert recipe_from_document(document) == recipe
    assert recipe_to_document(recipe_from_document(document)) == document


@pytest.mark.parametrize("value", [True, -1, 3, "1", 1.0])
def test_invalid_review_policy_rejected(value):
    with pytest.raises(ValueError, match="review_rounds"):
        GenerationRecipe(review_rounds=value)


def test_split_review_resume_preserves_invalid_subwindow_diagnostic(
    tmp_path, monkeypatch
):
    from alc_translate import workflow as workflow_module

    def split_review(blocks, translations, **kwargs):
        return (
            (tuple(blocks[:-1]), tuple(translations[:-1])),
            (tuple(blocks[-1:]), tuple(translations[-1:])),
        )

    monkeypatch.setattr(workflow_module, "_translation_review_windows", split_review)
    source, options = source_and_options(tmp_path)
    options["input_budget_bytes"] = 32000

    class InterruptedReview(ReviewTasks):
        def __init__(self):
            super().__init__()
            self.invalid_calls = 0
            self.did_pause = False

        def execute_or_resume(self, context, request, **kwargs):
            payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
            if "translations" not in payload:
                return super().execute_or_resume(context, request, **kwargs)
            if len(payload["blocks"]) > 1:
                self.invalid_calls += 1
                return LLMCompleted(
                    {
                        "schema_version": "alc.translate.text_slot_review_result.v1",
                        "translation_patches": {
                            "not-a-source-block": {"text_slots": {}}
                        },
                        "summary": "invalid review",
                    },
                    "fake",
                    "fake",
                    None,
                    None,
                )
            if not self.did_pause:
                self.did_pause = True
                return LLMPaused(ResumeReason.EXTERNAL_CONDITION, "next-subwindow")
            return LLMCompleted(
                {
                    "schema_version": "alc.translate.text_slot_review_result.v1",
                    "translation_patches": {},
                    "summary": "checked",
                },
                "fake",
                "fake",
                None,
                None,
            )

    tasks = InterruptedReview()
    context = context_for(tmp_path, "split-review-resume")
    workflow = TranslationWorkflowService(tasks)
    first = workflow.translate_blocks(context, source, review_rounds=2, **options)
    assert isinstance(first, Paused)
    invalid_calls = tasks.invalid_calls
    result = workflow.translate_blocks(context, source, review_rounds=2, **options)
    assert isinstance(result, TranslationResult)
    assert tasks.invalid_calls == invalid_calls
    ref = context.artifacts.find("translation/windows/0000/fallback")
    assert ref is not None
    diagnostic = workflow_module._read_json_artifact(context, ref, "test fallback")
    assert diagnostic["review_skipped_block_ids"]
    assert diagnostic["reason_codes"] == ["translation_review_invalid"]
