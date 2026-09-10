"""Guide-only partitions preserve published chapter and translation identities."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, Mapping

from .source_planning import SourceChapter


def split_guide_chapter(chapter: SourceChapter) -> tuple[SourceChapter, ...]:
    count = len(chapter.block_ids)
    if count < 2:
        return ()
    middle = count // 2
    boundaries = [chapter.block_ids.index(b) for b in chapter.section_block_ids]
    balanced = [i for i in boundaries if count / 4 <= i <= 3 * count / 4]
    cut = min(balanced, key=lambda i: abs(i - middle)) if balanced else middle
    result = []
    for ids in (chapter.block_ids[:cut], chapter.block_ids[cut:]):
        sections = [(b, t, level) for b, t, level in zip(
            chapter.section_block_ids, chapter.section_titles, chapter.section_levels
        ) if b in ids]
        digest = hashlib.sha256("\0".join(ids).encode()).hexdigest()[:24]
        result.append(replace(
            chapter, chapter_id=f"guide-batch-{digest}", block_ids=ids,
            display_anchor_block_id=ids[0],
            section_block_ids=tuple(s[0] for s in sections),
            section_titles=tuple(s[1] for s in sections),
            section_levels=tuple(s[2] for s in sections),
        ))
    return tuple(result)


def batch_translation_index(index: Mapping[str, Any] | None,
                            chapter: SourceChapter) -> Mapping[str, Any] | None:
    if index is None:
        return None
    by_id = {p["block_id"]: p for c in index["chapters"] for p in c["parts"]}
    return {**index, "chapters": [{"chapter_id": chapter.chapter_id,
        "parts": [by_id[b] for b in chapter.block_ids]}]}


def merge_guide_batches(chapter: SourceChapter, guides: list[Mapping[str, Any]]) -> dict[str, Any]:
    units = []
    references = {}
    issues = []
    for guide in guides:
        for unit in guide["learning_units"]:
            unit = dict(unit)
            # A batch overview describes its local range, not the whole chapter.
            if unit.get("placement") == "chapter":
                unit["placement"] = "inline"
            units.append(unit)
        for reference in guide["references"]:
            key = reference["reference_id"]
            if key in references and references[key] != reference:
                raise ValueError("Conflicting guide batch reference identity")
            references[key] = reference
        if guide.get("delivery_issue"):
            issues.append(guide["delivery_issue"])
    result = {"chapter_id": chapter.chapter_id, "learning_units": units,
              "references": list(references.values())}
    if issues:
        result["delivery_issue"] = {**issues[0], "batch_issues": issues}
    return result
