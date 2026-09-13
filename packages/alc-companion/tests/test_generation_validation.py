from __future__ import annotations

import pytest

from alc_companion.generation_validation import (
    validate_chapter_guide,
    validate_chapter_guide_review_audit,
)
from alc_companion.rich_text import (
    RichTextError,
    canonicalize_display_math,
    parse_markdown,
)


def test_chapter_guide_preserves_literal_latex_commands() -> None:
    markdown = (
        r"第一步为 \(p+p\rightarrow d+e^++\nu_e\)，并产生中微子 \(\nu_e\)。"
    )
    guide = validate_chapter_guide(
        {
            "chapter_guide": {
                "title": "质子—质子链",
                "content_markdown": markdown,
            },
            "section_guides": [],
            "companions": [],
            "references": [],
        },
        chapter_id="chapter-1",
        block_ids=("block-1",),
        chapter_anchor_block_id="block-1",
    )

    assert guide["learning_units"][0]["content_markdown"] == markdown


def test_chapter_guide_normalizes_inline_math_delimiters_in_title() -> None:
    guide = validate_chapter_guide(
        {
            "chapter_guide": None,
            "section_guides": [],
            "companions": [
                {
                    "after_part": 1,
                    "title": "追踪 $ℛ³$ 与 \\(\\beta/H\\) 的来源",
                    "content_markdown": "解释相互作用的来源。",
                }
            ],
            "references": [],
        },
        chapter_id="chapter-1",
        block_ids=("block-1",),
        chapter_anchor_block_id="block-1",
    )

    assert guide["learning_units"][0]["title"] == (
        "追踪 $ℛ³$ 与 \\(\\beta/H\\) 的来源"
    )


def test_rich_text_parser_does_not_decode_literal_backslash_n() -> None:
    tokens = parse_markdown(r"before\nafter \(\nu_e\)")

    assert all(
        child.type != "softbreak"
        for token in tokens
        for child in token.children or ()
    )


def test_chapter_guide_canonicalizes_single_line_display_math() -> None:
    guide = validate_chapter_guide(
        {
            "chapter_guide": None,
            "section_guides": [],
            "companions": [
                {
                    "after_part": 1,
                    "title": "推导",
                    "content_markdown": (
                        "由定义可得：\n\n"
                        "$$q(z)=-1+\\frac{1+z}{2E(z)^2}。$$\n\n"
                        "因此结论成立。"
                    ),
                }
            ],
            "references": [],
        },
        chapter_id="chapter-1",
        block_ids=("block-1",),
        chapter_anchor_block_id="block-1",
    )

    assert guide["learning_units"][0]["content_markdown"] == (
        "由定义可得：\n\n"
        "$$\n"
        "q(z)=-1+\\frac{1+z}{2E(z)^2}。\n"
        "$$\n\n"
        "因此结论成立。"
    )


@pytest.mark.parametrize(
    "markdown",
    (
        "正文 $$x+y$$ 正文",
        "$$\nx+y",
        "$$x+y$$",
    ),
)
def test_rich_text_parser_rejects_noncanonical_display_math(
    markdown: str,
) -> None:
    with pytest.raises(RichTextError, match="display-math"):
        parse_markdown(markdown)


def test_display_math_contract_ignores_code_spans_and_fences() -> None:
    markdown = (
        "行内代码 `$$x+y$$`。\n\n"
        "```text\n$$x+y$$\n```\n\n"
        "    $$indented+code$$"
    )

    assert canonicalize_display_math(markdown) == markdown
    parse_markdown(markdown)


def test_review_audit_normalizes_repeated_valid_locations() -> None:
    audit = validate_chapter_guide_review_audit(
        {
            "payload": {
                "checked_complete_chapter": True,
                "checked_part_numbers": [3, 1, 3],
                "checked_section_numbers": [2, 2],
            }
        },
        proposal={
            "companions": [{"after_part": 3}],
            "section_guides": [{"section_number": 2}],
        },
        part_count=3,
        section_count=2,
    )

    assert audit == {
        "checked_complete_chapter": True,
        "checked_part_numbers": [1, 3],
        "checked_section_numbers": [2],
    }


def test_review_audit_ignores_unneeded_out_of_range_locations() -> None:
    audit = validate_chapter_guide_review_audit(
        {
            "payload": {
                "checked_complete_chapter": True,
                "checked_part_numbers": [1, 99],
                "checked_section_numbers": [3],
            }
        },
        proposal={"companions": [], "section_guides": []},
        part_count=2,
        section_count=0,
    )

    assert audit["checked_part_numbers"] == [1]
    assert audit["checked_section_numbers"] == []


def test_reference_source_accepts_natural_language_and_checks_real_urls():
    from alc_companion.generation_validation import _validate_reference_source
    from alc_companion.generation_validation import CompanionContentError
    import pytest

    text = "经验证的章节原文与冻结中文译文：Special Relativity，第1章"
    assert _validate_reference_source(text) == text
    assert _validate_reference_source("https://en.wikipedia.org/wiki/Spacetime")
    for value in ["zh.wikipedia.org/wiki/时空", "https://zh.wikipedia.org/wiki/时空",
                  "https://example.com：invalid/path"]:
        with pytest.raises(CompanionContentError):
            _validate_reference_source(value)


