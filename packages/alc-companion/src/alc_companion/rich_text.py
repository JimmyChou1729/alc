"""Validation for model-authored Companion Markdown."""

from __future__ import annotations

import re
from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token


_CITATION = re.compile(r"\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]")


class RichTextError(ValueError):
    """Companion Markdown is invalid."""


def parse_markdown(value: str) -> tuple[Token, ...]:
    if not isinstance(value, str) or not value.strip():
        raise RichTextError("learning-unit markdown must be a non-empty string")
    _validate_display_math(value)
    tokens = tuple(_parser().parse(value))
    _reject_raw_html(tokens)
    return tokens


def citation_ids(value: str) -> tuple[str, ...]:
    return citation_ids_from_tokens(parse_markdown(value))


def citation_ids_from_tokens(tokens: Sequence[Token]) -> tuple[str, ...]:
    values: list[str] = []
    for token in tokens:
        values.extend(
            child.content
            for child in token.children or ()
            if child.type == "alc_citation"
        )
    return tuple(values)


def validate_rich_markdown(
    markdown: str,
    *,
    allowed_evidence_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    values = citation_ids(markdown)
    if allowed_evidence_ids is not None:
        allowed = set(allowed_evidence_ids)
        try:
            unknown = next(item for item in values if item not in allowed)
        except StopIteration:
            pass
        else:
            raise RichTextError(
                f"citation is not in bibliography: {unknown}"
            )
    return values


def canonicalize_display_math(value: str) -> str:
    """Isolate paired display delimiters without rewriting formula content."""

    if not isinstance(value, str):
        raise RichTextError("learning-unit markdown must be a string")
    visible = _visible_markdown(value)
    positions = _double_dollar_positions(visible)
    if len(positions) % 2:
        raise RichTextError("display-math $$ delimiters are unbalanced")
    for index, position in enumerate(positions):
        if (
            position > 0
            and visible[position - 1] == "$"
            and not _is_escaped(visible, position - 1)
        ) or visible[position + 2 : position + 3] == "$":
            raise RichTextError("display-math $$ delimiters are ambiguous")
        if index % 2 and not value[positions[index - 1] + 2 : position].strip():
            raise RichTextError("display-math body must not be empty")

    output: list[str] = []
    for line, visible_line in zip(value.split("\n"), visible.split("\n")):
        delimiters = _double_dollar_positions(visible_line)
        if not delimiters or visible_line.strip() == "$$":
            output.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        start = 0
        for position in delimiters:
            segment = line[start:position]
            if segment.strip():
                output.append((indent if start else "") + segment)
            output.append(indent + "$$")
            start = position + 2
        if line[start:].strip():
            output.append(indent + line[start:])
    normalized = "\n".join(output)
    _validate_display_math(normalized)
    return normalized


def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark", {"html": True})
    parser.inline.ruler.before("text", "alc_citation", _citation)
    return parser


def _validate_display_math(value: str) -> None:
    display_open = False
    for visible in _visible_markdown(value).split("\n"):
        positions = _double_dollar_positions(visible)
        if not positions:
            continue
        if visible.strip() != "$$" or len(positions) != 1:
            raise RichTextError(
                "display-math $$ delimiters must occupy separate lines"
            )
        display_open = not display_open
    if display_open:
        raise RichTextError("display-math $$ delimiters are unbalanced")


def _code_line_numbers(value: str) -> set[int]:
    lines: set[int] = set()
    for token in _parser().parse(value):
        if token.type not in {"fence", "code_block"} or token.map is None:
            continue
        lines.update(range(token.map[0], token.map[1]))
    return lines


def _visible_markdown(value: str) -> str:
    code_lines = _code_line_numbers(value)
    visible = "\n".join(
        " " * len(line) if number in code_lines else line
        for number, line in enumerate(value.split("\n"))
    )
    return _outside_code_spans(visible)


def _outside_code_spans(line: str) -> str:
    output = list(line)
    position = 0
    while position < len(line):
        if line[position] != "`" or _is_escaped(line, position):
            position += 1
            continue
        run_end = position
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        run_length = run_end - position
        cursor = run_end
        closing = -1
        while cursor < len(line):
            if line[cursor] != "`":
                cursor += 1
                continue
            close_end = cursor
            while close_end < len(line) and line[close_end] == "`":
                close_end += 1
            if close_end - cursor == run_length:
                closing = close_end
                break
            cursor = close_end
        if closing < 0:
            position = run_end
            continue
        output[position:closing] = [
            "\n" if char == "\n" else " " for char in line[position:closing]
        ]
        position = closing
    return "".join(output)


def _double_dollar_positions(value: str) -> tuple[int, ...]:
    positions: list[int] = []
    index = 0
    while index + 1 < len(value):
        if value[index : index + 2] != "$$":
            index += 1
            continue
        if _is_escaped(value, index):
            index += 1
            continue
        positions.append(index)
        index += 2
    return tuple(positions)


def _is_escaped(value: str, position: int) -> bool:
    slashes = 0
    cursor = position - 1
    while cursor >= 0 and value[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _citation(state: StateInline, silent: bool) -> bool:
    match = _CITATION.match(state.src, state.pos)
    if match is None:
        return False
    if not silent:
        token = state.push("alc_citation", "", 0)
        token.content = match.group(1)
    state.pos = match.end()
    return True


def _reject_raw_html(tokens: Sequence[Token]) -> None:
    for token in tokens:
        if token.type == "html_block":
            raise RichTextError(
                "raw HTML is not permitted in learning-unit markdown"
            )
        if any(
            child.type == "html_inline" for child in token.children or ()
        ):
            raise RichTextError(
                "raw HTML is not permitted in learning-unit markdown"
            )


__all__ = [
    "RichTextError",
    "canonicalize_display_math",
    "citation_ids",
    "citation_ids_from_tokens",
    "parse_markdown",
    "validate_rich_markdown",
]
