import hashlib
import json

import pytest
from alc_web.store import Store
from alc_web.pdf_retry import prepare_pdf_retry


def failed_pdf(tmp_path):
    store = Store(tmp_path)
    job = store.create({'runtime': {'old': True}, 'ocr': {'executable': 'mineru'}, 'model': 'saved-model'})
    root = store.job_directory(job['id'])
    root.mkdir(parents=True)
    pdf = root / 'source.pdf'
    pdf.write_bytes(b'%PDF-1.4 original')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    (root / 'pending-pdf.json').write_text(json.dumps({'path': 'source.pdf', 'sha256': digest}))
    attempt = root / 'ocr-job'
    attempt.mkdir()
    (attempt / 'job.json').write_text(json.dumps({'status': 'failed', 'source_sha256': digest, 'config': {'mode': 'local'}}))
    (attempt / 'local-ocr.log').write_text('original failure evidence')
    store.update(job['id'], state='needs_input', phase='ocr')
    return store, job['id'], root


def test_resume_restarts_unadopted_ocr_and_preserves_evidence(tmp_path):
    store, job_id, root = failed_pdf(tmp_path)
    assert not prepare_pdf_retry(store, store.get(job_id))
    store.control(job_id, 'resume')
    store.claim(job_id)
    assert store.bind_pdf_retry_runtime(job_id, {'new': True})
    archives = list((root / 'ocr-attempts').iterdir())
    assert len(archives) == 1
    assert (archives[0] / 'local-ocr.log').read_text() == 'original failure evidence'
    assert not (root / 'ocr-job').exists()
    assert (root / 'source.pdf').read_bytes() == b'%PDF-1.4 original'
    spec = store.get(job_id)['spec']
    assert spec['model'] == 'saved-model'
    assert spec['runtime'] == {'new': True}
    assert prepare_pdf_retry(store, store.get(job_id))
    assert len(list((root / 'ocr-attempts').iterdir())) == 1


@pytest.mark.parametrize('blocker', ['source', 'downstream', 'changed_pdf', 'ready', 'detail', 'remote'])
def test_saved_work_or_invalid_original_blocks_migration(tmp_path, blocker):
    store, job_id, root = failed_pdf(tmp_path)
    if blocker == 'source':
        (root / 'source.json').write_text('{}')
    elif blocker == 'downstream':
        (root / 'project').mkdir()
    elif blocker == 'changed_pdf':
        (root / 'source.pdf').write_bytes(b'changed')
    elif blocker == 'ready':
        p = root / 'ocr-job/job.json'
        state = json.loads(p.read_text()); state['status'] = 'ready'; p.write_text(json.dumps(state))
    elif blocker == 'detail':
        store.update(job_id, detail={'saved': True})
    else:
        with store.connect() as db:
            spec = store.get(job_id)['spec']; spec['ocr']['api_url'] = 'https://example.test'
            db.execute('UPDATE jobs SET spec=? WHERE id=?', (json.dumps(spec), job_id))
    store.control(job_id, 'resume'); store.claim(job_id)
    assert not store.bind_pdf_retry_runtime(job_id, {'new': True})
    assert (root / 'ocr-job/local-ocr.log').exists()
    assert store.get(job_id)['spec']['runtime'] == {'old': True}


def test_runtime_preparation_error_does_not_leave_job_running(tmp_path, monkeypatch):
    from ac_jobs import FileLease
    from alc_web.worker import execute
    store, job_id, root = failed_pdf(tmp_path)
    store.control(job_id, 'resume'); store.claim(job_id)
    monkeypatch.setattr('alc_web.runtime.runtime_identity', lambda: {'new': True})
    def blocked(*args):
        raise OSError('archive unavailable')
    monkeypatch.setattr('alc_web.pdf_retry.prepare_pdf_retry', blocked)
    execute(str(tmp_path), job_id)
    assert store.get(job_id)['state'] == 'needs_input'
    assert store.get(job_id)['error']['code'] == 'runtime_preparation_failed'
    with FileLease(root / 'worker.lock').acquire(blocking=False):
        assert (root / 'ocr-job/local-ocr.log').exists()


def test_busy_ocr_lease_releases_worker_and_reports_recovery_error(tmp_path, monkeypatch):
    from ac_jobs import FileLease
    from alc_web.worker import execute
    store, job_id, root = failed_pdf(tmp_path)
    store.control(job_id, 'resume'); store.claim(job_id)
    monkeypatch.setattr('alc_web.runtime.runtime_identity', lambda: {'new': True})
    with FileLease(root / '.ocr-job.mineru.lock').acquire(blocking=False):
        execute(str(tmp_path), job_id)
        assert store.get(job_id)['state'] == 'needs_input'
        assert store.get(job_id)['error']['code'] == 'runtime_preparation_failed'
        with FileLease(root / 'worker.lock').acquire(blocking=False):
            assert (root / 'ocr-job/local-ocr.log').exists()
