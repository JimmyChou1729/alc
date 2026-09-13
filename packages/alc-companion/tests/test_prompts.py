from __future__ import annotations

from alc_companion.prompts import (
    AUTHOR_IDENTITY_PROMPT_VERSION,
    HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3,
    HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16,
    HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17,
    HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16,
    HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17,
    author_identity_prompt,
    chapter_guide_proposer_instructions,
    chapter_guide_reviewer_instructions,
)
from alc_companion.request_contracts import CompanionGenerationRecipe


def test_author_identity_prompt_embeds_bounded_front_matter_evidence() -> None:
    prompt = author_identity_prompt(
        title="A paper",
        auto_candidates=[],
        block_access=[],
        front_matter_evidence=[
            {
                "block_id": "block-author",
                "text": "Ada Example, Example Institute.",
            }
        ],
    )

    assert AUTHOR_IDENTITY_PROMPT_VERSION.endswith(".v4")
    assert '"block_id":"block-author"' in prompt
    assert '"text":"Ada Example, Example Institute."' in prompt
    assert "Do not request a host action" in prompt


def test_v3_author_identity_prompt_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        author_identity_prompt=HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3
    )
    prompt = author_identity_prompt(
        title="Historical paper",
        auto_candidates=[],
        block_access=[],
        front_matter_evidence=[
            {"block_id": "ignored", "text": "new-only evidence"}
        ],
        version=recipe.author_identity_prompt,
    )

    assert HISTORICAL_AUTHOR_IDENTITY_PROMPT_VERSION_V3 in prompt
    assert "front_matter_evidence" not in prompt


def test_guide_prompts_treat_paratext_as_model_judgment() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    assert "current source segment" in proposer
    assert "current real chapter" not in proposer
    assert "current source segment" in reviewer
    assert "current real chapter" not in reviewer
    for prompt in (proposer, reviewer):
        assert "publication metadata" in prompt
        assert (
            "prefer `chapter_guide: null`" in prompt
            or "prefer a null guide" in prompt
        )
        assert "title keywords" in prompt
        assert "preface" in prompt
        assert "cross-segment reading route" in prompt
        assert "specific reading action or understanding increment" in prompt


def test_guide_prompts_bind_local_section_numbers() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    for prompt in (proposer, reviewer):
        assert "section_number" in prompt
        assert "source heading" in prompt or "source-heading" in prompt
        assert "sections" in prompt


def test_guide_prompts_use_the_host_request_schema_field() -> None:
    for prompt in (
        chapter_guide_proposer_instructions(),
        chapter_guide_reviewer_instructions(),
    ):
        assert "host_request.request_id" in prompt
        assert "host_request.id" not in prompt


def test_current_guide_prompts_require_canonical_display_math() -> None:
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()

    for prompt in (proposer, reviewer):
        assert "display-math" in prompt or "display math" in prompt
        assert "separate lines" in prompt


def test_v17_guide_prompt_recipe_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17,
        chapter_guide_review_prompt=(
            HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17
        ),
    )

    proposer = chapter_guide_proposer_instructions(
        recipe.chapter_guide_prompt
    )
    reviewer = chapter_guide_reviewer_instructions(
        recipe.chapter_guide_review_prompt
    )
    assert HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V17 in proposer
    assert HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V17 in reviewer
    assert "display-math" not in proposer
    assert "display-math" not in reviewer


def test_historical_guide_prompt_recipe_remains_decodable() -> None:
    recipe = CompanionGenerationRecipe(
        chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16,
        chapter_guide_review_prompt=(
            HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16
        ),
    )

    proposer = chapter_guide_proposer_instructions(
        recipe.chapter_guide_prompt
    )
    reviewer = chapter_guide_reviewer_instructions(
        recipe.chapter_guide_review_prompt
    )
    assert HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V16 in proposer
    assert HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V16 in reviewer
    assert "numeral printed in the source heading" not in proposer
    assert "source-heading numerals" not in reviewer


def test_source_citations_preserve_v18_recipe() -> None:
    historical = "alc.companion.chapter-learning-prompt.v18"
    recipe = CompanionGenerationRecipe(chapter_guide_prompt=historical)
    old = chapter_guide_proposer_instructions(recipe.chapter_guide_prompt)
    current = chapter_guide_proposer_instructions()
    assert "Make the basis of substantive explanations traceable" not in old
    assert "separate lines" in old
    assert "External research is a required part" in current
    assert "Make the basis of substantive explanations traceable" not in current


