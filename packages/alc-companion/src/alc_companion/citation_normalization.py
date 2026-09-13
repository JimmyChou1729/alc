"""Normalize model citation spacing without rewriting Markdown literals."""
import re
from markdown_it import MarkdownIt

def citation_spans(text, *, spaced=False, escaped_at=False):
    """Locate actual inline citations without touching code or link targets."""
    parser = MarkdownIt("commonmark", {"html": True})
    def recognize(state, silent):
        pattern = r"\[[ \t]*@[ \t]*([A-Za-z0-9][A-Za-z0-9._:-]*)[ \t]*\]" if spaced else r"\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]"
        if escaped_at:
            pattern = r"\[\\@([1-9][0-9]*)\]"
        match = re.compile(pattern).match(state.src, state.pos)
        if match is None:
            return False
        if not silent:
            token = state.push("alc_citation", "", 0)
            token.meta = {"start": state.pos, "end": match.end()}
        state.pos = match.end()
        return True
    parser.inline.ruler.before("text", "alc_citation", recognize)
    source_lines = text.splitlines(keepends=True)
    offsets, current = [], 0
    for line in source_lines:
        offsets.append(current)
        current += len(line)
    spans = set()
    for token in parser.parse(text):
        if token.type != "inline" or token.map is None:
            continue
        # Block syntax (list/quote prefixes) is absent from inline.content.
        inline_offsets = {}
        current = 0
        for number, line in enumerate(token.content.split("\n"), token.map[0]):
            if number >= len(source_lines):
                break
            column = source_lines[number].find(line)
            if column >= 0:
                for index in range(len(line)):
                    inline_offsets[current + index] = offsets[number] + column + index
            current += len(line) + 1
        for child in token.children or ():
            if child.type != "alc_citation":
                continue
            start, end = child.meta["start"], child.meta["end"]
            if start in inline_offsets and end - 1 in inline_offsets:
                spans.add((inline_offsets[start], inline_offsets[end - 1] + 1))
    return spans


def normalize_escaped_reference_markers(text, positions):
    """Recover an escaped @ only for a supplied positional reference."""
    known_positions = {str(position) for position in positions}
    for start, end in sorted(citation_spans(text, escaped_at=True), reverse=True):
        position = text[start + 3:end - 1]
        if position in known_positions:
            text = text[:start] + f"[@{position}]" + text[end:]
    return text


def normalize_citation_spacing(text):
    for start, end in sorted(citation_spans(text, spaced=True), reverse=True):
        marker = text[start:end]
        key = re.fullmatch(r"\[[ \t]*@[ \t]*([A-Za-z0-9][A-Za-z0-9._:-]*)[ \t]*\]", marker)[1]
        text = text[:start] + "[@" + key + "]" + text[end:]
    return text
