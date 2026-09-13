from alc_web.metrics import summarize, _cache
from alc_web.store import Store


def test_wait_resume_and_cache_replay_use_the_same_completed_work(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('alc_web.metrics.time.time', lambda: clock[0])
    store = Store(tmp_path)
    job_id = store.create({'title': 'paper', 'output': 'companion'})['id']
    store.claim(job_id)
    evidence = {'phase': 'guides', 'glossary_ready': True, 'total_chapters': 2,
                'translation_required': True, 'translated_chapters': 2,
                'guided_chapters': 0, 'completed_chapters': 0,
                'completed_units': 6, 'total_units': 11}
    store.update(job_id, phase='companion', detail={'progress': evidence})
    initial = summarize(store, store.get(job_id))['progress']['percent']
    assert 60 <= initial < 75
    clock[0] += 100000
    assert summarize(store, store.get(job_id))['progress']['percent'] == initial
    projection = _cache[(str(store.path), job_id)]
    projection.smooth_percent = 99  # Old in-memory estimates cannot force the bar forward.
    assert summarize(store, store.get(job_id))['progress']['percent'] == initial
    store.update(job_id, state='paused')
    store.control(job_id, 'resume')
    store.claim(job_id)
    store.update(job_id, detail={'progress': {'phase': 'source_preparation', 'completed_units': 0}})
    assert summarize(store, store.get(job_id))['progress']['percent'] == initial
    _cache.clear()
    assert summarize(store, store.get(job_id))['progress']['percent'] == initial
    store.update(job_id, detail={'progress': {**evidence, 'guided_chapters': 1, 'completed_units': 7}})
    advanced = summarize(store, store.get(job_id))['progress']['percent']
    assert initial < advanced < 90
    _cache.clear()
    assert summarize(store, store.get(job_id))['progress']['percent'] == advanced
    store.update(job_id, state='completed')
    assert summarize(store, store.get(job_id))['progress']['percent'] == 100


def test_single_chapter_uses_batch_evidence_without_consuming_guide_budget(tmp_path):
    from alc_web.timing import percentage
    evidence = {'phase': 'translation', 'total_chapters': 1, 'glossary_ready': True,
                'translated_chapters': 0, 'guided_chapters': 0}
    values = [percentage('companion', {**evidence, 'translation_fraction': x}, '')
              for x in (0, .25, .5, .75, .98)]
    assert values == sorted(set(values))
    assert values[-1] < 68
    ready = {**evidence, 'translated_chapters': 1, 'phase': 'guides'}
    assert 68 < percentage('companion', {**ready, 'guide_fraction': .5}, '') < 91
    assert percentage('companion', {**ready, 'guide_fraction': float('nan')}, '') == 68


def test_batch_progress_survives_replay_with_unchanged_chapter_count(tmp_path):
    store = Store(tmp_path)
    job_id = store.create({'title': 'paper', 'output': 'companion'})['id']
    store.claim(job_id)
    evidence = {'phase': 'translation', 'total_chapters': 1, 'glossary_ready': True,
                'completed_units': 4, 'translation_fraction': .75}
    store.update(job_id, phase='companion', detail={'progress': evidence})
    percent = summarize(store, store.get(job_id))['progress']['percent']
    store.update(job_id, detail={'progress': {**evidence, 'translation_fraction': .1}})
    _cache.clear()
    assert summarize(store, store.get(job_id))['progress']['percent'] == percent
