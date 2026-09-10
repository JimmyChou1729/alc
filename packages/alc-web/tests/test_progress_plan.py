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


def test_smoothing_is_bounded_and_only_delivery_reaches_100():
    j = job(source_id='a', title='test.pdf', ocr_proofread=True)
    values = [estimate(j, {'ocr'}, t, {}, 10) for t in (0, 10, 30, 100, 100000)]
    assert values == sorted(values)
    j['phase'] = 'ocr_proofread'
    assert estimate(j, {'ocr'}, 0, {}, 10) == values[-1]
    j['phase'] = 'validate'
    assert estimate(j, {'ocr'}, 100000, {}, 10) == 99
    j['state'] = 'completed'
    assert estimate(j, {'ocr'}, 0, {}, 10) == 100


def test_page_count_increases_proofreading_share():
    j = job(source_id='a', title='test.pdf', ocr_proofread=True)
    small, large = dict(plan(j, set(), 10)), dict(plan(j, set(), 47))
    assert large['ocr_proofread']/sum(large.values()) > small['ocr_proofread']/sum(small.values())
