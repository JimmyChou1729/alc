from __future__ import annotations

import json
from pathlib import Path

import pytest
from ac_document import AcDocumentService, RichDocumentParserService
from ac_jobs import RunContext, RunRepository, RunSpec, RunError
from ac_llm import LLMCompleted, LLMFailed, ProviderFailure, FailureCategory
from alc_render import decode_fragment_revision
from alc_translate import (
    GlossaryResult,
    LanguageResult,
    TranslationResult,
    TranslationSource,
    TranslationWorkflowService,
    source_blocks,
)
from alc_translate.atoms import text_slot_ids
from alc_translate.prompts import PROTECTED_ATOM_RESULT_SCHEMA, TEXT_SLOT_RESULT_SCHEMA
from alc_translate.source import block_text


class SplitTasks:
    def __init__(self, failures):
        self.failures = failures
        self.sizes = []

    def execute_or_resume(self, context, request, **kwargs):
        blocks = json.loads(request.prompt.split("Input JSON:\n", 1)[1])["blocks"]
        self.sizes.append(len(blocks))
        if (
            len(self.sizes) == 1
            or self.failures == "all"
            or (self.failures == "half" and len(self.sizes) == 3)
        ):
            return LLMFailed(
                ProviderFailure("idle timeout", category=FailureCategory.TIMEOUT)
            )
        if self.failures == "auth":
            return LLMFailed(
                ProviderFailure("auth", category=FailureCategory.AUTHENTICATION)
            )
        return LLMCompleted(
            {
                "schema_version": TEXT_SLOT_RESULT_SCHEMA,
                "translations": {
                    b["block_id"]: {
                        "text_slots": {
                            p["slot_id"]: "完整译文"
                            for p in b["content"]["parts"]
                            if p["kind"] == "text_slot"
                        }
                    }
                    for b in blocks
                },
            },
            "fake",
            "fake",
            None,
            None,
        )


@pytest.mark.parametrize(
    "failures,expected", [("none", 0), ("half", 2), ("all", 4), ("auth", None)]
)
def test_provider_window_split_delivers_partial_success(tmp_path, failures, expected):
    markdown = tmp_path / "input.md"
    markdown.write_text(
        "One paragraph.\n\nTwo paragraphs.\n\nThree paragraphs.\n\nFour paragraphs.\n"
    )
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    repo = RunRepository(tmp_path / "jobs")
    context = RunContext(
        repo, repo.create(RunSpec("split", "test", {})), resume_input=None
    )
    tasks = SplitTasks(failures)
    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
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
            source.document_digest, source.source_digest, "zh-CN", 1, "a" * 64, ()
        ),
        target_language="zh-CN",
        review_rounds=0,
    )
    if failures == "auth":
        assert isinstance(result, RunError)
        assert tasks.sizes == [4, 2]
        return
    assert isinstance(result, TranslationResult)
    assert tasks.sizes == [4, 2, 2]
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(i.artifact).decode(),
            filename=Path(i.revision.path).name,
        )
        for i in result.revision_artifacts
    ]
    assert len(revisions) == 4
    assert sum("translation_fallback" in r.provenance for r in revisions) == expected
