"""Preserve rejected guide text without asserting invalid links or locations."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .citation_normalization import citation_spans as _citation_spans, normalize_citation_spacing

from .generation_validation import (
    CompanionContentError, _generated_unit, _minimal_references,
    _published_reference_ids, _dois, _arxiv_ids, _original_reference,
)
from .rich_text import RichTextError, canonicalize_display_math, validate_rich_markdown, strip_ansi_sgr


def literal_markdown(text: str) -> str:
    # Make control bytes visible without deleting evidence from the candidate.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
                  lambda match: f"\\u{ord(match[0]):04x}", text)
    # A fence longer than any candidate fence cannot be closed by its contents.
    fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
    return f"{fence}text\n{text}\n{fence}"


_UNREADABLE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def readable_control_fallback(text: str) -> str:
    """Mark damaged expressions without guessing symbols or hiding intact prose."""
    from .rich_text import _visible_markdown

    visible = _visible_markdown(text)
    math = re.compile(
        r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$"
        r"|(?<![\\$])\$(?!\$)[^\n$]*?(?<!\\)\$"
        r"|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]"
    )
    replacements = [(m.start(), m.end()) for m in math.finditer(visible)
                    if _UNREADABLE_CONTROL.search(text[m.start():m.end()])]
    for start, end in reversed(replacements):
        text = text[:start] + "〔公式含缺失字符 / unreadable math〕" + text[end:]
    return _UNREADABLE_CONTROL.sub("〔字符缺失 / unreadable character〕", text)


def recover_chapter_guide(candidate: Any, *, chapter_id: str,
                          block_ids, chapter_anchor_block_id: str,
                          section_block_ids=(), chapter_title="Original document", source_review_unconfirmed=False) -> dict[str, Any]:
    if chapter_anchor_block_id not in block_ids:
        raise CompanionContentError("source_anchor_invalid", "Recovery requires a valid source chapter anchor")
    raw = dict(candidate) if isinstance(candidate, Mapping) else {}
    references = []
    positions = {}
    raw_references = raw.get("references", [])
    rejected_references = [] if isinstance(raw_references, list) else [raw_references]
    for index, item in enumerate(raw.get("references", []) if isinstance(raw.get("references"), list) else [], 1):
        try:
            valid = [_original_reference(value, block_ids, chapter_anchor_block_id, chapter_title)
                     for value in _minimal_references([item])]
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
        issues = ["review_unconfirmed"] if source_review_unconfirmed else []
        text, _ = strip_ansi_sgr(text)
        text = normalize_citation_spacing(text)
        if kind != "chapter" and placement == "chapter":
            issues.append("source_location_unconfirmed")
        citation_spans = _citation_spans(text)
        def citation(match):
            key = match[1]
            if (match.start(), match.end()) not in citation_spans:
                return match[0]
            identity = positions.get(key, key)
            if identity in allowed:
                return f"[@{identity}]"
            issues.append("reference_unresolved")
            return "\\" + match[0]
        normalized = re.sub(r"\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]", citation, text)
        try:
            normalized = canonicalize_display_math(normalized)
            cites = validate_rich_markdown(normalized, allowed_evidence_ids=tuple(allowed))
        except RichTextError:
            readable = readable_control_fallback(normalized)
            try:
                if readable == normalized:
                    raise RichTextError("No control-character recovery available")
                readable = canonicalize_display_math(readable)
                cites = validate_rich_markdown(readable, allowed_evidence_ids=tuple(allowed))
            except RichTextError:
                normalized, cites = literal_markdown(text), ()
                issues.append("markdown_literal")
            else:
                normalized = readable
                issues.append("unreadable_character")
        units.append(_generated_unit(chapter_id, kind=kind, index=len(units) + 1,
                     title=title, anchor=anchor, placement=placement,
                     markdown=normalized, citations=list(dict.fromkeys(cites))))
        if issues:
            units[-1]["recovery_diagnostic"] = recovery_diagnostic(issues)
    if not units and candidate:
        units.append(_generated_unit(chapter_id, kind="chapter", index=1,
                     title="保留的伴读内容 / Retained guide", anchor=chapter_anchor_block_id,
                     placement="chapter", markdown=literal_markdown(json.dumps(candidate, ensure_ascii=False)), citations=[]))
        units[-1]["recovery_diagnostic"] = recovery_diagnostic(["markdown_literal"])
    cited = {c for unit in units for c in unit["citations"]}
    unused = [r for r in references if r["reference_id"] not in cited]
    retained = rejected_references + [{"title": r["title"], "source": r["source"]} for r in unused]
    if retained:
        units.append(_generated_unit(chapter_id, kind="chapter", index=len(units) + 1,
                     title="待核对参考来源 / References to review", anchor=chapter_anchor_block_id,
                     placement="chapter", markdown=literal_markdown(json.dumps(retained, ensure_ascii=False, indent=2)), citations=[]))
        units[-1]["recovery_diagnostic"] = recovery_diagnostic(["reference_unresolved", "audit_only"])
        units[-1]["audit_scope"] = chapter_id
    return {"chapter_id": chapter_id, "learning_units": units,
            "references": list({r["reference_id"]: r for r in references if r["reference_id"] in cited}.values())}


_RECOVERY_ISSUES = {"audit_only", "markdown_literal", "unreadable_character", "reference_unresolved", "source_location_unconfirmed", "review_unconfirmed"}


def recovery_diagnostic(issues):
    return {"schema_version": "alc.companion.recovery_diagnostic.v1",
            "issues": sorted(set(issues) & _RECOVERY_ISSUES)}




def is_reference_audit_unit(unit: Mapping[str, Any]) -> bool:
    """Recognize generated audit records, including pre-marker saved candidates."""
    diagnostic = unit.get("recovery_diagnostic", {})
    issues = diagnostic.get("issues", []) if isinstance(diagnostic, Mapping) else []
    if "audit_only" in issues:
        return True
    if (unit.get("title") != "待核对参考来源 / References to review"
            or "reference_unresolved" not in issues or unit.get("citations")):
        return False
    text = str(unit.get("content_markdown", "")).strip()
    match = re.fullmatch(r"(`{3,})text\n(.*)\n\1", text, re.DOTALL)
    if not match:
        return False
    try:
        return isinstance(json.loads(match[2]), list)
    except ValueError:
        return False
