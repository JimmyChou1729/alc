import json
from alc_web.store import Store
from alc_web.metrics import summarize


def test_ocr_progress_counts_saved_pages_and_deduplicates(tmp_path):
    store = Store(tmp_path)
    job = store.create({'output': 'reader'})
    root = store.job_directory(job['id']) / 'ocr-job/bundle'
    root.mkdir(parents=True)
    (root / 'manifest.json').write_text(json.dumps({'pages': [{}, {}]}))
    store.update(job['id'], state='running', phase='ocr_proofread')
    for unit, status in [('page-1', 'succeeded'), ('page-1', 'succeeded'), ('page-2', 'failed')]:
        store.event(job['id'], 'package.event', {'run_id': 'ocr1', 'event': 'group_unit_finished', 'data': {'group_id': 'pdf-pages', 'unit_id': unit, 'status': status}})
    progress = summarize(store, store.get(job['id']))['progress']
    assert 0 < progress['percent'] < 100
    assert progress['label'] == '已校对 1 / 2 页'
    assert progress['eta_seconds'] is None
    store.event(job['id'], 'package.event', {'run_id': 'ocr1', 'event': 'group_unit_finished', 'data': {'group_id': 'pdf-pages', 'unit_id': 'page-2', 'status': 'succeeded'}})
    progress = summarize(store, store.get(job['id']))['progress']
    assert progress['percent'] < 100
    assert '正在汇总' in progress['label']


def test_acquisition_has_no_false_numeric_estimate(tmp_path):
    store = Store(tmp_path)
    job = store.create({'output': 'reader'})
    store.update(job['id'], state='running', phase='acquisition')
    progress = summarize(store, store.get(job['id']))['progress']
    assert progress['mode'] == 'overall'
    assert progress['eta_seconds'] is None


def test_paused_estimate_does_not_grow_with_wall_clock(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.create({'output': 'reader'})
    store.claim(job['id'])
    store.update(job['id'], phase='glossary')
    store.update(job['id'], state='paused')
    before = summarize(store, store.get(job['id']))['progress']['percent']
    monkeypatch.setattr('alc_web.metrics.time.time', lambda: 9999999999)
    after = summarize(store, store.get(job['id']))['progress']['percent']
    assert before == after
