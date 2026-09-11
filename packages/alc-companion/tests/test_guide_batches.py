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


def test_parent_numbers_map_by_source_identity_without_changing_evidence():
    from alc_companion.guide_batches import normalize_batch_numbers
    parent = SourceChapter('parent', 'Chapter', tuple(str(i) for i in range(700)), '0')
    batch = SourceChapter('batch', 'Chapter', parent.block_ids[550:640], '550')
    proposal = {'companions': [{'after_part': 581}, {'after_part': 583},
                              {'after_part': 20}, {'after_part': 999}]}
    mapped = normalize_batch_numbers(proposal, batch, parent)
    assert [x['after_part'] for x in mapped['companions']] == [31, 33, 20, 999]
    assert proposal['companions'][0]['after_part'] == 581
    review = {'payload': {'checked_part_numbers': [581], 'checked_section_numbers': []}}
    assert normalize_batch_numbers(review, batch, parent, review=True)['payload']['checked_part_numbers'] == [31]
    # No extra inspected locations are invented to make a proposal pass.
    assert 33 not in normalize_batch_numbers(review, batch, parent, review=True)['payload']['checked_part_numbers']
    assert normalize_batch_numbers(mapped, batch, parent) == mapped


def test_confirmed_parent_source_citations_become_source_links_only():
    from alc_companion.guide_batches import normalize_batch_numbers
    parent = SourceChapter('parent', 'Chapter', tuple(str(i) for i in range(700)), '0')
    batch = SourceChapter('batch', 'Chapter', parent.block_ids[550:640], '550')
    value = {'references': [{'title': 'Book', 'source': 'Book'}], 'companions': [
        {'after_part': 581, 'content_markdown': 'Source [@581], book [@1], unknown [@999].'}]}
    result = normalize_batch_numbers(value, batch, parent)
    assert result['companions'][0]['content_markdown'] == 'Source [↗](#block-580), book [@1], unknown [@999].'
    assert value['companions'][0]['after_part'] == 581


def test_source_only_local_citations_use_batch_blocks():
    from alc_companion.guide_batches import normalize_batch_numbers
    parent = SourceChapter('parent', 'Chapter', ('a', 'b', 'c', 'd'), 'a')
    batch = SourceChapter('batch', 'Chapter', ('c', 'd'), 'c')
    value = {'references': [], 'companions': [{'after_part': 1, 'content_markdown': 'See [@1] and [@99].'}]}
    result = normalize_batch_numbers(value, batch, parent)
    assert result['companions'][0]['content_markdown'] == 'See [↗](#block-c) and [@99].'


def test_invalid_batch_collections_survive_until_content_recovery():
    from alc_companion.guide_batches import normalize_batch_numbers
    parent = SourceChapter('parent', 'Chapter', ('a', 'b'), 'a')
    batch = SourceChapter('batch', 'Chapter', ('b',), 'b')
    for value in (None, 42, 'raw text', {'raw': 'content'}):
        candidate = {'companions': value}
        assert normalize_batch_numbers(candidate, batch, parent) == candidate
