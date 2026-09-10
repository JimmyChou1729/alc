from alc_companion.guide_batches import batch_translation_index, merge_guide_batches, split_guide_chapter
from alc_companion.source_planning import SourceChapter


def test_partition_preserves_coverage_sections_and_stable_identity():
    chapter = SourceChapter('chapter', 'Chapter', tuple(str(i) for i in range(10)), '0',
                            ('3', '7'), ('First', 'Second'), (2, 2))
    batches = split_guide_chapter(chapter)
    assert batches == split_guide_chapter(chapter)
    assert tuple(b for c in batches for b in c.block_ids) == chapter.block_ids
    assert batches[1].block_ids[0] == '3'
    assert all(c.display_anchor_block_id == c.block_ids[0] for c in batches)
    assert tuple(b for c in batches for b in c.section_block_ids) == chapter.section_block_ids
    index = {'cached_document': {'digest': 'frozen'}, 'chapters': [{'chapter_id': 'chapter',
        'parts': [{'block_id': str(i), 'line_start': i + 1, 'line_end': i + 1} for i in range(10)]}]}
    subset = batch_translation_index(index, batches[1])
    assert subset['cached_document'] == index['cached_document']
    assert subset['chapters'][0]['parts'][0]['line_start'] == 4
    assert len(index['chapters'][0]['parts']) == 10


def test_merge_preserves_local_anchors_and_audit():
    chapter = SourceChapter('chapter', 'Chapter', ('a', 'b'), 'a')
    reference = {'reference_id': 'ref', 'title': 'Reference'}
    guides = [{'learning_units': [{'unit_id': b, 'placement': 'chapter', 'anchor_block_ids': [b]}],
               'references': [reference]} for b in chapter.block_ids]
    guides[1]['delivery_issue'] = {'category': 'guide_evaluated_omitted'}
    result = merge_guide_batches(chapter, guides)
    assert result['chapter_id'] == chapter.chapter_id
    assert [u['anchor_block_ids'] for u in result['learning_units']] == [['a'], ['b']]
    assert all(u['placement'] == 'inline' for u in result['learning_units'])
    assert result['references'] == [reference]
    assert len(result['delivery_issue']['batch_issues']) == 1
    assert guides[0]['learning_units'][0]['placement'] == 'chapter'
