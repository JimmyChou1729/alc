"""Versioned OCR triage shared by generation and read-only presentation."""

import re

POLICY_VERSION = "ocr-triage.v2"
POLICY_PROMPT = """
Apply this OCR triage policy to every document, regardless of subject:
1. Apply only visually confirmed transcription corrections through exact edits.
   Do not put confirmed corrections in uncertainties. before must differ from after.
2. Ignore running headers, footers, page numbers and purely decorative text unless
   their loss changes the meaning of the body. Do not invent text descriptions of
   labels already preserved in a figure image merely because image_alt is empty.
3. uncertainties is reserved for genuinely ambiguous or unreadable source content:
   a nonempty exact excerpt/location plus why the original page cannot decide it.
   Set kind=ambiguous only for this case; give competing readings when available.
4. Nonessential layout differences use kind=irrelevant; a clearly known omission
   that cannot be represented safely uses kind=limitation. Neither is ambiguity.
5. A failed coverage check is diagnostic status, not evidence of an ambiguous word.
Never fix an error actually printed in the source book. Preserve original wording
where uncertain; never invent a correction from context alone.
"""


def issue_kind(issue):
    """Conservative legacy normalization; unknown concrete issues stay visible."""
    kind = issue.get("kind")
    if kind in {"ambiguous", "irrelevant", "limitation"}:
        return kind
    reason = str(issue.get("reason", ""))
    excerpt = str(issue.get("excerpt", "")).strip()
    if (
        "proposed_edit" in issue
        or reason == "Edit does not change the source text."
        or reason.startswith("Visual comparison is incomplete:")
    ):
        return "limitation"
    if re.search(
        r"page[- ]?header|running header|page footer|page number", reason, re.I
    ) and re.search(
        r"absent|missing|not represented|no corresponding|no editable", reason, re.I
    ):
        return "irrelevant"
    if re.search(
        r"requir\w* (?:a |an |adding |new |a new )*structure|structure change|new (?:text|structural).*node|not represented.*(?:image_alt|editable)|image.alt.*empty|rather than.*transcription correction",
        reason,
        re.I,
    ):
        return "limitation"
    if not excerpt and re.search(
        r"contract|coverage|original structure|formula is missing", reason, re.I
    ):
        return "limitation"
    if re.search(
        r"heading.*absent|heading.*missing|diagram labels.*missing", reason, re.I
    ):
        return "limitation"
    return "ambiguous"


def split_issues(issues):
    ambiguous, diagnostics = [], []
    for issue in issues:
        kind = issue_kind(issue)
        if kind == "ambiguous":
            ambiguous.append(issue)
        elif kind == "limitation":
            diagnostics.append(issue)
    return ambiguous, diagnostics
