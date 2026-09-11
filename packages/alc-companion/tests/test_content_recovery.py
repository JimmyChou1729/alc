import pytest
from alc_companion.content_recovery import recover_chapter_guide
from alc_companion.rich_text import parse_markdown, validate_rich_markdown


def recover(candidate):
    return recover_chapter_guide(candidate, chapter_id="c", block_ids=("a", "b"),
                                 chapter_anchor_block_id="a", section_block_ids=("a",))


@pytest.mark.parametrize("text", ["before $$broken", "<script>alert(1)</script>", "```\nraw\n```\n$$"])
def test_unrenderable_candidate_is_visible_literal_text(text):
    result = recover({"companions": [{"title": "Test", "after_part": 2, "content_markdown": text}]})
    unit = result["learning_units"][0]
    tokens = parse_markdown(unit["content_markdown"])
    assert any(t.type == "fence" and text in t.content for t in tokens)
    assert unit["anchor_block_ids"] == ["b"]


def test_unknown_citations_and_locations_do_not_fabricate_links():
    result = recover({"companions": [{"title": "Test", "after_part": 999, "content_markdown": "Keep this [@9]."}]})
    unit = result["learning_units"][0]
    assert unit["placement"] == "chapter"
    assert "Source location unconfirmed" in unit["content_markdown"]
    assert "Keep this" in unit["content_markdown"]
    assert validate_rich_markdown(unit["content_markdown"]) == ()


def test_valid_units_and_reference_identity_survive_bad_siblings():
    result = recover({"companions": [
        {"title": "Good", "after_part": 2, "content_markdown": "Good [@2]."},
        {"title": "Bad", "after_part": 1, "content_markdown": "Bad $$"}],
        "references": [{"oops": "bad"}, {"title": "Book", "source": "Book source"}]})
    good = result["learning_units"][0]
    assert "Good" in good["content_markdown"]
    assert good["citations"] == [result["references"][0]["reference_id"]]
    assert any('"oops"' in u["content_markdown"] for u in result["learning_units"])


@pytest.mark.parametrize("candidate", ["raw text", {"companions": "raw text"}, {"companions": [{"unknown": "retain me"}]}])
def test_malformed_shapes_keep_original_content(candidate):
    result = recover(candidate)
    assert result["learning_units"]
    for unit in result["learning_units"]:
        validate_rich_markdown(unit["content_markdown"])


def test_nonlist_references_are_not_lost_with_valid_text():
    result = recover({"chapter_guide": {"title": "Keep", "content_markdown": "Valid text"},
                      "references": {"title": "Retain reference"}})
    assert any("Retain reference" in u["content_markdown"] for u in result["learning_units"])
