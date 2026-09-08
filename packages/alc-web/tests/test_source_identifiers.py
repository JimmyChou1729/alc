import pytest
from alc_web.acquisition import normalize_source_url


@pytest.mark.parametrize('value,identifier', [
    ('2609.04308', '2609.04308'),
    (' 2609.04308v1 ', '2609.04308v1'),
    ('arXiv:2609.04308', '2609.04308'),
    ('arxiv: 2609.04308v12', '2609.04308v12'),
    ('0704.0001', '0704.0001'),
    ('astro-ph/0601001', 'astro-ph/0601001'),
])
def test_arxiv_identifiers(value, identifier):
    assert normalize_source_url(value) == 'https://arxiv.org/html/' + identifier


@pytest.mark.parametrize('value', ['2609.043', '2609.043080', '2609.04308v0', 'arXiv:../../foo', 'http://example.org/paper', 'https://user:pass@example.org/paper'])
def test_invalid_inputs_remain_rejected(value):
    with pytest.raises(ValueError):
        normalize_source_url(value)


def test_urls_and_dois_remain_supported():
    assert normalize_source_url('https://arxiv.org/html/2609.04308v1') == 'https://arxiv.org/html/2609.04308v1'
    assert normalize_source_url('10.1234/example') == 'https://doi.org/10.1234/example'
