from __future__ import annotations

import json
from pathlib import Path

import pytest
from ac_document import AcDocumentService, RichDocumentParserService
from ac_jobs import RunContext, RunRepository, RunSpec
from ac_llm import LLMCompleted
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


class AtomRepairTasks:
    def __init__(self, source, *, exhausted):
        self.blocks = {block["block_id"]: block for block in source_blocks(source)}
        self.exhausted = exhausted
        self.requests = []

    def execute_or_resume(self, context, request, *, input=None, options=None):
        self.requests.append(request)
        payload = json.loads(request.prompt.split("Input JSON:\n", 1)[1])
        blocks = payload["blocks"]
        if len(self.requests) == 2:
            assert "alc.translate.paragraph_repair.v1" in request.prompt
            # Match the observed defect: formula positions become empty text,
            # leaving too many text pieces for unambiguous local restoration.
            value = {
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                "translations": [
                    {
                        "block_id": b["block_id"],
                        "parts": [
                            {
                                "kind": "text",
                                "text": "" if p["kind"] == "atom" else "局部译文",
                            }
                            for p in b["parts"]
                        ],
                    }
                    for b in blocks
                ],
            }
        else:
            value = {"schema_version": TEXT_SLOT_RESULT_SCHEMA, "translations": {}}
            for block in blocks:
                source = self.blocks[block["block_id"]]
                slots = {slot: "完整译文" for slot in text_slot_ids(source)}
                if "$x$" in block_text(source) and (
                    len(self.requests) == 1 or self.exhausted
                ):
                    slots[next(reversed(slots))] = ""
                if "$x$" not in block_text(source):
                    slots = {slot: "保留健康邻段" for slot in slots}
                value["translations"][block["block_id"]] = {"text_slots": slots}
        return LLMCompleted(value, "fake", "fake", None, None)


@pytest.mark.parametrize("exhausted", [False, True])
def test_atom_repair_is_bounded_and_always_delivers_neighbors(tmp_path, exhausted):
    markdown = tmp_path / "atoms.md"
    markdown.write_text("Before $x$ between $y$ after.\n\nA healthy neighbor.\n")
    paper = AcDocumentService(cache_root=tmp_path / "cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    repository = RunRepository(tmp_path / "jobs")
    context = RunContext(
        repository,
        repository.create(RunSpec("repair", "test.parent", {})),
        resume_input=None,
    )
    tasks = AtomRepairTasks(source, exhausted=exhausted)
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
    assert isinstance(result, TranslationResult)
    assert len(tasks.requests) == 3
    assert "original source text slots" in tasks.requests[2].prompt
    assert "A healthy neighbor" not in tasks.requests[2].prompt
    assert len({r.task_id for r in tasks.requests}) == 3
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode(),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    formula_id = next(
        b["block_id"] for b in source_blocks(source) if "$x$" in block_text(b)
    )
    formula = next(r for r in revisions if r.anchor.target_id == formula_id)
    assert "$x$" in formula.markdown_body and "$y$" in formula.markdown_body
    assert ("translation_fallback" in formula.provenance) is exhausted
    neighbor = next(r for r in revisions if r.anchor.target_id != formula_id)
    assert neighbor.markdown_body.strip() == "保留健康邻段"
    assert "translation_fallback" not in neighbor.provenance
    if exhausted:
        assert formula.markdown_body.strip() == "Before $x$ between $y$ after."
    else:
        assert "完整译文" in formula.markdown_body
