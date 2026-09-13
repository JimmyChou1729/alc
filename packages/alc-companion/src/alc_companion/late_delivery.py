"""Deliver verified translations when optional guide processing fails."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

from ac_jobs import canonical_json_bytes

from ._build_support import read_json
from .translation_results import load_translation_selection


def completed_chapters(context, chapters, source, target_language, translation_required, accepted=()):
    by_id = {item["chapter_id"]: item for item in accepted}
    values = []
    for chapter in chapters:
        saved = by_id.get(chapter.chapter_id)
        if saved is None:
            ref = context.artifacts.find(f"chapters/{chapter.chapter_id}/accepted")
            saved = read_json(context, ref, "completed chapter") if ref else {}
        translation = saved.get("translation_result")
        if translation_required:
            if translation is None:
                ref = context.artifacts.find(f"chapters/{chapter.chapter_id}/translation/result")
                if ref is None:
                    return None
                translation = read_json(context, ref, "completed translation")
            load_translation_selection(context, translation, source=source,
                block_ids=chapter.block_ids, target_language=target_language)
        values.append({
            "chapter_id": chapter.chapter_id, "title": chapter.title,
            "block_ids": list(chapter.block_ids),
            "display_anchor_block_id": chapter.display_anchor_block_id,
            "section_block_ids": list(chapter.section_block_ids),
            "section_titles": list(chapter.section_titles),
            "section_levels": list(chapter.section_levels),
            "guide_expected": chapter.generate_guide,
            "translation_result": translation if translation_required else None,
            "learning_units": saved.get("learning_units", []),
            "delivery_issue": saved.get("delivery_issue"),
        })
    return values


def publish_fallback(context, *, publisher, reference_resolver, values, reason, **options):
    """Use a separate namespace after a possibly half-written publication."""
    try:
        values, bibliography = reference_resolver(values)
    except (KeyError, TypeError, ValueError):
        values = [{**item, "learning_units": []} for item in values]
        bibliography = ()
    for attempt in range(2):
        if attempt:
            values = [{**item, "learning_units": []} for item in values]
            bibliography = ()
        issue = {
            "issue_id": "late-guide-delivery",
            "category": "guide_delivery_degraded",
            "scope": "document", "fallback": "verified_translations_and_available_guides",
            "affected_count": 1, "source_preserved": True,
            "retry": "not_semantic_retry", "evidence": reason,
        }
        identity = hashlib.sha256(canonical_json_bytes({
            "chapters": values, "bibliography": bibliography, "reason": reason,
            "attempt": attempt,
        })).hexdigest()
        scoped = SimpleNamespace(artifacts=context.artifacts.scoped("delivery-fallback/" + identity),
                                 events=context.events)
        try:
            prior_issues = tuple(item["delivery_issue"] for item in values
                                if isinstance(item.get("delivery_issue"), dict))
            return publisher(scoped, chapters=values, bibliography=bibliography,
                             delivery_issues=(*prior_issues, issue), **options)
        except (KeyError, TypeError, ValueError):
            if attempt:
                raise
    raise AssertionError("unreachable")
