"""Prompt contracts for source-anchored Companion generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


CHAPTER_GUIDE_PROMPT_VERSION = "alc.companion.chapter-learning-prompt.v26"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V25 = "alc.companion.chapter-learning-prompt.v25"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V24 = "alc.companion.chapter-learning-prompt.v24"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V23 = "alc.companion.chapter-learning-prompt.v23"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22 = "alc.companion.chapter-learning-prompt.v22"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21 = "alc.companion.chapter-learning-prompt.v21"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20 = "alc.companion.chapter-learning-prompt.v20"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19 = "alc.companion.chapter-learning-prompt.v19"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V18 = (
    "alc.companion.chapter-learning-prompt.v18"
)
CHAPTER_GUIDE_REVIEW_PROMPT_VERSION = "alc.companion.chapter-learning-review-prompt.v20"
HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19 = "alc.companion.chapter-learning-review-prompt.v19"
HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18 = "alc.companion.chapter-learning-review-prompt.v18"
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17 = (
    "alc.companion.chapter-learning-prompt.v17"
)
HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17 = (
    "alc.companion.chapter-learning-review-prompt.v17"
)
HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16 = (
    "alc.companion.chapter-learning-prompt.v16"
)
HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16 = (
    "alc.companion.chapter-learning-review-prompt.v16"
)
AUTHOR_IDENTITY_PROMPT_VERSION = "alc.companion.author-identity-prompt.v4"
HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3 = (
    "alc.companion.author-identity-prompt.v3"
)
EDITORIAL_PROPOSER_PROMPT_VERSION = (
    "alc.companion.cross-chapter-editorial-proposer-prompt.v1"
)
EDITORIAL_REVIEWER_PROMPT_VERSION = (
    "alc.companion.cross-chapter-editorial-reviewer-prompt.v1"
)


def _closed(
    properties: Mapping[str, Any], required: Sequence[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


_NONEMPTY = {"type": "string", "minLength": 1}
_STRING_IDS = {
    "type": "array",
    "items": _NONEMPTY,
    "uniqueItems": True,
}
_REFERENCE = _closed(
    {"title": _NONEMPTY, "source": _NONEMPTY},
    ("title", "source"),
)
_GUIDE_TEXT = _closed(
    {
        "title": _NONEMPTY,
        "content_markdown": _NONEMPTY,
    },
    ("title", "content_markdown"),
)
_SECTION_GUIDE = _closed(
    {
        "section_number": {"type": "integer", "minimum": 1},
        "title": _NONEMPTY,
        "content_markdown": _NONEMPTY,
    },
    ("section_number", "title", "content_markdown"),
)
_COMPANION = _closed(
    {
        "after_part": {"type": "integer", "minimum": 1},
        "title": _NONEMPTY,
        "content_markdown": _NONEMPTY,
    },
    ("after_part", "title", "content_markdown"),
)
CHAPTER_GUIDE_PROPOSAL_SCHEMA = _closed(
    {
        "chapter_guide": {"anyOf": [_GUIDE_TEXT, {"type": "null"}]},
        "section_guides": {"type": "array", "items": _SECTION_GUIDE},
        "companions": {"type": "array", "items": _COMPANION},
        "references": {"type": "array", "items": _REFERENCE},
    },
    ("chapter_guide", "section_guides", "companions", "references"),
)
AUTHOR_IDENTITY_SCHEMA = _closed(
    {
        "authors": _STRING_IDS,
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "basis": _NONEMPTY,
        "anchor_block_ids": _STRING_IDS,
    },
    ("authors", "confidence", "basis", "anchor_block_ids"),
)
_POSITIVE_INTEGERS = {
    "type": "array",
    "items": {"type": "integer", "minimum": 1},
    "uniqueItems": True,
}
CHAPTER_GUIDE_REVIEW_AUDIT_SCHEMA = _closed(
    {
        "checked_complete_chapter": {"const": True},
        "checked_part_numbers": _POSITIVE_INTEGERS,
        "checked_section_numbers": _POSITIVE_INTEGERS,
    },
    (
        "checked_complete_chapter",
        "checked_part_numbers",
        "checked_section_numbers",
    ),
)


_GUIDE_CONTENT_INSTRUCTION = """
Write the Companion for the current source segment. The program owns chapter,
section, block, learning-unit, and reference identities. Fill only the simple
semantic template supplied in the loop context: one optional `chapter_guide`
(an object or `null`), sparse `section_guides` selected by `section_number`,
sparse local `companions` selected by `after_part`, and `references`
containing only `title` and `source`.

Use only the exact local `section_number` values listed in the supplied
`sections` context. If that list is empty, `section_guides` must be empty. A
numeral printed in the source heading is content, not a local section number.

