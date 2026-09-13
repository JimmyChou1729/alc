"""Bounded plain-text editing of source-bound PDF proofreading candidates."""

from __future__ import annotations

import copy
import hashlib
import html
import tempfile
from pathlib import Path

from ac_document import PDFSourceBundleError, verify_pdf_source_bundle

from .pdf_bundle import (
    _HTML,
    PDFBundleProofreadService,
    _skeleton,
    _visible_text,
    candidate_digest,
)


def _invalid(message):
    raise PDFSourceBundleError("pdf_review_invalid", message)


def validate_candidate(manifest, candidate):
    if not isinstance(candidate, dict) or candidate.get(
        "candidate_digest"
    ) != candidate_digest(candidate):
        _invalid("Candidate digest does not match its content.")
    bundle = verify_pdf_source_bundle(manifest)
    source = (Path(manifest).parent / bundle["source"]["path"]).read_bytes()
    if (
        candidate.get("original_bundle_digest") != bundle["bundle_digest"]
        or candidate.get("pdf_sha256") != bundle["original"]["sha256"]
        or candidate.get("source_sha256") != bundle["source"]["sha256"]
        or not isinstance(candidate.get("original_html"), str)
        or candidate["original_html"].encode() != source
        or candidate.get("proofread") is not False
        or candidate.get("approval_required") is not True
        or candidate.get("status") != "reviewable"
    ):
        _invalid("Candidate is not bound to this original source.")
    corrected = candidate.get("corrected_html")
    if not isinstance(corrected, str) or hashlib.sha256(
        corrected.encode()
    ).hexdigest() != candidate.get("corrected_sha256"):
        _invalid("Candidate source bytes changed.")
    structured = bool(candidate.get("inline_repairs"))
    baseline = candidate.get("inline_baseline_html") if structured else corrected
    if not isinstance(baseline, str) or _skeleton(baseline) != _skeleton(source.decode()):
        _invalid("Candidate baseline changes document structure or protected content.")
    original_parser = _HTML(source.decode(), bundle)
    baseline_parser = _HTML(baseline, bundle)
    if [(s.page, s.target) for s in original_parser.slots] != [
        (s.page, s.target) for s in baseline_parser.slots
    ]:
        _invalid("Candidate changed editable source slots.")
    for before, after in zip(original_parser.slots, baseline_parser.slots):
        old_text = html.unescape(original_parser.source[before.start:before.end])
        new_text = html.unescape(baseline_parser.source[after.start:after.end])
        if old_text.strip() and not new_text.strip():
            _invalid("Candidate removes all content from an editable source node.")
    if structured:
        from ac_document.pdf_inline import validate_inline_revision
        validate_inline_revision(source.decode(), corrected, bundle,
            {**candidate, "schema_version": "ac.document.pdf_review.v3"})
    corrected_parser = _HTML(corrected, bundle)
    pages = candidate.get("pages")
    if (
        not isinstance(pages, list)
        or not all(isinstance(p, dict) for p in pages)
        or [p.get("page_number") for p in pages]
        != [p["page_number"] for p in bundle["pages"]]
    ):
        _invalid("Candidate must cover every original page exactly once.")
    if not isinstance(candidate.get("manual_resolutions", {}), dict):
        _invalid("Invalid manual resolution audit.")
    unresolved = 0
    for page in pages:
        number = page["page_number"]
        if page.get("original_html") != original_parser.fragment(number) or page.get(
            "corrected_html"
        ) != corrected_parser.fragment(number):
            _invalid("Candidate page fragments do not match its document.")
        if not isinstance(page.get("uncertainties"), list) or not all(
            isinstance(u, dict) for u in page["uncertainties"]
        ):
            _invalid("Invalid page uncertainty records.")
        for index, uncertainty in enumerate(page["uncertainties"]):
            resolution = uncertainty.get("resolution")
            if resolution is not None:
                uid = f"{number}:{index}"
                if (
                    resolution not in {"corrected", "accepted"}
                    or candidate.get("manual_resolutions", {}).get(uid) != resolution
                ):
                    _invalid("Uncertainty resolution lacks a manual audit record.")
            else:
                unresolved += 1
    if (
        type(candidate.get("uncertainty_count")) is not int
        or candidate["uncertainty_count"] != unresolved
    ):
        _invalid("Candidate uncertainty count is inconsistent.")
    return bundle, original_parser, corrected_parser


