from alc_web.progress_plan import plan, estimate


def job(**spec):
    return {'spec': {'output': 'reader', **spec}, 'state': 'running', 'phase': 'ocr'}


def test_routes_use_resolved_format_and_optional_work():
    url = job(source_url='https://example.org/document', ocr_proofread=True)
    assert 'ocr' not in dict(plan(url, set()))
    assert 'ocr_proofread' in dict(plan(url, {'ocr'}, 10))
    pdf = job(source_id='a', title='test.pdf', pdf_mode='text_only')
    assert 'ocr' not in dict(plan(pdf, set()))
    assert 'translation' not in dict(plan(job(output='source'), set()))
    assert 'companion' in dict(plan(job(output='companion'), set()))


def test_elapsed_time_does_not_complete_a_phase_and_only_delivery_reaches_100():
    j = job(source_id='a', title='test.pdf', ocr_proofread=True)
    values = [estimate(j, {'ocr'}, t, {}, 10) for t in (0, 10, 30, 100, 100000)]
    assert len(set(values)) == 1
    j['phase'] = 'ocr_proofread'
    assert estimate(j, {'ocr'}, 0, {}, 10) > values[-1]
    j['phase'] = 'validate'
    assert estimate(j, {'ocr'}, 100000, {}, 10) == estimate(j, {'ocr'}, 0, {}, 10) < 100
    j['state'] = 'completed'
    assert estimate(j, {'ocr'}, 0, {}, 10) == 100


def test_page_count_increases_proofreading_share():
    j = job(source_id='a', title='test.pdf', ocr_proofread=True)
    small, large = dict(plan(j, set(), 10)), dict(plan(j, set(), 47))
    assert large['ocr_proofread']/sum(large.values()) > small['ocr_proofread']/sum(small.values())


def test_companion_waiting_never_spends_the_unstarted_guide_budget():
    j = job(output='companion')
    j['phase'] = 'companion'
    progress = {'phase': 'guides', 'glossary_ready': True, 'total_chapters': 1,
                'translation_required': True, 'translated_chapters': 1,
                'guided_chapters': 0, 'completed_chapters': 0,
                'completed_units': 5, 'total_units': 8}
    values = [estimate(j, {'companion'}, elapsed, progress) for elapsed in (0, 600, 100000)]
    assert len(set(values)) == 1
    assert 60 <= values[0] < 75
    guided = estimate(j, {'companion'}, 0, {**progress, 'guided_chapters': 1})
    joined = estimate(j, {'companion'}, 0, {**progress, 'guided_chapters': 1, 'completed_chapters': 1})
    assert values[0] < guided < joined < 100


def test_companion_generic_completion_cannot_claim_unreported_guide_work():
    from alc_web.timing import percentage
    assert percentage('companion', {'completed_units': 8, 'total_units': 8}, 'companion') == 8
    progress = {'phase': 'guides', 'glossary_ready': True, 'total_chapters': 2,
                'translation_required': False, 'translated_chapters': 0,
                'guided_chapters': 0, 'completed_chapters': 0}
    assert percentage('companion', progress, 'companion') == 68
    assert percentage('companion', {**progress, 'guided_chapters': 1}, 'companion') == 79.5
    assert percentage('companion', {**progress, 'guided_chapters': 500, 'completed_chapters': 500}, 'companion') == 94


def test_unknown_work_waits_for_counts_instead_of_wall_clock():
    for phase in ('glossary', 'translation', 'ocr_proofread'):
        j = job(source_id='pdf', title='paper.pdf', ocr_proofread=True)
        j['phase'] = phase
        initial = estimate(j, {phase}, 0, {}, pages=10)
        assert estimate(j, {phase}, 100000, {}, pages=10) == initial
        progress = {'phase': phase, 'completed_units': 5, 'total_units': 10}
        assert estimate(j, {phase}, 0, progress, pages=10, ocr_done=5) > initial
