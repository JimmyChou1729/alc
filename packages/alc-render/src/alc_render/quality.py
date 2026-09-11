"""Quality projection from verified selected revisions, not transient event totals."""

from collections.abc import Mapping
from .html import HTMLRenderError, read_publication_workspace_state


def publication_translation_quality(publication_path) -> dict:
    try:
        state = read_publication_workspace_state(publication_path)
    except HTMLRenderError as exc:
        raise ValueError("Publication quality is unavailable: " + str(exc)) from exc
    ids = {"source_text": set(), "review_skipped": set()}
    warning_ids = set()
    issues = []
    blocks = {b.block_id: b for b in state.publication.source_document.blocks}
    for revision in state.selected_revisions:
        if revision.provenance.get("translation_quality_resolved"):
            continue
        warning = revision.provenance.get("translation_quality")
        if warning is not None:
            if not isinstance(warning, Mapping) or warning.get("schema_version") != "alc.translate.quality_diagnostic.v1":
                raise ValueError("Invalid translation quality diagnostic")
            warning_ids.update(block.block_id for block in revision.anchor.related_blocks)
            for anchor in revision.anchor.related_blocks:
                block = blocks.get(anchor.block_id)
                if block is not None:
                    message = str(warning.get("message", ""))
                    reason = "译文中的引用分组与原文不同，请核对引用位置。" if "bibliography citation groups" in message else "译文与原文的结构标记存在差异，请核对这一段。"
                    issues.append({"block_id": block.block_id, "ordinal": block.ordinal + 1,
                        "excerpt": str(block.payload.get("text", ""))[:200], "reason": reason})
        fallback = revision.provenance.get("translation_fallback")
        if fallback is None:
            continue
        if (
            not isinstance(fallback, Mapping)
            or fallback.get("schema_version") != "alc.translate.fallback.v1"
            or fallback.get("kind") not in ids
        ):
            raise ValueError("Selected translation has an invalid fallback declaration")
        ids[fallback["kind"]].update(
            block.block_id for block in revision.anchor.related_blocks
        )
    return {
        "schema_version": "alc.render.translation_quality.v1",
        "available": True,
        "publication_digest": state.publication.publication_digest,
        "edition_digest": state.edition_digest,
        "source_fallback_count": len(ids["source_text"]),
        "translation_warning_count": len(warning_ids),
        "translation_warning_ids": sorted(warning_ids),
        "translation_issues": issues,
        "review_skipped_count": len(ids["review_skipped"]),
        "source_fallback_ids": sorted(ids["source_text"]),
        "review_skipped_ids": sorted(ids["review_skipped"]),
    }
