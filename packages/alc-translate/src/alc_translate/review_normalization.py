"""Restore provable presentation-only review edits before source validation."""

import re
from difflib import SequenceMatcher

from .source import _markdown_math_spans

_GREEK_NAMES = frozenset(
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "pi rho sigma tau upsilon phi chi psi omega".split()
)
_LITERAL_TOKENS = re.compile(r"[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|\s+|.", re.DOTALL)


def _tokens(text, spans):
    tokens = []
    math = {}
    cursor = 0
    for start, end, tex in spans:
        tokens.extend(_LITERAL_TOKENS.findall(text[cursor:start]))
        math[len(tokens)] = tex
        tokens.append(text[start:end])
        cursor = end
    tokens.extend(_LITERAL_TOKENS.findall(text[cursor:]))
    return tokens, math


def restore_review_math_presentation(candidate: str, draft: str) -> str:
    """Undo only exact literal-to-math wrapping at an aligned edit location.

    Existing math atoms are never replaced by this function. A changed value,
    operator, or an ambiguous multi-edit remains subject to strict validation.
    """
    before_spans = _markdown_math_spans(draft)
    after_spans = _markdown_math_spans(candidate)
    if [s[2] for s in before_spans] == [s[2] for s in after_spans]:
        return candidate
    before, before_math = _tokens(draft, before_spans)
    after, after_math = _tokens(candidate, after_spans)
    restored = list(after)
    for tag, i, end_i, j, end_j in SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if tag != "replace" or end_j != j + 1 or j not in after_math:
            continue
        if any(index in before_math for index in range(i, end_i)):
            continue
        literal = "".join(before[i:end_i])
        tex = after_math[j]
        if literal == tex or (literal in _GREEK_NAMES and tex == "\\" + literal):
            restored[j] = literal
    return "".join(restored)
