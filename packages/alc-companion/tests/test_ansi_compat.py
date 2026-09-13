import pytest

from alc_companion.rich_text import strip_ansi_sgr, parse_markdown, RichTextError
from alc_companion.generation_validation import validate_chapter_guide
from alc_companion.content_recovery import literal_markdown


@pytest.mark.parametrize('prefix,suffix', [('\x1b[1m', '\x1b[0m'), (r'\u001b[1m', r'\u001b[0m'), ('\x1b[38;2;1;2;3m', '\x1b[m')])
def test_sgr_is_removed_without_changing_formula(prefix, suffix):
    text = 'Before $' + prefix + r'\frac{a b}{c}' + suffix + '$ after.'
    cleaned, count = strip_ansi_sgr(text)
    assert cleaned == r'Before $\frac{a b}{c}$ after.'
    assert count == 2
    assert strip_ansi_sgr(cleaned) == (cleaned, 0)


@pytest.mark.parametrize('text', ['`\x1b[1m`', '```\n\\u001b[1m\n```', r'\\u001b[1m', r'$\mathbf{x}+\begin{matrix}a&b\end{matrix}$'])
def test_code_and_math_commands_are_preserved(text):
    assert strip_ansi_sgr(text) == (text, 0)


@pytest.mark.parametrize('text', ['\x1b[2J', '\x1b[1', '\x1b[nope m', '\x07', r'\u001b[2J'])
def test_non_sgr_is_not_silently_removed(text):
    assert strip_ansi_sgr(text) == (text, 0)
    with pytest.raises(RichTextError):
        parse_markdown(text)
    tokens = parse_markdown(literal_markdown(text))
    assert any(token.type == 'fence' for token in tokens)


def test_generated_guide_retains_normalization_diagnostic():
    original = 'Formula $\x1b[1mx\\u001b[0m$.'
    proposal = {'chapter_guide': None, 'section_guides': [], 'references': [],
                'companions': [{'title': 'Math', 'after_part': 1, 'content_markdown': original}]}
    accepted = validate_chapter_guide(proposal, chapter_id='c', block_ids=['b'], chapter_anchor_block_id='b')
    unit = accepted['learning_units'][0]
    assert unit['content_markdown'] == 'Formula $x$.'
    assert unit['normalization_diagnostics'] == {'ansi_sgr_removed': 2}
    assert proposal['companions'][0]['content_markdown'] == original


def test_clean_sibling_with_same_text_is_not_marked_normalized():
    proposal = {'chapter_guide': None, 'section_guides': [], 'references': [],
                'companions': [
                    {'title': 'Dirty', 'after_part': 1, 'content_markdown': '\x1b[1mSame\x1b[0m'},
                    {'title': 'Clean', 'after_part': 1, 'content_markdown': 'Same'},
                ]}
    units = validate_chapter_guide(proposal, chapter_id='c', block_ids=['b'], chapter_anchor_block_id='b')['learning_units']
    assert units[0]['normalization_diagnostics'] == {'ansi_sgr_removed': 2}
    assert 'normalization_diagnostics' not in units[1]