def editable_candidate(manifest, candidate):
    _, original, corrected = validate_candidate(manifest, candidate)
    result = copy.deepcopy(candidate)
    result.setdefault("base_candidate_digest", candidate["candidate_digest"])
    if candidate.get("inline_repairs"):
        result["manual_editing_supported"] = False
    for page in result["pages"]:
        number = page["page_number"]
        old = [s for s in original.slots if s.page == number]
        new = [s for s in corrected.slots if s.page == number]
        if candidate.get("inline_repairs"):
            page["segments"] = [{"id": f"{number}:{i}", "kind": b.target,
                "original_text": "", "corrected_text": html.unescape(corrected.source[b.start:b.end]),
                "read_only": True} for i, b in enumerate(new)]
            for i, item in enumerate(page["uncertainties"]):
                item["id"] = f"{number}:{i}"
            continue
        page["segments"] = [
            {
                "id": f"{number}:{i}",
                "kind": a.target,
                "original_text": html.unescape(original.source[a.start : a.end]),
                "corrected_text": html.unescape(corrected.source[b.start : b.end]),
            }
            for i, (a, b) in enumerate(zip(old, new))
        ]
        for i, item in enumerate(page["uncertainties"]):
            item["id"] = f"{number}:{i}"
    result["candidate_digest"] = candidate_digest(result)
    return result


def revise_candidate(manifest, candidate, *, edits, resolutions):
    if candidate.get("inline_repairs") and edits:
        raise PDFSourceBundleError("pdf_review_structure_readonly", "含结构修订的结果请在 Reader 中编辑。")
    if candidate.get("manual_edits") or candidate.get("manual_resolutions"):
        _invalid(
            "Apply overrides to the original model candidate, not a previous revision."
        )
    result = editable_candidate(manifest, candidate)
    if not isinstance(edits, dict) or not isinstance(resolutions, dict):
        _invalid("Edits and resolutions must be mappings.")
    segments = {s["id"]: s for p in result["pages"] for s in p["segments"]}
    uncertainties = {u["id"]: u for p in result["pages"] for u in p["uncertainties"]}
    if any(
        k not in segments or not isinstance(v, str) or (not v.strip() and v != segments[k]["corrected_text"])
        for k, v in edits.items()
    ):
        _invalid("Edits require a known segment and nonempty plain text.")
    if any(
        k not in uncertainties or v not in ("corrected", "accepted")
        for k, v in resolutions.items()
    ):
        _invalid("Unknown uncertainty or resolution.")
    effective = {k: v for k, v in edits.items() if v != segments[k]["corrected_text"]}
    changed_pages = {k.split(":")[0] for k in effective}
    if any(
        v == "corrected" and k.split(":")[0] not in changed_pages
        for k, v in resolutions.items()
    ):
        _invalid("A corrected uncertainty needs a manual edit on that page.")
    bundle = verify_pdf_source_bundle(manifest)
    source = result["corrected_html"]
    parsed = _HTML(source, bundle)
    positions = {}
    counts = {}
    for slot in parsed.slots:
        index = counts.get(slot.page, 0)
        positions[f"{slot.page}:{index}"] = slot
        counts[slot.page] = index + 1
    for key in sorted(effective, key=lambda k: positions[k].start, reverse=True):
        slot = positions[key]
        source = (
            source[: slot.start]
            + html.escape(effective[key], quote=slot.target != "text")
            + source[slot.end :]
        )
    if not result.get("inline_repairs") and _skeleton(source) != _skeleton(result["original_html"]):
        _invalid("Manual edits change document structure.")
    with tempfile.TemporaryDirectory(prefix="alc-review-validation-") as directory:
        service = PDFBundleProofreadService(directory)
        service.runtime_root.mkdir(parents=True, exist_ok=True)
        service._validate_corrected(source, Path(manifest), bundle)
    parsed = _HTML(source, bundle)
    result.update(
        corrected_html=source,
        corrected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        manual_edits=effective,
        manual_resolutions=dict(resolutions),
    )
    for page in result["pages"]:
        page["corrected_html"] = parsed.fragment(page["page_number"])
        page["corrected_text"] = _visible_text(page["corrected_html"])
        for uncertainty in page["uncertainties"]:
            uncertainty.pop("resolution", None)
            if uncertainty["id"] in resolutions:
                uncertainty["resolution"] = resolutions[uncertainty["id"]]
    result["uncertainty_count"] = sum(
        not u.get("resolution") for p in result["pages"] for u in p["uncertainties"]
    )
    result["candidate_digest"] = candidate_digest(result)
    return editable_candidate(manifest, result)
