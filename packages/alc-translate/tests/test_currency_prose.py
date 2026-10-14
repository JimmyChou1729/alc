from __future__ import annotations

from pathlib import Path

import pytest
from ac_document import AcDocumentService
from alc_translate.atoms import (
    assemble_text_slot_translation,
    protected_atom_plan,
    text_slot_ids,
)
from alc_translate.source import (
    _escape_currency_dollars,
    _markdown_math_spans,
    resolve_translation_source,
    source_blocks,
    source_identity,
    validate_translation_text,
)


@pytest.mark.parametrize(
    ("source", "translation"),
    [
        ("Spend $30, $50, or even $100.", "花费 $30、$50，甚至 $100。"),
        (
            "At $0.015 per article on Google Cloud, it would cost $30,000.",
            "按每篇 $0.015 计算，总费用为 $30,000。",
        ),
        ("Prices: $30,$50,$100.", "价格为 $30、$50、$100。"),
    ],
)
def test_html_currency_remains_translatable_prose(
    tmp_path: Path, source: str, translation: str
) -> None:
    path = tmp_path / "paper.html"
    original = f"<article><p>{source}</p></article>".encode()
    path.write_bytes(original)
    parsed = resolve_translation_source(
        AcDocumentService(cache_root=tmp_path / "cache"), path
    )
    block, = source_blocks(parsed)
    plan = protected_atom_plan(block)
    assert plan["atoms"] == []
    assert source_identity(block)["equations"] == []
    slot, = text_slot_ids(block)
    rendered, _ = assemble_text_slot_translation(block, {slot: translation})
    assert rendered.replace(r"\$", "$") == translation
    assert rendered.count(r"\$") == translation.count("$")
    validate_translation_text(rendered, block)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("text", "formulas"),
    [
        ("Spend $30 and $x$ afterwards.", ["x"]),
        ("Spend $30,$50 and solve $2x+1$.", ["2x+1"]),
        (r"Pay \$30, \$50 and solve $x$.", ["x"]),
        (r"$2$ and $30$ and $x>\mbox{$1/2$}$", ["2", "30", r"x>\mbox{$1/2$}"]),
        (r"\(2x\) and $$30$$ and \[x=2\]", ["2x", "30", "x=2"]),
    ],
)
def test_currency_detection_preserves_math(text: str, formulas: list[str]) -> None:
    assert [tex for _, _, tex in _markdown_math_spans(text)] == formulas
    escaped = _escape_currency_dollars(text)
    assert [tex for _, _, tex in _markdown_math_spans(escaped)] == formulas
    assert _escape_currency_dollars(escaped) == escaped


def test_currency_serialization_preserves_code_and_link_destinations() -> None:
    text = "Price $30; `$50` and [price](https://example.test/$100)."
    assert _escape_currency_dollars(text) == (
        r"Price \$30; `$50` and [price](https://example.test/$100)."
    )


@pytest.mark.parametrize("tex", ["2", "2 "])
def test_authoritative_numeric_math_beside_digits(tmp_path: Path, tex: str) -> None:
    path = tmp_path / "math.html"
    path.write_text(f'<p><math alttext="{tex}"><mn>2</mn></math>3 values cost $30 or $50.</p>')
    source = resolve_translation_source(
        AcDocumentService(cache_root=tmp_path / "cache"), path
    )
    block, = source_blocks(source)
    # The source parser may normalize whitespace in the math annotation.
    formula, = source_identity(block)["equations"]
    assert formula.strip() == "2"
    assert protected_atom_plan(block)["atoms"][0]["payload"] == rf"\({formula}\)"
    slot, = text_slot_ids(block)
    rendered, _ = assemble_text_slot_translation(block, {slot: "3 个值花费 $30 或 $50。"})
    assert rendered == rf"\({formula}\)3 个值花费 \$30 或 \$50。"
    validate_translation_text(rendered, block)


def test_translated_currency_link_label(tmp_path: Path) -> None:
    path = tmp_path / "link.html"
    path.write_text('<p><a href="https://example.test/$100">Price $30 or $50</a></p>')
    source = resolve_translation_source(
        AcDocumentService(cache_root=tmp_path / "cache"), path
    )
    block, = source_blocks(source)
    slot, = text_slot_ids(block)
    rendered, _ = assemble_text_slot_translation(block, {slot: "费用 $30 或 $50"})
    assert rendered == r"[费用 \$30 或 \$50](https://example.test/$100)"
    validate_translation_text(rendered, block)
