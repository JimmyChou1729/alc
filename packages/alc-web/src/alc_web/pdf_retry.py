"""Restart failed local OCR before any derived source has been adopted."""

import hashlib
import json
import uuid

from ac_jobs import FileLease


def retryable_pdf(store, job):
    root = store.job_directory(job['id'])
    allowed = {'input', 'source.pdf', 'pending-pdf.json', 'ocr-job', 'ocr-attempts',
               '.ocr-job.mineru.lock', 'worker.lock', 'worker.log', 'provider.json'}
    if job['phase'] not in {'acquisition', 'ocr'} or job.get('detail') or job.get('result'):
        return False
    if not root.is_dir() or any(p.name not in allowed or p.is_symlink() for p in root.iterdir()):
        return False
    if not job['spec'].get('ocr') or job['spec']['ocr'].get('api_url'):
        return False
    try:
        pending = json.loads((root / 'pending-pdf.json').read_text())
        pdf = (root / pending['path']).resolve()
        if not pdf.is_relative_to(root.resolve()) or hashlib.sha256(pdf.read_bytes()).hexdigest() != pending['sha256']:
            return False
        attempt = root / 'ocr-job'
        if attempt.exists():
            state = json.loads((attempt / 'job.json').read_text())
            if (state.get('status') not in {'failed', 'running', 'prepared'}
                or state.get('source_sha256') != pending['sha256']
                or state.get('config', {}).get('mode') != 'local'):
                return False
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    with store.connect() as db:
        event = db.execute("SELECT data FROM events WHERE job_id=? AND kind='job.control' ORDER BY sequence DESC LIMIT 1", (job['id'],)).fetchone()
    return bool(event and json.loads(event[0]).get('action') == 'resume')


def prepare_pdf_retry(store, job):
    """Called under the Web worker lease, with explicit resume authorization."""
    if not retryable_pdf(store, job):
        return False
    root = store.job_directory(job['id'])
    with FileLease(root / '.ocr-job.mineru.lock').acquire(blocking=False):
        if not retryable_pdf(store, job):
            return False
        attempt = root / 'ocr-job'
        if attempt.exists():
            archive = root / 'ocr-attempts' / uuid.uuid4().hex
            archive.parent.mkdir(exist_ok=True)
            attempt.rename(archive)
            store.event(job['id'], 'ocr.retry_prepared', {'archive': archive.relative_to(root).as_posix()})
    return True
