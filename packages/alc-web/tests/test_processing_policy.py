import pytest
from pydantic import ValidationError
from alc_web.models import JobInput
from alc_web.store import Store
from alc_web.worker import Worker


def test_web_and_dev_use_per_task_limits_with_matching_timeouts(tmp_path, monkeypatch):
    from alc_companion.cli import _parser as companion_parser, _execution_options
    from alc_translate.cli import _parser as translate_parser, _execution

    monkeypatch.setenv('AC_HOME', str(tmp_path / 'ac-home'))
    web_options = []
    for name in ('first-workspace', 'second-workspace'):
        store = Store(tmp_path / name)
        job = store.create({'source_url': 'https://example.org/paper', 'provider_id': 'codex'})
        web_options.append(Worker(store, job['id']).options)
    translate = _execution(translate_parser().parse_args([
        'translate-blocks', 'source.md', '--project-dir', str(tmp_path / 'translate'),
        '--execution-profile', 'local-app', '--window-workers', '8',
    ])).llm
    companion = _execution_options(companion_parser().parse_args([
        'build', 'source.md', '--project-dir', str(tmp_path / 'companion'),
        '--execution-profile', 'local-app', '--workers', '2',
    ])).llm
    for options in [*web_options, translate, companion]:
        assert options.gate.global_limit == 8
        assert options.gate.shared_root is None
        assert options.limits.idle_timeout_seconds == 300
        assert options.limits.total_timeout_seconds == 600


@pytest.mark.parametrize('workers,reviews', [(4, 0), (2, 1), (2, 2), (7, 2)])
def test_explicit_policy_survives_storage_and_overrides_legacy_speed(tmp_path, workers, reviews):
    spec = JobInput(source_url='https://example.org/paper', processing_workers=workers, review_rounds=reviews).model_dump()
    store = Store(tmp_path)
    job = store.create(spec)
    for generation in (1, 2):
        store.update(job['id'], generation=generation)
        worker = Worker(store, job['id'])
        assert worker.window_workers == worker.companion_workers == workers
        args = worker.model_args()
        assert args[args.index('--review-rounds')+1] == str(reviews)


@pytest.mark.parametrize('policy', [dict(processing_workers=2), dict(review_rounds=1), dict(processing_workers=0,review_rounds=1), dict(processing_workers=9,review_rounds=1), dict(processing_workers=2,review_rounds=3), dict(processing_workers=True,review_rounds=False)])
def test_invalid_or_partial_policy_is_rejected(policy):
    with pytest.raises(ValidationError):
        JobInput(source_url='https://example.org/paper', **policy)


def test_legacy_job_keeps_original_policy(tmp_path):
    store = Store(tmp_path)
    spec = JobInput(source_url='https://example.org/paper', speed='fast').model_dump()
    job = store.create(spec)
    worker = Worker(store, job['id'])
    assert worker.window_workers == 4
    assert '--review-rounds' not in worker.model_args()


@pytest.mark.parametrize('generation', [1, 2])
def test_explicit_preload_reaches_build_and_resume(tmp_path, monkeypatch, generation):
    store = Store(tmp_path)
    job = store.create({'source_url':'https://example.org/paper','output':'companion','provider_id':'codex','preload_chapter_evidence':True})
    store.update(job['id'], generation=generation)
    worker = Worker(store, job['id']); worker.active_owner = 'companion'
    captured=[]
    def cli(owner, command, **kwargs):
        if command[0]=='status': return {'data':{'run':{'status':'failed'}}}
        captured.append(command); return {'data':{}}
    monkeypatch.setattr('alc_web.worker.call_cli',cli)
    worker.stage('companion',['build','source.md'])
    assert '--preload-chapter-evidence' in captured[0]
    assert captured[0][0] == ('build' if generation==1 else 'resume')