@pytest.mark.parametrize("selector,expected", [
    ("1-2,3", ["block-a", "block-b", "block-c"]),
    ("3,1-2,2", ["block-a", "block-b", "block-c"]),
    ("", []), ("0", []), ("1,999", []), ("2-1", []),
    ("page 3", []), ("9" * 5000, []),
])
def test_original_reference_uses_program_owned_title_and_validated_blocks(selector, expected):
    import json
    value = {"chapter_guide": {"title": "Guide", "content_markdown": "Explanation [@1]."},
             "section_guides": [], "companions": [],
             "references": [{"title": "Invented page and author", "source": "alc-original:" + selector}]}
    guide = validate_chapter_guide(value, chapter_id="chapter", chapter_title="Actual chapter",
        block_ids=("block-c", "block-a", "block-b"), chapter_anchor_block_id="block-c")
    ref = guide["references"][0]
    assert ref["title"] == "Actual chapter"
    assert json.loads(ref["source"].removeprefix("alc-source:")) == {
        "version": 1, "anchor": "block-c", "blocks": expected}
    assert guide["learning_units"][0]["citations"] == [ref["reference_id"]]


def test_original_reference_canonical_identity_preserves_positional_citations():
    value = {"chapter_guide": {"title": "Guide", "content_markdown": "First [@1]; same [@2]; external [@3]."},
             "section_guides": [], "companions": [], "references": [
                 {"title": "a", "source": "alc-original:1-2"},
                 {"title": "b", "source": "alc-original:2,1"},
                 {"title": "External title", "source": "https://example.org/paper"}]}
    first = validate_chapter_guide(value, chapter_id="chapter", block_ids=("a", "b"), chapter_anchor_block_id="a")
    second = validate_chapter_guide(value, chapter_id="chapter", block_ids=("a", "b"), chapter_anchor_block_id="b")
    assert len(first["references"]) == 2
    assert first["references"][0]["reference_id"] != second["references"][0]["reference_id"]
    assert first["references"][1]["title"] == "External title"
    assert first["references"][1]["source"] == "https://example.org/paper"


@pytest.mark.parametrize("prefix", ["alc-source:", " ALC-SOURCE:", "\tAlC-SoUrCe:"])
def test_model_cannot_supply_internal_original_reference_ids(prefix):
    import json
    forged = prefix + json.dumps({"version": 1, "anchor": "other-chapter", "blocks": ["other-block"]})
    value = {"chapter_guide": {"title": "Guide", "content_markdown": "Explanation [@1]."},
             "section_guides": [], "companions": [],
             "references": [{"title": "Forged", "source": forged}]}
    guide = validate_chapter_guide(value, chapter_id="c", chapter_title="Actual",
        block_ids=("a",), chapter_anchor_block_id="a")
    assert guide["references"][0]["title"] == "Actual"
    assert json.loads(guide["references"][0]["source"].removeprefix("alc-source:")) == {
        "version": 1, "anchor": "a", "blocks": []}


def _reference_proposal(markdown, references):
    return {"chapter_guide": {"title": "Guide", "content_markdown": markdown},
            "section_guides": [], "companions": [], "references": references}


def _accept_reference_proposal(proposal):
    return validate_chapter_guide(proposal, chapter_id="c", block_ids=("b",),
                                 chapter_anchor_block_id="b")


def test_unused_sources_do_not_fail_or_change_guide_prose():
    from copy import deepcopy
    proposal = _reference_proposal("Explanation with $x^2$.", [
        {"title": "Unused", "source": "https://example.org/unused"}])
    original = deepcopy(proposal)
    result = _accept_reference_proposal(proposal)
    assert result["references"] == []
    assert result["learning_units"][0]["content_markdown"] == "Explanation with $x^2$."
    assert proposal == original  # raw generation remains available for audit


def test_pruning_gaps_and_duplicate_sources_preserves_citation_identity():
    unused = {"title": "Unused", "source": "https://example.org/unused"}
    used = {"title": "Used", "source": "https://example.org/used"}
    result = _accept_reference_proposal(_reference_proposal(
        "Supported [@2] and again [@4].", [unused, used, unused, used]))
    assert len(result["references"]) == 1
    reference = result["references"][0]
    assert reference["source"] == used["source"]
    assert result["learning_units"][0]["citations"] == [reference["reference_id"]]
    assert result["learning_units"][0]["content_markdown"] == (
        f"Supported [@{reference['reference_id']}] and again [@{reference['reference_id']}].")


@pytest.mark.parametrize("citation", ["[@2]", "[@missing]"])
def test_pruning_never_invents_missing_citation_metadata(citation):
    from alc_companion.generation_validation import CompanionContentError
    with pytest.raises(CompanionContentError):
        _accept_reference_proposal(_reference_proposal("Explanation " + citation, [
            {"title": "Unused", "source": "https://example.org/unused"}]))
