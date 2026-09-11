"""Preserve rejected guide text without asserting invalid links or locations."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .generation_validation import (
    CompanionContentError, _generated_unit, _minimal_references,
    _published_reference_ids, _dois, _arxiv_ids,
)
from .rich_text import RichTextError, canonicalize_display_math, validate_rich_markdown


def literal_markdown(text: str) -> str:
    # A fence longer than any candidate fence cannot be closed by its contents.
    fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
    return f"{fence}text\n{text}\n{fence}"


def recover_chapter_guide(candidate: Any, *, chapter_id: str,
                          block_ids, chapter_anchor_block_id: str,
                          section_block_ids=()) -> dict[str, Any]:
    if chapter_anchor_block_id not in block_ids:
        raise CompanionContentError("source_anchor_invalid", "Recovery requires a valid source chapter anchor")
    raw = dict(candidate) if isinstance(candidate, Mapping) else {}
    references = []
    positions = {}
    raw_references = raw.get("references", [])
    rejected_references = [] if isinstance(raw_references, list) else [raw_references]
    for index, item in enumerate(raw.get("references", []) if isinstance(raw.get("references"), list) else [], 1):
        try:
            valid = _minimal_references([item])
        except CompanionContentError:
            rejected_references.append(item)
            continue
        identities, _, unique = _published_reference_ids(valid)
        positions[str(index)] = identities[0]
        references.append({"reference_id": identities[0], "title": unique[0]["title"],
                           "source": unique[0]["source"], "dois": _dois(unique[0]["source"]),
                           "arxiv_ids": _arxiv_ids(unique[0]["source"]),
                           "cached_document": None, "cached_material": None})
    allowed = {r["reference_id"] for r in references}
    units = []
    candidates = [("chapter", raw.get("chapter_guide"))]
    for key, kind in (("section_guides", "section"), ("companions", "companion")):
        values = raw.get(key, [])
        candidates.extend((kind, item) for item in (values if isinstance(values, list) else [values]))
    for kind, item in candidates:
        if item is None:
            continue
        text = item.get("content_markdown") if isinstance(item, Mapping) else item
        if not isinstance(text, str) or not text.strip():
            text = json.dumps(item, ensure_ascii=False)
        title = item.get("title") if isinstance(item, Mapping) else None
        title = title.strip() if isinstance(title, str) and title.strip() else "保留的伴读内容 / Retained guide"
        title = re.sub(r"[\r\n]+", " ", title)
        anchor, placement = chapter_anchor_block_id, "chapter"
        location = item.get("section_number" if kind == "section" else "after_part") if isinstance(item, Mapping) else None
        anchors = section_block_ids if kind == "section" else block_ids
        if kind != "chapter" and isinstance(location, int) and not isinstance(location, bool) and 1 <= location <= len(anchors):
            anchor, placement = anchors[location - 1], "inline"
        warning = "待核对：此内容未通过自动验收，已保留供编辑。 / Retained for review and editing."
        if kind != "chapter" and placement == "chapter":
            warning += " 原文位置未确认 / Source location unconfirmed."
        def citation(match):
            key = match[1]
            identity = positions.get(key, key)
            return f"[@{identity}]" if identity in allowed else "\\" + match[0]
        normalized = re.sub(r"\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]", citation, text)
        try:
            normalized = canonicalize_display_math(normalized)
            cites = validate_rich_markdown(normalized, allowed_evidence_ids=tuple(allowed))
        except RichTextError:
            normalized, cites = literal_markdown(text), ()
        units.append(_generated_unit(chapter_id, kind=kind, index=len(units) + 1,
                     title=title, anchor=anchor, placement=placement,
                     markdown=warning + "\n\n" + normalized, citations=list(dict.fromkeys(cites))))
    if not units and candidate:
        units.append(_generated_unit(chapter_id, kind="chapter", index=1,
                     title="保留的伴读内容 / Retained guide", anchor=chapter_anchor_block_id,
                     placement="chapter", markdown=literal_markdown(json.dumps(candidate, ensure_ascii=False)), citations=[]))
    cited = {c for unit in units for c in unit["citations"]}
    unused = [r for r in references if r["reference_id"] not in cited]
    retained = rejected_references + [{"title": r["title"], "source": r["source"]} for r in unused]
    if retained:
        units.append(_generated_unit(chapter_id, kind="chapter", index=len(units) + 1,
                     title="待核对参考来源 / References to review", anchor=chapter_anchor_block_id,
                     placement="chapter", markdown=literal_markdown(json.dumps(retained, ensure_ascii=False, indent=2)), citations=[]))
    return {"chapter_id": chapter_id, "learning_units": units,
            "references": list({r["reference_id"]: r for r in references if r["reference_id"] in cited}.values())}
