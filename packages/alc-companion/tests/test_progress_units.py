import json
from alc_companion.progress_units import unit_fractions


def test_parallel_chapter_batches_and_guide_steps(tmp_path):
    path = tmp_path / 'events.jsonl'
    events = [
        ('translation_progress', {'artifact_prefix': 'chapters/a/translation', 'completed_units': 2, 'total_units': 4}),
        ('translation_progress', {'artifact_prefix': 'chapters/b/translation', 'completed_units': 1, 'total_units': 10}),
        ('guide_progress_plan', {'execution_scope': 'a', 'owners': {'x': 'a', 'y': 'a'}}),
        ('proposer_reviewer_worker_finished', {'execution_scope': 'a', 'loop_id': 'x', 'status': 'succeeded'}),
    ]
    def write():
        path.write_text('\n'.join(json.dumps({'event': kind, 'data': data}) for kind, data in events))
    write()
    translations, guides = unit_fractions(path, ['a', 'b'])
    assert translations == {'a': .5, 'b': .1}
    assert guides == {'a': .25}
    events.append(('proposer_reviewer_loop_finished', {'execution_scope': 'a', 'loop_id': 'x', 'status': 'succeeded'}))
    write()
    assert unit_fractions(path, ['a', 'b'])[1]['a'] == .475
    assert unit_fractions(path, ['a', 'b'], 1) == ({}, {})


def test_missing_old_and_incomplete_events_are_safe(tmp_path):
    path = tmp_path / 'events.jsonl'
    assert unit_fractions(path, ['a']) == ({}, {})
    path.write_text('{"event":"translation_progress","data":{"completed_units":1,"total_units":2}}\n{')
    assert unit_fractions(path, ['a']) == ({}, {})