The chapter guide appears before the body and helps the reader enter the
chapter as a whole. A section guide appears after that section's translated
heading and before its body. A companion appears after its selected source
part and translation. Add section guides and companions only where useful;
there is no quota. Each local companion must have one primary target part and
must directly explain material at that location. Do not combine independent
themes from different source locations merely to make one longer unit. Split
them, or put genuinely chapter-wide synthesis in `chapter_guide`. In
particular, do not move an explanation of an earlier title, quotation, work,
or concept to a later date merely because the same unit mentions a later
development. Work only on the current source segment.

Every local companion and section guide must add a concrete increment of
understanding that the nearby source does not itself supply. Missing context,
an intermediate derivation, a logical bridge, prerequisite clarification, a
later correction or development, historical significance, and a substantive
connection across passages are non-exhaustive examples, not a taxonomy or
quota. A brief source phrase may identify the explanation's target, but the
body must then add new information, a missing reasoning step, context, or a
useful connection not already available at that location. Compacting,
reorganizing, or summarizing information already present in the paragraph or
chapter does not qualify for a local companion or section guide, even when
the result is fluent or shorter. Reordered facts, same-meaning rewrite,
generic summary, transitions such as “this shows”, or polished paraphrase
likewise do not qualify. If removing a proposed unit would leave the resolved
reader's understanding essentially unchanged, omit it. Simple,
self-contained source material needs no local companion.

A chapter guide has a different role. It may select, organize, and compress
information already present in the source segment only when doing so gives a
specific reading action or understanding increment that is not readily
obtainable from the source itself. It may also add new background,
connections, reading strategies, later developments, or any other useful help
supported by the source and references. Permission to compress is not a
default form, a limit, or the chapter guide's only purpose. Do not merely
retell the segment or reproduce its navigation: selection and compression
must provide that concrete additional benefit.

When the current segment primarily contains publication metadata,
copyright or cataloging material, a navigation list, an index, or another
paratextual lookup aid, prefer `chapter_guide: null`. Keep a guide only when it
offers a concrete reading action or understanding increment the segment does
not readily provide. Judge the actual content, not title keywords: a preface
or other paratext may still deserve a guide when it supplies a valuable
cross-segment reading route or substantive orientation.

Return `chapter_guide: null` when the complete chapter is already simple and
self-contained and no useful orientation, background, connection, reading
strategy, later development, or other concrete reading benefit is available.
Do not create a chapter guide merely to fill the field.

The structured `title` field is the unit's sole main title.
`content_markdown` must begin with substantive prose, not another Markdown
heading. Later internal headings are allowed only when the body genuinely
needs structure.

Write titles and Markdown in the target language. Cite an externally grounded
claim nearby using the reference's one-based array position, for example
`[@1]` or `[@2]`. Include only cited references. ALC assigns publication
identities and enriches cache metadata deterministically. References may be
absent or arbitrarily numerous. The complete translation lane is frozen
before Companion generation begins. Read the original and frozen translation
together. Use the frozen translation's proper names, translated titles, and
technical terminology consistently in every generated title and body; do not
silently invent a different translation. Use the supplied chapter glossary
consistently as well.

Use the reader background specified in the user intent. Otherwise, for
popular, directional, or weakly specialized writing assume an adult with
average general literacy and no specialist training. For a research paper,
assume a professional student who completed the relevant foundational
courses. For a textbook, assume a student who completed standard prerequisite
courses, but do not assume difficult prerequisite concepts are confidently
mastered.

Write every guide and companion in plain, accessible language suited to the
resolved reader. The source and translation are material to explain, not
style templates. If either is difficult, compressed, jargon-heavy, or
syntactically dense, do not imitate that style. Unpack the reasoning, explain
necessary terms, prefer concrete wording, and split overloaded sentences or
steps while preserving technical accuracy. A reader should find the
Companion easier to understand than the passage it accompanies.

Concentrate first on making difficult or compressed material understandable:
provide missing background for isolated quotations or named works, supply
skipped derivation steps, bridge real logical gaps, and explain prerequisite
material the reader should not be assumed to command. When references support
it, add later corrections, disputes, doubts, unexpectedly important
developments, or historical significance. These are priorities, not a
taxonomy or quota.

Do not decide in advance that the Companion will explain only one kind of
thing. Check the actual source for every place where the resolved reader needs
help. One useful explanation does not cancel a different need nearby: for
example, historical context does not replace an omitted equation step, and an
equation explanation does not replace needed context. When a source contains
mathematical, scientific, or other technical material, actively check for
unexplained terms, mechanisms, methods, formal steps, equations, experiments,
and relevant people, and add useful explanations rather than overlooking
them. This request adds missing coverage; it is not a reason to omit other
useful Companion material, and the total amount may grow. These are
non-exhaustive signals, not a fixed list, minimum count, or required format.

