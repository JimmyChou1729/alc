import pytest

from alc_translate.source import TranslationSourceError, validate_caption_translation


CAPTION = 'FIGURE 6.8 Conformal diagram for the Kerr solution with $G^2M^2>a^2$. As with the charged solution, there are infinite copies.'


def block(caption=CAPTION):
    return {'block_id': 'caption', 'kind': 'figure', 'payload': {'caption': caption}}


@pytest.mark.parametrize('text', [
    '带有 $G^2M^2>a^2$。与带电解类似，存在无限多个副本。',
    '图 6.8 带有 $G^2M^2>a^2$。与带电解类似，存在无限多个副本。',
])
def test_detects_missing_label_or_almost_empty_caption_subject(text):
    with pytest.raises(TranslationSourceError) as error:
        validate_caption_translation(text, block())
    assert error.value.code == 'translation_caption_incomplete'


@pytest.mark.parametrize('text', [
    '图 6.8 满足 $G^2M^2>a^2$ 的 Kerr 解的共形图。与带电解类似，存在无限多个副本。',
    '图 6.8 Kerr 解的共形图，其中 $G^2M^2>a^2$。',
    '图6.8 满足 $G^2M^2>a^2$ 的 Kerr 解的共形图。',
    '第6.8图，满足 $G^2M^2>a^2$ 的 Kerr 解的共形图。',
    'Figure 6.8. Kerr geometry with $G^2M^2>a^2$.',
    'Figure 6.8 Kerr geometry with $G^2M^2>a^2$.',
])
def test_preserves_concise_or_reordered_complete_captions(text):
    validate_caption_translation(text, block())


def test_unlabelled_short_caption_is_not_subject_to_length_ratio():
    validate_caption_translation('能谱', block('Energy spectrum'))


@pytest.mark.parametrize('number', ['16.8', '6.80', '6.8.1'])
def test_does_not_accept_a_different_figure_number(number):
    with pytest.raises(TranslationSourceError):
        validate_caption_translation(f'图 {number} Kerr 解的共形图，其中 $G^2M^2>a^2$。', block())
