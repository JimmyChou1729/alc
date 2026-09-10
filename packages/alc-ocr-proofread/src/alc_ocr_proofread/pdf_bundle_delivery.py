"""Explicit model adoption and human approval boundaries for PDF candidates."""

from __future__ import annotations

import hashlib

from ac_document import PDFSourceBundleError
from ac_document.pdf_revision import publish_reviewed_pdf_source

from .pdf_bundle_edit import validate_candidate


def adopt_pdf_candidate(
    manifest,
    candidate,
    *,
    candidate_digest,
    output_dir,
    mode="model",
    confirm_reviewed=False,
):
    original, _, _ = validate_candidate(manifest, candidate)
    if candidate_digest != candidate["candidate_digest"]:
        raise PDFSourceBundleError(
            "pdf_review_stale",
            "The review candidate changed; reload it before adopting.",
        )
    if mode not in {"model", "user"}:
        raise PDFSourceBundleError("pdf_review_invalid", "Unknown review mode.")
    if mode == "user" and (
        confirm_reviewed is not True or candidate["uncertainty_count"] != 0 or candidate.get("diagnostic_count", 0) != 0
    ):
        raise PDFSourceBundleError(
            "pdf_review_incomplete",
            "Review every page and resolve uncertainties before approving.",
        )
    corrected = candidate["corrected_html"].encode()
    review = {
        "schema_version": "ac.document.pdf_review.v2",
        "source_bundle_digest": original["bundle_digest"],
        "source_sha256": original["source"]["sha256"],
        "reviewed_source_sha256": hashlib.sha256(corrected).hexdigest(),
        "candidate_digest": candidate_digest,
        "reviewer": "user" if mode == "user" else "model",
        "approved": mode == "user",
        "uncertainty_count": candidate["uncertainty_count"],
        "page_count": len(original["pages"]),
        "manual_edits": candidate.get("manual_edits", {}),
        "manual_resolutions": candidate.get("manual_resolutions", {}),
    }
    return publish_reviewed_pdf_source(
        manifest, reviewed_source=corrected, review=review, output_dir=output_dir
    )


def approve_pdf_candidate(
    manifest, candidate, *, candidate_digest, confirm_reviewed, output_dir
):
    return adopt_pdf_candidate(
        manifest,
        candidate,
        candidate_digest=candidate_digest,
        confirm_reviewed=confirm_reviewed,
        output_dir=output_dir,
        mode="user",
    )
