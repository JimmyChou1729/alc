import pytest
from alc_ocr_proofread.inline_structure import apply_proposal


def proposal(before, after, anchor="p1"):
    return {
        "proposal_id": "fix1",
        "anchor_id": anchor,
        "before_html": before,
        "after": after,
        "reason": "Printed source",
    }


BUNDLE = {
    "entries": [
        {"page_number": 1, "source_ids": ["p1"]},
        {"page_number": 2, "source_ids": ["p2"]},
    ]
}


@pytest.mark.parametrize(
    "before,after",
    [
        ('<math alttext="P_n"></math>1', [{"kind": "math", "value": "P_{n-1}"}]),
        (
            "dimension  of",
            [
                {"kind": "text", "value": "dimension "},
                {"kind": "math", "value": "D"},
                {"kind": "text", "value": " of"},
            ],
        ),
        ("&lt;sup&gt;2&lt;/sup&gt;", [{"kind": "sup", "value": "2"}]),
        (
            '<math alttext="x"></math>',
            [{"kind": "math", "value": "x"}, {"kind": "text", "value": "."}],
        ),
    ],
)
def test_controlled_inline_shapes(before, after):
    source = '<p id="p1">Before ' + before + ' after.</p><p id="p2">Other page</p>'
    result = apply_proposal(source, BUNDLE, 1, proposal(before, after))
    assert result.startswith('<p id="p1">Before ')
    assert result.endswith(' after.</p><p id="p2">Other page</p>')
    assert result != source


@pytest.mark.parametrize(
    "source,fix,page",
    [
        ('<p id="p1">text</p>', proposal("text", [{"kind": "img", "value": "x"}]), 1),
        (
            '<p id="p1">text</p><p id="p1">text</p>',
            proposal("text", [{"kind": "sup", "value": "1"}]),
            1,
        ),
        (
            '<p id="p2">text</p>',
            proposal("text", [{"kind": "sup", "value": "1"}], "p2"),
            1,
        ),
        (
            '<p id="p1"><math alttext="x"></math>tail</p>',
            proposal("x", [{"kind": "sup", "value": "1"}]),
            1,
        ),
        (
            '<p id="p1"><span id="keep">text</span></p>',
            proposal('<span id="keep">text</span>', [{"kind": "sup", "value": "1"}]),
            1,
        ),
    ],
)
def test_unsafe_shapes_rejected(source, fix, page):
    with pytest.raises(ValueError):
        apply_proposal(source, BUNDLE, page, fix)


def test_neutral_schema_contract_matches():
    from ac_document.pdf_inline import INLINE_PROPOSAL_SCHEMA
    from alc_ocr_proofread.inline_structure import PROPOSAL_SCHEMA

    assert PROPOSAL_SCHEMA == INLINE_PROPOSAL_SCHEMA


def test_markup_in_typed_value_is_inert_text():
    result = apply_proposal(
        '<p id="p1">text</p>',
        BUNDLE,
        1,
        proposal("text", [{"kind": "text", "value": "<script>x</script>"}]),
    )
    assert "&lt;script&gt;x&lt;/script&gt;" in result
    assert "<script>" not in result