Before explaining a technical term, mechanism, or person, search the complete
source document to see whether the author explains it substantially elsewhere.
Use `source_commands.full_document_search_examples`: one example shows a literal
term search; the “A or B” example is represented by two literal ALC commands,
one for each alternative, because the command does not require shell-regex
syntax. Replace only the final query argument. Search the original-language
name and useful alternative names when appropriate. If the source explains
the subject elsewhere, point the reader to or connect that explanation
instead of redundantly paraphrasing it. If it does not, supply the missing
explanation. A remote, highly compressed, or differently purposed occurrence
does not automatically make local help unnecessary.

Prefer direct affirmative explanation. This rule applies to every generated
field, including chapter-guide, section-guide, and local-companion titles,
definitions, opening sentences, transitions, and body prose. Do not use a
negative setup as a rhetorical shortcut for a definition or explanation.
Forms such as “not X but Y”, “not just X”, “not merely X”, “does not mean X;
instead Y”, and their target-language equivalents all count as corrective
framing. Use one only when the source, user intent, or an inspected reference
shows that X is a live misconception, and make that basis clear. Otherwise
state Y directly. Ordinary factual negation is allowed when the fact itself is
negative; never manufacture a prior reader belief.

Translate English excerpts or quotations into the target language while
preserving and citing the source's English title and URL. English Wikipedia is
an optional ordinary source; only `en.wikipedia.org` is allowed.

"""

_GUIDE_LEGACY_SOURCE_POLICY = """Use only the verified document, frozen translation, and any reviewed
supplements supplied with this build. External academic research is an
optional host-level workflow and is not performed by alc-companion itself."""

_GUIDE_RESEARCH_POLICY = """Research when it materially improves the Companion. Prefer a source already
available through the shared paper cache. External reference sources may be
used when needed. There is no reference-count limit, and no minimum. If
acquisition is required, use any currently available and authorized
capability-matching tool; do not assume one exists or insist on
authorization that was not granted."""

_GUIDE_EXTERNAL_REFERENCE_POLICY = """

Find external references that materially support the Companion's supplementary
explanations. Use web search and cite only sources whose title and identifier
or URL are supported by a reliable source. Prefer arXiv IDs, then DOI IDs;
use a stable source URL when neither applies. Read the relevant content before
citing it and confirm that it supports the specific explanation.
"""

_GUIDE_VERIFY_BEFORE_TRIMMING = """

When a useful explanation extends beyond the supplied source and lacks support,
first try to verify the specific claim with available authorized research tools.
Do not discard a valuable explanation solely because it currently lacks a
citation. Read relevant evidence, correct the claim and state its assumptions,
then cite the inspected source nearby. This applies especially when review has
identified a concrete evidence gap. A citation to the original document does
not support an extension absent from that document.
If tools are unavailable, an attempted search finds no usable support, or the
extension adds little value, narrow or omit it and continue the full Companion.
Do not retain unsupported claims, invent sources, repeat an unchanged failed
search, or turn the chapter into a separate research task. No retrieval or
reference quota applies.
"""

_GUIDE_REVIEW_VERIFY_BEFORE_TRIMMING = """

For a valuable extension with a concrete evidence gap, first use available
research tools to check it, or ask the next proposer to verify that specific
claim before narrowing or omitting it. Name the missing support and the reader
benefit to preserve; do not offer immediate deletion as an equal first choice
merely because a citation is missing. Distinguish missing evidence from a
false or low-value claim. After an unsuccessful verification attempt, or when
no suitable tool is available, source-bounded wording or omission is appropriate.
Do not demand research for content already adequately grounded, require a
citation quota, or claim that an uninspected source supports the extension.
"""

_GUIDE_SOURCE_ACCESS_INSTRUCTION = """

When `source_commands.availability` is `exact`, the source body is not embedded
in the loop context: run the supplied commands for exact numbered parts,
complete current sections, the complete current chapter, search, and
source inspection. For a host request, copy the selected command's `shell`
value exactly into `host_request.instruction` and its caller-owned
`host_request_id` exactly into `host_request.request_id`; never invent or reuse an ID
within a task. Do not add commentary or another command. Read the complete
original chapter once before drafting. When
`source_commands.translation.availability` is `exact`, also run its
`complete-current-chapter` command and read the complete frozen translation
before drafting. For every local companion, confirm its placement and wording
against both the original `source` part command and the matching frozen
translation `translation.parts` command. When source availability is
`fallback_only`, inspect the attached verified text-only Companion source
using the supplied chapter part and line metadata instead. The frozen
translation remains the terminology authority whenever it is available.
Do not explore ALC source code or cache directories to rediscover access
methods. Avoid reading the whole book when the complete current chapter is
enough. Never open image or media assets.

