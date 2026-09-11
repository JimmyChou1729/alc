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


def normalize_batch_numbers(value: Mapping[str, Any], chapter: SourceChapter,
                            parent: SourceChapter, *, review: bool = False) -> dict[str, Any]:
    """Map only out-of-range parent numbers with an exact source-block match."""
    import copy
    result = copy.deepcopy(dict(value))
    if chapter.chapter_id == parent.chapter_id:
        return result
    parts = {parent.block_ids.index(block) + 1: index
             for index, block in enumerate(chapter.block_ids, 1)}
    sections = {parent.section_block_ids.index(block) + 1: index
                for index, block in enumerate(chapter.section_block_ids, 1)}

    def local(number, mapping, count):
        if isinstance(number, int) and not isinstance(number, bool) and number > count:
            return mapping.get(number, number)
        return number

    if not review:
        import re
        references = result.get('references', [])
        reference_count = len(references) if isinstance(references, list) else 0
        uses_parent_anchors = any(isinstance(item, dict) and
            isinstance(item.get('after_part'), int) and
            item['after_part'] > len(chapter.block_ids) and item['after_part'] in parts
            for item in result.get('companions', []))
        if uses_parent_anchors or reference_count == 0:
            def source_link(match):
                number = int(match.group(1))
                if reference_count == 0 and 1 <= number <= len(chapter.block_ids):
                    block = chapter.block_ids[number - 1]
                elif number > max(reference_count, len(chapter.block_ids)) and number in parts:
                    block = chapter.block_ids[parts[number] - 1]
                else:
                    return match.group(0)
                token = re.sub(r'[^A-Za-z0-9_.:-]', '-', block)
                return f"[↗](#block-{token})"
            def rewrite(node):
                if isinstance(node, dict):
                    for key, item in node.items():
                        if key.endswith('_markdown') and isinstance(item, str):
                            node[key] = re.sub(r'\[@(\d+)\]', source_link, item)
                        elif key != 'references':
                            rewrite(item)
                elif isinstance(node, list):
                    for item in node:
                        rewrite(item)
            rewrite(result)
    if review:
        payload = result.get('payload')
        if isinstance(payload, dict):
            for key, mapping, count in [('checked_part_numbers', parts, len(chapter.block_ids)),
                                        ('checked_section_numbers', sections, len(chapter.section_block_ids))]:
                if isinstance(payload.get(key), list):
                    payload[key] = [local(n, mapping, count) for n in payload[key]]
    else:
        for key, field, mapping, count in [('companions', 'after_part', parts, len(chapter.block_ids)),
                                           ('section_guides', 'section_number', sections, len(chapter.section_block_ids))]:
            if isinstance(result.get(key), list):
                for item in result[key]:
                    if isinstance(item, dict) and field in item:
                        item[field] = local(item[field], mapping, count)
    return result
