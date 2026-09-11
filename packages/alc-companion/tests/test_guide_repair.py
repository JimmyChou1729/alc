import pytest

from ac_jobs import Paused, ResumeReason, RunContext, RunRepository, RunSpec, StoppedError
from ac_llm import LLMCompleted, LLMExecutionOptions, LLMPaused, LLMStopped

import alc_companion.guide_repair as repair
from alc_companion.generation_validation import CompanionContentError


@pytest.fixture
def context(tmp_path):
    repo = RunRepository(tmp_path / "jobs")
    return RunContext(repo, repo.create(RunSpec("repair", "test", {})), resume_input=None)


def invoke(context, validate=lambda value: value):
    return repair.repair_guide_candidate(
        None,
        context,
        candidate={"companions": [{"content_markdown": "broken"}]},
        chapter_id="chapter-1",
        model=None,
        options=LLMExecutionOptions(),
        error=CompanionContentError("learning_markdown_invalid", "bad math"),
        validate=validate,
    )


@pytest.mark.parametrize("valid", [True, False])
def test_repair_once_and_replay_even_when_validation_fails(context, monkeypatch, valid):
    calls = []
    candidate = {"companions": [{"content_markdown": "broken"}]}

    def execute(*args, **kwargs):
        calls.append(args[2])
        return LLMCompleted(candidate, "fake", "fake", None, None)

    def validate(value):
        assert value == candidate
        if not valid:
            raise CompanionContentError("learning_markdown_invalid", "still bad")

    monkeypatch.setattr(repair, "execute_task", execute)
    assert invoke(context, validate) == (candidate if valid else None)
    assert invoke(context, validate) == (candidate if valid else None)
    assert len(calls) == 1
    assert "bad math" in calls[0].prompt


@pytest.mark.parametrize("raw", [None, [], "not JSON"])
def test_malformed_repair_is_not_retried(context, monkeypatch, raw):
    calls = []

    def execute(*args, **kwargs):
        calls.append(1)
        return LLMCompleted(raw, "fake", "fake", None, None)

    monkeypatch.setattr(repair, "execute_task", execute)
    assert invoke(context) is None
    assert invoke(context) is None
    assert len(calls) == 1


@pytest.mark.parametrize("local", [True, False])
def test_optional_repair_pause_falls_back(context, monkeypatch, local):
    outcome = LLMPaused(
        ResumeReason.SUPERVISION_REQUIRED if local else ResumeReason.EXTERNAL_CONDITION,
        "key",
        {"code": "output_invalid" if local else "authentication", "automatic_retry_exhausted": True},
    )
    monkeypatch.setattr(repair, "execute_task", lambda *args, **kwargs: outcome)
    result = invoke(context)
    assert result is None


def test_stop_is_never_converted_to_fallback(context, monkeypatch):
    monkeypatch.setattr(repair, "execute_task", lambda *args, **kwargs: LLMStopped())
    with pytest.raises(StoppedError):
        invoke(context)


@pytest.mark.parametrize("raw", [
    {"companions": []},
    {"companions": [{"content_markdown": "changed meaning"}]},
    {"companions": [{"content_markdown": "broken"}], "references": [{"source": "invented"}]},
])
def test_valid_but_destructive_repair_is_rejected(context, monkeypatch, raw):
    monkeypatch.setattr(repair, "execute_task", lambda *a, **kw: LLMCompleted(raw, "fake", "fake", None, None))
    assert invoke(context) is None


def test_repair_cannot_invent_a_new_anchor():
    assert not repair._preserves_content(
        {"companions": [{"after_part": 999, "content_markdown": "Keep"}]},
        {"companions": [{"after_part": 1, "content_markdown": "Keep"}]})


def test_repair_cannot_remove_semantic_spaces_or_change_unit_kind():
    assert not repair._preserves_content(
        {"companions": [{"content_markdown": r"$\text{a b}$"}]},
        {"companions": [{"content_markdown": r"$\text{ab}$"}]})
    assert not repair._preserves_content(
        {"companions": [{"content_markdown": "Keep"}]},
        {"section_guides": [{"content_markdown": "Keep"}]})


def test_model_closes_missing_formula_delimiter_and_replays(context, monkeypatch):
    from alc_companion.generation_validation import validate_chapter_guide
    original = {"chapter_guide": None, "section_guides": [], "references": [],
                "companions": [{"after_part": 1, "title": "Formula",
                                "content_markdown": "The equation:\n$$\nx+y"}]}
    fixed = {**original, "companions": [{**original["companions"][0],
                                       "content_markdown": "The equation:\n$$\nx+y\n$$"}]}
    calls = []
    def execute(*args, **kwargs):
        calls.append(1)
        return LLMCompleted(fixed, "fake", "fake", None, None)
    monkeypatch.setattr(repair, "execute_task", execute)
    def validate(value):
        return validate_chapter_guide(value, chapter_id="c", block_ids=("b",),
                                     chapter_anchor_block_id="b")
    with pytest.raises(CompanionContentError):
        validate(original)
    for _ in range(2):
        result = repair.repair_guide_candidate(None, context, candidate=original,
            chapter_id="c", model=None, options=LLMExecutionOptions(),
            error=CompanionContentError("learning_markdown_invalid", "unbalanced"), validate=validate)
        assert result == fixed
    assert calls == [1]


@pytest.mark.parametrize("replacement", ["Equation:\n$$\nx-y\n$$", "Equation:\n$$\nx+y\n$$\nExtra claim", "Equation:\n$$\n\text{ab}\n$$"])
def test_delimiter_repair_does_not_allow_content_rewrites(replacement):
    assert not repair._preserves_content(
        {"content_markdown": "Equation:\n$$\nx+y"},
        {"content_markdown": replacement})