On every revised proposal, use only part and section locations recorded as
inspected in the preceding review payload. This is especially important for
the terminal revision, which is published without another review. A reviewer
who proposes a valuable addition at a new location must inspect and record
that location first.
"""

_CHAPTER_GUIDE_INSTRUCTION_V17 = (
    _GUIDE_CONTENT_INSTRUCTION
    + _GUIDE_LEGACY_SOURCE_POLICY
    + _GUIDE_SOURCE_ACCESS_INSTRUCTION
)
_GUIDE_MATH_INSTRUCTION = """

Use `$...$` or `\\(...\\)` for inline math. For display math, put the opening
and closing `$$` delimiters on separate lines with the TeX body between them.
Never place display-math content on the same line as either `$$` delimiter.
"""


_CHAPTER_GUIDE_INSTRUCTION_V18 = (
    _CHAPTER_GUIDE_INSTRUCTION_V17 + _GUIDE_MATH_INSTRUCTION
)
_GUIDE_LEGACY_REFERENCE_INSTRUCTION = """

Make the basis of substantive explanations traceable. References are not
limited to external literature: for explanations grounded in the supplied
original document, cite that document with its actual title and inspected
section or numbered part range, using the same `[@n]` mechanism. Identify
these entries as supplied original-document sources; do not invent an author,
URL, edition, page number, or an external publication. A frozen translation
is a reading aid, not an independent source of corroboration.
For additions grounded in a reviewed supplement, cite the actual supplied
source supporting the addition. Do not manufacture a bibliography from
remembered titles or claim to have consulted sources that were not supplied
or inspected. Keep only references actually cited by retained guide content.
An empty reference list is allowed when there is no supported citation; lack
of a reference must not prevent delivering the usable translation and guide.
"""

_CHAPTER_GUIDE_INSTRUCTION_V19 = (
    _CHAPTER_GUIDE_INSTRUCTION_V18 + _GUIDE_LEGACY_REFERENCE_INSTRUCTION
)
_GUIDE_ORIGINAL_REFERENCE_FORMAT = """

For a supplied-original reference, set `source` to exactly
`alc-original:1-14,20`, replacing the example with the inspected one-based
part numbers from the current chapter input. Use comma-separated numbers or
inclusive ranges, not page numbers, equation numbers, titles, or prose.
When no reliable inspected part location is available, use `alc-original:`.
The caller supplies the displayed original-document title; your reference
`title` field remains required but is replaced with that authoritative title.
Never guess page numbers or claim an uninspected part supports an explanation.
External references continue to use their actual title and source.
"""


_CHAPTER_GUIDE_INSTRUCTION = (
    _GUIDE_CONTENT_INSTRUCTION
    + _GUIDE_RESEARCH_POLICY
    + _GUIDE_SOURCE_ACCESS_INSTRUCTION
    + _GUIDE_MATH_INSTRUCTION
    + _GUIDE_ORIGINAL_REFERENCE_FORMAT
)


_CHAPTER_GUIDE_REVIEW_INSTRUCTION = """
Review the chapter guide, sparse section guides, sparse post-part companions,
and references against the actual current source segment. ALC provides context and
recovery, not a prescribed creative form.

Do not criticize merely to demonstrate reviewer activity or present a
stylistic preference as a defect. If the proposal already satisfies reader
needs, is well grounded, and has no concrete path to meaningful improvement,
accept it by choosing `stop`. Choose `continue` only for a specific achievable
gain. Feedback must say what to preserve, what to change, and how.

When you discover a valuable new Companion idea, describe it constructively
in feedback using a supplied local section or part number so the next proposer
can add or improve it. Suggest newly inspected references when useful. The
Companion-specific review payload records the source locations you inspected.
Set `checked_complete_chapter` to true, list every exact part and section read
in `checked_part_numbers` and `checked_section_numbers`, and include locations
inspected for constructive additions as well as locations already used by the
proposal. Never copy a reference body or invent a source, DOI, arXiv
identifier, or URL.

Reject a proposal that uses a `section_number` absent from the supplied local
`sections` context. When that context is empty, both the proposal's
`section_guides` and the review payload's `checked_section_numbers` must be
empty; source-heading numerals do not count as local section numbers.

Actively consider and, when it could materially improve the Companion, inspect
a reference the proposer missed. Both roles may introduce useful new source
material. There is no minimum or maximum reference count, so never search,
criticize, or request a citation merely to make the review look more thorough.

