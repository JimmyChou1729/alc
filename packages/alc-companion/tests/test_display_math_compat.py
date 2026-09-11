"""Lossless display-math layout compatibility for model-authored Markdown."""

import pytest

from alc_companion.rich_text import (
    RichTextError,
    canonicalize_display_math,
    parse_markdown,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("  $$x+y$$", "  $$\n  x+y\n  $$"),
        ("由 $$x+y$$ 得解。", "由 \n$$\nx+y\n$$\n 得解。"),
        ("$$x$$ 与 $$y$$", "$$\nx\n$$\n 与 \n$$\ny\n$$"),
        ("由 $$x\n+y$$ 得解。", "由 \n$$\nx\n+y\n$$\n 得解。"),
        ("$$x\n+y\n$$", "$$\nx\n+y\n$$"),
        ("$$\nx\n+y$$", "$$\nx\n+y\n$$"),
        ("$$x$$\n\n$$\ny\n$$", "$$\nx\n$$\n\n$$\ny\n$$"),
        (
            r"龟坐标满足 $$\frac{dr^*}{dr}=\left(1-\frac{2GM}{r}\right)^{-1},$$ 因而径向零曲线可写成 $t\mp r^*=\mathrm{constant}$。[@1]",
            "龟坐标满足 \n$$\n"
            r"\frac{dr^*}{dr}=\left(1-\frac{2GM}{r}\right)^{-1},"
            "\n$$\n 因而径向零曲线可写成 "
            r"$t\mp r^*=\mathrm{constant}$。[@1]",
        ),
    ],
)
def test_isolate_display_math_without_changing_content(source, expected):
    normalized = canonicalize_display_math(source)
    assert normalized == expected
    assert canonicalize_display_math(normalized) == normalized
    parse_markdown(normalized)


@pytest.mark.parametrize(
    "source",
    [
        r"Escaped \$\$x\$\$ and \$$y\$$",
        "`$$inline$$` and ``$$with ` backtick$$``",
        "`code with\n$$unpaired dollar in code`",
        "```text\n$$unpaired\n```",
        "    $$unpaired indented code",
    ],
)
def test_preserve_code_and_escaped_delimiters(source):
    assert canonicalize_display_math(source) == source
    parse_markdown(source)


def test_normalize_math_beside_code_and_escaped_dollars():
    source = r"`$$code$$` then $$x+\$\$$$ done"
    assert canonicalize_display_math(source) == "`$$code$$` then \n$$\nx+\\$\\$\n$$\n done"


@pytest.mark.parametrize("source", ["$$x", "x$$", "$$x$$ then $$y", "$$$$", "$$ $$", "$$$x$$$"])
def test_reject_ambiguous_or_unbalanced_math(source):
    with pytest.raises(RichTextError, match="display-math"):
        canonicalize_display_math(source)
