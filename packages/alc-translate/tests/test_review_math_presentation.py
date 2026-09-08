import pytest

from alc_translate.workflow import _apply_review, TranslationWorkflowError


def block(text):
    from alc_translate.source import _markdown_math_spans

    spans = []
    cursor = 0
    for start, end, tex in _markdown_math_spans(text):
        spans.append(
            {"kind": "text", "start": cursor, "end": start, "text": text[cursor:start]}
        )
        spans.append(
            {
                "kind": "math",
                "start": start,
                "end": end,
                "text": text[start:end],
                "tex": tex,
                "source": text[start:end],
            }
        )
        cursor = end
    spans.append(
        {"kind": "text", "start": cursor, "end": len(text), "text": text[cursor:]}
    )
    return {
        "block_id": "p",
        "kind": "paragraph",
        "payload": {"text": text, "inline_spans": spans},
    }


def apply(original, candidate):
    return _apply_review(
        {
            "translation_patches": [{"block_id": "p", "replacement": candidate}],
            "summary": "reviewed",
        },
        [{"block_id": "p", "text": original}],
        [block(original)],
    )[0]["text"]


def test_review_keeps_literal_gamma_and_accepts_prose_correction():
    original = r"其所有 gamma 值都远在 -0.25 < $\gamma$ < 0.25 范围内。"
    candidate = r"其所有 $\gamma$ 值都处于 -0.25 < $\gamma$ < 0.25 范围内。"
    assert (
        apply(original, candidate)
        == r"其所有 gamma 值都处于 -0.25 < $\gamma$ < 0.25 范围内。"
    )


@pytest.mark.parametrize("literal", ["1.0", "r < 0.4", "alpha", "x"])
def test_review_restores_exact_literal_math_wrapping(literal):
    tex = r"\alpha" if literal == "alpha" else literal
    assert apply(f"值为 {literal}。", f"值为 ${tex}$。") == f"值为 {literal}。"


@pytest.mark.parametrize(
    "original,candidate",
    [
        ("值为 1.0。", "值为 $2.0$。"),
        ("值为 alpha。", r"值为 $\gamma$。"),
        (r"值为 $\gamma$。", r"值为 $\alpha$。"),
        (r"值为 $\gamma$。", "值为 gamma。"),
        ("值为 a b。", "值为 $ab$。"),
        ("值为 x。", "值为 $x^2$。"),
    ],
)
def test_review_does_not_accept_changed_or_removed_math(original, candidate):
    with pytest.raises(TranslationWorkflowError):
        apply(original, candidate)