def test_original_reference_prompt_v20_preserves_v19_contract():
    from alc_companion.prompts import HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19
    from alc_companion.request_contracts import CompanionGenerationRecipe
    current = chapter_guide_proposer_instructions()
    previous = chapter_guide_proposer_instructions(HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19)
    assert "alc-original:1-14,20" in chapter_guide_proposer_instructions("alc.companion.chapter-learning-prompt.v20")
    assert "alc-original:" not in previous
    assert "actual title and inspected" in previous
    assert CompanionGenerationRecipe(chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V19).chapter_guide_prompt.endswith("v19")


def test_historical_v25_preserves_optional_research_policy():
    prompt = chapter_guide_proposer_instructions("alc.companion.chapter-learning-prompt.v25")
    text = " ".join(prompt.split())
    expected = """Research when it materially improves the Companion. Prefer a source already
available through the shared paper cache. External reference sources may be
used when needed. There is no reference-count limit, and no minimum. If
acquisition is required, use any currently available and authorized
capability-matching tool; do not assume one exists or insist on
authorization that was not granted."""
    assert " ".join(expected.split()) in text
    assert 'Make the basis of substantive explanations traceable.' not in prompt
    assert 'the supplied material is sufficient' not in prompt
    assert 'even when the explanation seems familiar' not in prompt
    assert 'Use only the verified document' not in prompt
    assert 'alc-original:' not in prompt
    historical = chapter_guide_proposer_instructions("alc.companion.chapter-learning-prompt.v18")
    assert 'External reference sources may be used when needed' not in " ".join(historical.split())


def test_verify_before_trimming_is_new_contract_only():
    from alc_companion.prompts import (
        HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20,
        HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18,
    )
    proposer = chapter_guide_proposer_instructions()
    reviewer = chapter_guide_reviewer_instructions()
    assert 'first try to verify the specific claim' in proposer
    assert 'no usable support' in proposer
    assert 'does not support an extension absent' not in proposer
    assert 'do not offer immediate deletion as an equal first choice' in reviewer
    old = chapter_guide_proposer_instructions(HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20)
    old_review = chapter_guide_reviewer_instructions(HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18)
    assert 'first try to verify the specific claim' not in old
    assert 'do not offer immediate deletion as an equal first choice' not in old_review
    CompanionGenerationRecipe(chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V20,
        chapter_guide_review_prompt=HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V18)


def test_external_reference_policy_preserves_existing_contracts():
    from alc_companion.prompts import (
        HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21,
        HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19,
    )
    for render in (chapter_guide_proposer_instructions, chapter_guide_reviewer_instructions):
        prompt = " ".join(render().split())
        assert "Prefer arXiv IDs, then DOI IDs" in prompt
        assert "use a stable source URL when neither applies" in prompt
        assert "Read the relevant content before citing it" in prompt
    old = chapter_guide_proposer_instructions(HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21)
    old_review = chapter_guide_reviewer_instructions(HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19)
    assert "Prefer arXiv IDs" not in old
    assert "Prefer arXiv IDs" not in old_review
    CompanionGenerationRecipe(
        chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V21,
        chapter_guide_review_prompt=HISTORICAL_CHAPTER_GUIDE_REVIEW_PROMPT_VERSION_V19,
    )


def test_current_prompt_omits_original_reference_guidance_without_prohibition():
    from alc_companion.prompts import (
        HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22,
        _GUIDE_ORIGINAL_REFERENCE_FORMAT,
    )
    old = chapter_guide_proposer_instructions(HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22)
    current = chapter_guide_proposer_instructions("alc.companion.chapter-learning-prompt.v23")
    normalized = lambda text: " ".join(text.split())
    expected = normalized(old.split("\n\n", 1)[1]).replace(
        normalized(_GUIDE_ORIGINAL_REFERENCE_FORMAT), ""
    ).replace(
        "A citation to the original document does not support an extension absent from that document.", ""
    )
    assert normalized(current.split("\n\n", 1)[1]) == normalized(expected)
    assert "alc-original" not in current
    assert "supplied-original reference" not in current
    CompanionGenerationRecipe(chapter_guide_prompt=HISTORICAL_CHAPTER_GUIDE_PROMPT_VERSION_V22)


def test_initial_prompt_requires_research_independent_of_review():
    from alc_companion.prompts import chapter_guide_proposer_instructions
    prompt = chapter_guide_proposer_instructions()
    assert 'External research is a required part' in prompt
    assert 'Research when it materially improves' not in prompt
    assert 'do not wait for reviewer feedback' in prompt
    assert 'briefly state the concrete limitation' in prompt
    assert 'prepared_references' not in prompt