Prioritize missing background for isolated quotations or named works,
skipped derivation steps, logical gaps, prerequisite knowledge the reader may
not command, and reference-grounded later corrections, disputes, doubts,
unexpected developments, or historical significance. Remove or replace
paraphrase, repeated reasoning, generic summary, and unsupported claims.
If an existing unit clearly helps the reader understand something and has no
specific defect, keep it. Do not remove it merely because you want to add a
different kind of explanation. When the source contains mathematical,
scientific, or other technical material, also check its terms, mechanisms,
methods, formal steps, equations, experiments, and relevant people carefully.
Suggest useful additions where the proposal missed them, even if this makes
the Companion longer. For an explanation of a term, mechanism, or person, use
the supplied full-document ALC search examples to check whether the author
already gives a substantial explanation elsewhere; for “A or B”, run both
literal alternative commands. Keep a useful cross-reference or local bridge
when the other occurrence is remote, compressed, or serves a different
purpose.
For every retained local companion and section guide, identify a concrete
understanding increment absent from the nearby source. Reordered source
facts, same-meaning rewrite, a transition such as “this shows”, or prose whose
removal would not change the reader's understanding is not an increment.
Reject a local companion or section guide that merely compacts, reorganizes,
or summarizes information already present nearby, even if it is fluent.
Require new information, a missing reasoning step, context, or a useful
connection that the source does not already make locally.

Review the chapter guide by a different standard. It may select, organize, and
compress information already in the source segment only when that yields a
specific reading action or understanding increment not readily obtainable
from the source itself. It may also add new background, connections, reading
strategies, later developments, or other useful help. Compression is
permitted, not required and not the chapter guide's only purpose. Request
revision when it merely retells the segment or reproduces its contents without
that concrete additional benefit. For publication metadata, copyright or
cataloging material, navigation lists, indexes, and other paratextual lookup
aids, prefer a null guide unless this test is met. Judge actual content rather
than title keywords, and retain a genuinely useful preface or cross-segment
reading route.
Require plain, accessible language in every title and body. Treat the source
and translation as material to explain, not style templates. If they are
difficult, compressed, jargon-heavy, or syntactically dense, the proposal
must make them easier to understand by unpacking reasoning, explaining
necessary terms, using concrete wording, and splitting overloaded sentences
or steps without losing technical accuracy. Request revision for needlessly
abstract, opaque, or source-imitating prose even when its facts are correct.
Compare every generated proper name, translated title, and technical term
with the frozen translation. Require the translation's established wording
throughout the Companion, including titles, unless the user explicitly asked
for a different wording. A fluent but inconsistent retranslation is a
material defect.
Require nearby positional `[@N]` citations for externally grounded claims.

Treat unsupported corrective framing as a material defect. Audit every
generated field, including titles, definitions, opening sentences,
transitions, and body prose. “Not X but Y”, “not just X”, “not merely X”,
“does not mean X; instead Y”, and target-language equivalents are all
corrective framing. They are justified only when supplied material shows that
X is a live misconception and the proposal makes that basis clear. Otherwise
request a direct affirmative replacement even when the rest of the unit is
strong; do not overlook the defect merely because the contrast occurs in a
title or a technically accurate definition. Ordinary factual negation is
allowed when the fact itself is negative.

When `source_commands.availability` is `exact`, run the supplied original-source
`complete-current-chapter` command before judging anything. When
`source_commands.translation.availability` is `exact`, also run its
`complete-current-chapter` command before judging anything. For a host request,
copy the selected command's `shell` value exactly into
`host_request.instruction` and its caller-owned `host_request_id` exactly into
`host_request.request_id`; never invent or reuse an ID within a task. Then run both
matching exact `part-N` commands for every local companion and both matching
`section-N-complete` commands for every section guide. When source
availability is `fallback_only`, inspect the corresponding complete chapter
and exact locations in the attached verified text-only Companion source using
the supplied part and line metadata; still inspect the frozen translation
through its supplied commands. In either mode, compare each unit with both
the original and translation at its proposed display location and record
every inspected location in the review payload. If useful material is
misplaced, request a move or split rather than deleting it automatically. If
a proposed constructive addition uses another location, inspect and record
that location too. Avoid reading the whole book when the complete current
chapter is enough. Never open image or media assets.
"""

_CHAPTER_GUIDE_REVIEW_INSTRUCTION_V17 = _CHAPTER_GUIDE_REVIEW_INSTRUCTION
_CHAPTER_GUIDE_REVIEW_INSTRUCTION += """

Treat malformed math delimiters as a material defect. Require `$...$` or
`\\(...\\)` for inline math and require display-math `$$` delimiters to occupy
separate lines with only the TeX body between them.
"""


_CHAPTER_GUIDE_INSTRUCTION_V16 = _CHAPTER_GUIDE_INSTRUCTION_V17.replace(
    "Use only the exact local `section_number` values listed in the supplied\n"
    "`sections` context. If that list is empty, `section_guides` must be empty. A\n"
    "numeral printed in the source heading is content, not a local section number.\n\n",
    "",
)
_CHAPTER_GUIDE_REVIEW_INSTRUCTION_V16 = (
    _CHAPTER_GUIDE_REVIEW_INSTRUCTION_V17.replace(
        "Reject a proposal that uses a `section_number` absent from the supplied local\n"
        "`sections` context. When that context is empty, both the proposal's\n"
        "`section_guides` and the review payload's `checked_section_numbers` must be\n"
        "empty; source-heading numerals do not count as local section numbers.\n\n",
        "",
    )
)

_EDITORIAL_PROPOSER_INSTRUCTION = """
Review the complete frozen editorial inventory and full-text view across all
generated chapter guides, section guides, and local companions. Report only
genuine cross-chapter redundancy. Repeated terminology, keywords, or related
topics are not by themselves redundant. Preserve repetition that supports
local understanding, distinct derivations, different experimental links, or
different later developments.

