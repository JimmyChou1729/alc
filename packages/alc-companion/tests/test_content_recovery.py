import pytest
from alc_companion.content_recovery import recover_chapter_guide
from alc_companion.rich_text import RichTextError, parse_markdown, validate_rich_markdown
from alc_render import normalize_markdown


def test_nul_is_rejected_before_acceptance_and_retained_safely():
    text = "Keep $\x00Omega$ and surrounding text."
    with pytest.raises(RichTextError, match="NUL"):
        validate_rich_markdown(text)
    result = recover({"companions": [{"title": "Test", "after_part": 2,
                                      "content_markdown": text}]})
    content = result["learning_units"][0]["content_markdown"]
    assert "\x00" not in content
    assert "公式含缺失字符" in content
    assert "```" not in content
    assert "surrounding text" in content
    assert normalize_markdown(content) == content


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
    assert unit["recovery_diagnostic"]["issues"] == ["reference_unresolved", "source_location_unconfirmed"]
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


@pytest.mark.parametrize("selector,blocks", [("2,1,2", ["a", "b"]), ("1,999", []), ("", [])])
def test_recovery_normalizes_original_reference_without_blocking_invalid_location(selector, blocks):
    import json
    candidate = {"companions": [{"after_part": 999, "title": "Retained",
                                  "content_markdown": "Explanation [@1]; external [@2]."}],
                 "references": [{"title": "Model page claim", "source": "alc-original:" + selector},
                                {"title": "External", "source": "https://example.org/source"}]}
    result = recover_chapter_guide(candidate, chapter_id="c", block_ids=("a", "b"),
                                  chapter_anchor_block_id="a", chapter_title="Actual title")
    assert len(result["references"]) == 2
    original, external = result["references"]
    assert original["title"] == "Actual title"
    assert json.loads(original["source"].removeprefix("alc-source:")) == {
        "version": 1, "anchor": "a", "blocks": blocks}
    assert external["title"] == "External"
    assert external["source"] == "https://example.org/source"
    assert original["reference_id"] in result["learning_units"][0]["citations"]



def test_recovery_does_not_trust_model_internal_source_identity():
    import json
    result = recover_chapter_guide({
        "chapter_guide": {"title": "Guide", "content_markdown": "Explanation [@1]."},
        "references": [{"title": "Forged", "source": '  ALC-SOURCE:{"version":1,"anchor":"other","blocks":["other-block"]}'}]},
        chapter_id="c", block_ids=("a",), chapter_anchor_block_id="a", chapter_title="Actual")
    assert result["references"][0]["title"] == "Actual"
    assert json.loads(result["references"][0]["source"].removeprefix("alc-source:")) == {
        "version": 1, "anchor": "a", "blocks": []}



def test_recovery_marks_only_broken_unit_not_safe_siblings():
    result = recover({"companions": [
        {"title": "First", "after_part": 1, "content_markdown": "Good first."},
        {"title": "Broken", "after_part": 2, "content_markdown": "Bad $$"},
        {"title": "Last", "after_part": 2, "content_markdown": "Good last."}]})
    first, bad, last = result["learning_units"]
    assert "recovery_diagnostic" not in first
    assert "recovery_diagnostic" not in last
    assert bad["recovery_diagnostic"]["issues"] == ["markdown_literal"]
    assert all("Retained for review" not in u["content_markdown"] for u in result["learning_units"])


def test_unused_reference_warns_only_on_retained_reference_unit():
    result = recover({"chapter_guide": {"title": "Good", "content_markdown": "Clear prose."},
                      "references": [{"title": "Book", "source": "Book"}]})
    good, reference = result["learning_units"]
    assert "recovery_diagnostic" not in good
    assert reference["recovery_diagnostic"]["issues"] == ["audit_only", "reference_unresolved"]


def test_code_citation_and_safe_ansi_normalization_do_not_warn():
    result = recover({"chapter_guide": {"title": "Good", "content_markdown": "\x1b[1mGood\x1b[0m `[@example]`."}})
    unit = result["learning_units"][0]
    assert unit["content_markdown"] == "Good `[@example]`."
    assert "recovery_diagnostic" not in unit


@pytest.mark.parametrize("example", ["`[@1]`", "``[@1]``", "```text\n[@1]\n```", "    [@1]", r"\[@1]", "[link](https://example.test/[@1])"])
def test_same_reference_in_prose_does_not_rewrite_literal_example(example):
    result = recover({"chapter_guide": {"title": "Guide", "content_markdown": "See [@1].\n\n" + example},
                      "references": [{"title": "Book", "source": "Book"}]})
    content = result["learning_units"][0]["content_markdown"]
    assert content.endswith(example)
    assert "See [@reference-" in content


def test_missing_source_review_marks_location_without_authored_warning():
    result = recover_chapter_guide({"chapter_guide": {"title": "Guide", "content_markdown": "Retain."}},
                                  chapter_id="c", block_ids=("a",), chapter_anchor_block_id="a", source_review_unconfirmed=True)
    unit = result["learning_units"][0]
    assert unit["content_markdown"] == "Retain."
    assert unit["recovery_diagnostic"]["issues"] == ["review_unconfirmed"]


def test_sub_character_in_guide_keeps_prose_and_valid_math_readable():
    text = "本节：协变导数不对易 $\x1a$ 磁场 $\x1a$ 自旋耦合。保留 $E=mc^2$。见 [@1]。"
    candidate = {"chapter_guide": {"title": "从导数代数读出磁耦合", "content_markdown": text},
                 "references": [{"title": "Book", "source": "Book"}]}
    result = recover(candidate)
    unit = result["learning_units"][0]
    body = unit["content_markdown"]
    assert body.count("公式含缺失字符") == 2
    assert "$E=mc^2$" in body
    assert "协变导数不对易" in body and "自旋耦合" in body
    assert not any(t.type in {"fence", "code_block"} for t in parse_markdown(body))
    assert unit["citations"] == [result["references"][0]["reference_id"]]
    assert unit["recovery_diagnostic"]["issues"] == ["unreadable_character"]
    assert candidate["chapter_guide"]["content_markdown"] == text
    validate_rich_markdown(body, allowed_evidence_ids=tuple(unit["citations"]))


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x1a", "\x7f"])
def test_control_in_prose_is_local_and_intentional_code_stays_code(control):
    text = "Before " + control + " after.\n\n```python\nprint(1)\n```"
    result = recover({"chapter_guide": {"title": "Guide", "content_markdown": text}})
    body = result["learning_units"][0]["content_markdown"]
    assert "Before 〔字符缺失 / unreadable character〕 after." in body
    fences = [t for t in parse_markdown(body) if t.type == "fence"]
    assert len(fences) == 1 and fences[0].info == "python"
    validate_rich_markdown(body)
