import pytest
from alc_companion.citation_normalization import normalize_citation_spacing
from alc_companion.generation_validation import validate_chapter_guide

@pytest.mark.parametrize('marker', ['[ @1]', '[@ 1 ]', '[\t@1\t]', '[@1]'])
def test_spacing_is_normalized_before_source_filtering(marker):
    result = validate_chapter_guide({'chapter_guide': {'title':'Guide','content_markdown':'Text '+marker},
        'section_guides':[], 'companions':[], 'references':[{'title':'Source','source':'https://example.org/paper'}]},
        chapter_id='c',block_ids=('b',),chapter_anchor_block_id='b')
    assert len(result['references']) == 1
    assert result['learning_units'][0]['citations'] == [result['references'][0]['reference_id']]

@pytest.mark.parametrize('text', ['`[ @1]`', '```text\n[ @1]\n```', r'\[ @1]', '[link](https://example.org/[@1])'])
def test_literals_are_preserved(text):
    assert normalize_citation_spacing(text) == text

@pytest.mark.parametrize('text', ['`[@1]`', '[link](https://example.org/[@1])', r'\[@1]', '`[@9]`'])
def test_acceptance_never_rewrites_literal_positional_citations(text):
    result = validate_chapter_guide({'chapter_guide': {'title':'Guide','content_markdown':text},
        'section_guides':[], 'companions':[], 'references':[{'title':'Source','source':'https://example.org/paper'}]},
        chapter_id='c',block_ids=('b',),chapter_anchor_block_id='b')
    assert result['references'] == []
    assert result['learning_units'][0]['content_markdown'] == text

@pytest.mark.parametrize('marker', [r'[\@1]', '> Supported [\\@1]', '- Supported [\\@1]'])
def test_escaped_at_marker_retains_supplied_reference(marker):
    result = validate_chapter_guide({'chapter_guide': {'title': 'Guide', 'content_markdown': marker},
        'section_guides': [], 'companions': [], 'references': [{'title': 'Source', 'source': 'https://example.org/paper'}]},
        chapter_id='c', block_ids=('b',), chapter_anchor_block_id='b')
    assert len(result['references']) == 1
    assert result['learning_units'][0]['citations'] == [result['references'][0]['reference_id']]

@pytest.mark.parametrize('text', [r'`[\@1]`', '```text\n[\\@1]\n```', r'\[\@1]',
    r'[link](https://example.org/[\@1])', r'[\@9]', r'[\@name]', r'[\\@1]'])
def test_escaped_at_literals_and_unknown_references_are_preserved(text):
    result = validate_chapter_guide({'chapter_guide': {'title': 'Guide', 'content_markdown': text},
        'section_guides': [], 'companions': [], 'references': [{'title': 'Source', 'source': 'https://example.org/paper'}]},
        chapter_id='c', block_ids=('b',), chapter_anchor_block_id='b')
    assert result['references'] == []
    assert result['learning_units'][0]['content_markdown'] == text