Prefer revising a repeated unit into a chapter-specific increment of
understanding. Propose omission only when the unit contributes no distinct
local value. Do not impose a deletion count, coverage target, style quota, or
closed taxonomy. Do not add scientific claims, references, or source anchors.
Every finding must bind at least two units from different chapters. Every edit
must use the exact unit ID and base content digest from the frozen inventory.
A replacement must remain faithful to the unit's source anchors; use the
verified source-evidence inputs named in the caller input_manifest to inspect
those locations before proposing it.
A revise edit returns the complete replacement title and Markdown body; an
omit edit removes the unit only from the resolved publication view. Reference
markers must use only the frozen reference_ids. Stable finding and edit IDs
must continue to identify the same issue across rounds.
"""

_EDITORIAL_REVIEWER_INSTRUCTION = """
Independently audit the complete frozen inventory, full-text view, user intent,
and every proposed cross-chapter edit. A final stop decision must bind the
exact inventory_digest and the exact current proposer artifact digest shown in
round_task.proposal_digests for `editorial-proposer`. Cover every proposed edit
ID exactly once by approving it or rejecting it with a non-empty reason.
Set each required `checked_*` audit field to true only after checking source
anchors, user intent, and the frozen reference set for every replacement.

Approve only edits that preserve the unit's source anchors, remain useful for
the user intent, use only frozen reference IDs, and do not introduce a new
scientific claim. Do not treat terminology, keyword, or thematic similarity as
sufficient redundancy. Preserve locally necessary definitions, distinct
derivations, different experimental connections, and different later
developments. There is no deletion quota. Use continue only with actionable
feedback when a further round can repair the proposal; otherwise stop and
explicitly reject every unsafe or unnecessary edit.
Use the verified source-evidence inputs named in the caller input_manifest to
inspect each edited unit's exact source anchors before completing the audit.
"""


def chapter_guide_proposer_instructions(
    version: str = CHAPTER_GUIDE_PROMPT_VERSION,
) -> str:
    if version in {CHAPTER_GUIDE_PROMPT_VERSION, HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V25, HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V24, HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V23}:
        instruction = (
            _GUIDE_CONTENT_INSTRUCTION
            + _GUIDE_RESEARCH_POLICY
            + _GUIDE_SOURCE_ACCESS_INSTRUCTION
            + _GUIDE_MATH_INSTRUCTION
            + _GUIDE_VERIFY_BEFORE_TRIMMING.replace(
                " A citation to the original document does\n"
                "not support an extension absent from that document.",
                "",
            )
            + _GUIDE_EXTERNAL_REFERENCE_POLICY
        )
        if version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V24:
            instruction += """

Complete evidence use in this first draft; do not defer citations to a reviewer.
The caller's prepared_references contains a generation-stage evidence plan.
Use relevant verified support when writing supplementary explanations, keeping
its limitations. For each retained externally supported explanation, add a nearby
[@N] marker and its actual title/source in this proposal's references array;
renumber markers to that array, not the source paper's bibliography or the plan.
Do not present unresolved planned claims as verified facts. Verify further with
available tools, derive them from supplied evidence, or omit unsupported additions.
Before returning, check every external claim has supporting evidence, every
citation has a matching reference, and every listed reference is used. An empty
bibliography is valid when the retained explanations need no external support.
"""
        if version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V25:
            instruction += """

Write a useful supplementary Companion in this initial generation, including
research and citations as part of writing it. A faithful paraphrase alone is
not sufficient when the reader would benefit from missing background. Identify
what the supplied text assumes rather than explains: definitions, omitted
reasoning, conditions of validity, connections to established methods, or a
comparison needed to understand the result. Choose additions for their teaching
value and the user's intent, not merely because the supplied text already covers
them. Familiarity with a topic does not establish that the source explains it.
For those additions requiring external support, use available authorized research
tools now, inspect the relevant content, and incorporate the supported explanation
with a nearby [@N] citation and matching title/source in references. Existing
bibliography entries are starting points for lookup, not evidence of having read
their content. Prefer arXiv IDs, then DOI IDs, then stable source URLs.
An empty result from one research provider does not establish that useful support
is unavailable. Try a simpler focused query or available native web search before
abandoning a useful addition; keep this lookup bounded and respect tool failures.
Finish the explanation, research, and bibliography in this same proposal; do not
leave missing background or sources for a later reviewer. If support cannot be
verified, narrow or omit the unsupported claim without inventing a source.
Use only references cited in retained explanations, with markers numbered against
this proposal's references array. There is no citation quota: an empty bibliography
is appropriate when useful additions genuinely require no external support.
"""
        if version == CHAPTER_GUIDE_PROMPT_VERSION:
            instruction = instruction.replace(_GUIDE_RESEARCH_POLICY, "")
            instruction += """

External research is a required part of this initial Companion generation,
independent of whether any later review is enabled. Before returning your first
proposal, perform a focused search for reliable external sources relevant to the
paper's concepts, methods, or interpretation using available authorized research
or native web tools. Do not skip this search because the supplied paper seems
self-contained, the topic is familiar, or you can paraphrase its explanations.
Choose useful background the paper assumes, definitions, omitted derivations,
conditions of validity, or comparisons that help the reader understand it.
Inspect relevant source content and integrate the supported background into the
Companion with nearby [@N] markers and matching title/source entries in references.
Prefer arXiv IDs, then DOI IDs, then stable URLs. Existing bibliography entries
are lookup candidates, not evidence that their content has been read.
If one provider returns no results, simplify the query or use available native
web search. Keep attempts bounded. Finish research and citation in this proposal;
do not wait for reviewer feedback to request or add references.
An empty references array is allowed only after unsuccessful lookup, no suitable
relevant source was found, or supporting content could not be verified (including
unavailable tools). In that case, briefly state the concrete limitation in the
chapter guide, in the target language, without claiming unperformed tool use.
Do not use "the original is sufficient" as a reason to omit the required search.
Never fabricate references or pad the bibliography: include only verified sources
actually used in substantive explanations. Number citations against this proposal's
references array. The number of later review rounds must not change these duties.
"""
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22:
        instruction = (
            _CHAPTER_GUIDE_INSTRUCTION
            + _GUIDE_VERIFY_BEFORE_TRIMMING
            + _GUIDE_EXTERNAL_REFERENCE_POLICY
        )
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21:
        instruction = _CHAPTER_GUIDE_INSTRUCTION + _GUIDE_VERIFY_BEFORE_TRIMMING
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20:
        instruction = _CHAPTER_GUIDE_INSTRUCTION
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19:
        instruction = _CHAPTER_GUIDE_INSTRUCTION_V19
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V18:
        instruction = _CHAPTER_GUIDE_INSTRUCTION_V18
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17:
        instruction = _CHAPTER_GUIDE_INSTRUCTION_V17
    elif version == HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16:
        instruction = _CHAPTER_GUIDE_INSTRUCTION_V16
    else:
        raise ValueError("unsupported chapter guide prompt contract")
    return _instruction_contract(
        version,
        instruction,
    )


def chapter_guide_reviewer_instructions(
    version: str = CHAPTER_GUIDE_REVIEW_PROMPT_VERSION,
) -> str:
    if version == CHAPTER_GUIDE_REVIEW_PROMPT_VERSION:
        instruction = (
            _CHAPTER_GUIDE_REVIEW_INSTRUCTION
            + _GUIDE_REVIEW_VERIFY_BEFORE_TRIMMING
            + _GUIDE_EXTERNAL_REFERENCE_POLICY
        )
    elif version == HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19:
        instruction = _CHAPTER_GUIDE_REVIEW_INSTRUCTION + _GUIDE_REVIEW_VERIFY_BEFORE_TRIMMING
    elif version == HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18:
        instruction = _CHAPTER_GUIDE_REVIEW_INSTRUCTION
    elif version == HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17:
        instruction = _CHAPTER_GUIDE_REVIEW_INSTRUCTION_V17
    elif version == HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16:
        instruction = _CHAPTER_GUIDE_REVIEW_INSTRUCTION_V16
    else:
        raise ValueError("unsupported chapter guide review prompt contract")
    return _instruction_contract(
        version,
        instruction,
    )


def editorial_proposer_instructions(
    version: str = EDITORIAL_PROPOSER_PROMPT_VERSION,
) -> str:
    if version != EDITORIAL_PROPOSER_PROMPT_VERSION:
        raise ValueError("unsupported editorial proposer prompt contract")
    return _instruction_contract(version, _EDITORIAL_PROPOSER_INSTRUCTION)


def editorial_reviewer_instructions(
    version: str = EDITORIAL_REVIEWER_PROMPT_VERSION,
) -> str:
    if version != EDITORIAL_REVIEWER_PROMPT_VERSION:
        raise ValueError("unsupported editorial reviewer prompt contract")
    return _instruction_contract(version, _EDITORIAL_REVIEWER_INSTRUCTION)


def author_identity_prompt(
    *,
    title: str,
    auto_candidates: Sequence[Mapping[str, Any]],
    block_access: Sequence[Mapping[str, Any]] = (),
    front_matter_evidence: Sequence[Mapping[str, Any]] = (),
    version: str = AUTHOR_IDENTITY_PROMPT_VERSION,
) -> str:
    if version not in {
        AUTHOR_IDENTITY_PROMPT_VERSION,
        HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3,
    }:
        raise ValueError("unsupported author identity prompt contract")
    evidence_instruction = (
        """
        All available author evidence is embedded in `front_matter_evidence`.
        Do not request a host action or attempt to read another file. If the
        embedded evidence is insufficient, return an empty, non-high-confidence
        result.
        """
        if version == AUTHOR_IDENTITY_PROMPT_VERSION
        else """
        Prefer the bounded front-matter line ranges in `block_access`. If they
        are insufficient, use a precise search or inspect a complete relevant
        chapter. Avoid reading the whole book when narrower evidence resolves
        the identity.
        """
    )
    payload = {
        "title": title,
        "auto_candidates": list(auto_candidates),
        "block_access": [dict(item) for item in block_access],
        "source_inputs": _source_input_manifest(),
    }
    if version == AUTHOR_IDENTITY_PROMPT_VERSION:
        payload["front_matter_evidence"] = [
            dict(item) for item in front_matter_evidence
        ]
    return _prompt(
        version,
        f"""
        Verify publication authorship from the supplied title, verified source
        inputs, and automatically parsed candidates with their bases. Author names are
        publication identity, not a constraint on Companion interpretation or
        creative form. Confirm or correct an automatic candidate when the
        supplied material supports it, or infer an author when there is no
        candidate only when the material makes the attribution very certain.
        Do not guess. Use high confidence only for a very certain attribution;
        at medium or low confidence, authors must be empty. Give the exact
        source anchors that support a high-confidence attribution. Explain the
        basis even when authors is empty. Never invent source block IDs.
        {evidence_instruction}
        Every anchor must be a real source block ID. If the
        inspected source does not establish authorship, return an empty,
        non-high-confidence result.
        """,
        payload,
    )


def _source_input_manifest(
    *,
    additional: Sequence[str] = (),
) -> dict[str, Any]:
    """Describe verified workspace inputs without embedding their content."""

    inputs = [
        "companion-source-index",
        *additional,
    ]
    return {
        "input_ids": inputs,
        "conditional_input_ids": [
            "companion-source when cache_relationship is fallback_only"
        ],
        "instructions": (
            "Inspect companion-source-index first. In direct mode, prefer the "
            "exact cache-only ac-document operations listed there and pass its "
            "cached document reference unchanged. For chapter tasks, use the "
            "task's block_access line ranges and selectors first. If those "
            "excerpts are insufficient, the agent may inspect the complete "
            "current chapter. Avoid reading the whole book when chapter-scoped "
            "or narrower access is enough. A verified text-only companion-source "
            "input is present only when cache_relationship is fallback_only. "
            "Never open image or media assets. The task payload is authoritative "
            "for chapter and block IDs and effective equation labels. Other named "
            "inputs are verified JSON files. In restricted or unknown mode, use "
            "an available text-only fallback rather than requesting a host turn "
            "solely to read the same source."
        ),
    }


def _prompt(
    version: str, instruction: str, payload: Mapping[str, Any]
) -> str:
    return (
        f"Contract: {version}\n\n"
        + " ".join(line.strip() for line in instruction.strip().splitlines())
        + "\n\nInput JSON:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _instruction_contract(version: str, instruction: str) -> str:
    return (
        f"Contract: {version}\n\n"
        + " ".join(line.strip() for line in instruction.strip().splitlines())
    )


__all__ = [
    "AUTHOR_IDENTITY_PROMPT_VERSION",
    "HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3",
    "AUTHOR_IDENTITY_SCHEMA",
    "CHAPTER_GUIDE_PROMPT_VERSION",
    "CHAPTER_GUIDE_PROPOSAL_SCHEMA",
    "CHAPTER_GUIDE_REVIEW_AUDIT_SCHEMA",
    "CHAPTER_GUIDE_REVIEW_PROMPT_VERSION",
    "EDITORIAL_PROPOSER_PROMPT_VERSION",
    "EDITORIAL_REVIEWER_PROMPT_VERSION",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V18",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V25",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V24",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V23",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21",
    "HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20",
    "HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16",
    "HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17",
    "HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19",
    "HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18",
    "author_identity_prompt",
    "chapter_guide_proposer_instructions",
    "chapter_guide_reviewer_instructions",
    "editorial_proposer_instructions",
    "editorial_reviewer_instructions",
]
