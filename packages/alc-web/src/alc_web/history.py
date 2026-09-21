"""Live projections and Web-local presentation of package-owned Agent tasks."""
from datetime import datetime
import json
from pathlib import Path
from fastapi import HTTPException
from ac_jobs.errors import AcJobsError
from alc_catalog import project_records, records, register_project
from .presentation import source_label


def _time(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


def _is_local_web_job_project(value):
    """Exclude projects nested inside any Local Web task workspace.

    A catalog is shared between Local Web workspaces.  A task created by one
    workspace can therefore be discovered while another workspace is open,
    but it must not be presented as read-only Agent-plugin history.
    """
    path = Path(value).resolve()
    for candidate in (path, *path.parents):
        if candidate.name != 'project':
            continue
        job = candidate.parent
        jobs = job.parent
        web = jobs.parent
        if (
            jobs.name == 'jobs'
            and web.name == 'web'
            and web.parent.name == '.alc'
        ):
            return True
    return False


def _history_source_label(entry):
    manifest = Path(entry['project']) / 'source-bundle/manifest.json'
    try:
        bundle = json.loads(manifest.read_text()).get('bundle', {})
        source = bundle.get('requested_url') or bundle.get('final_url')
        return source_label({'source_url': source}) if source else ''
    except (OSError, ValueError, TypeError):
        return ''


def history_jobs(store):
    result = []
    with store.connect() as db:
        presentation = {row['job_id']: dict(row) for row in db.execute('SELECT * FROM job_presentation')}
    for entry in records():
        if _is_local_web_job_project(entry['project']):
            continue
        display = presentation.get(entry['id'], {})
        if display.get('deleted'):
            continue
        state = {'succeeded': 'completed', 'failed': 'needs_input', 'paused': 'paused',
                 'pending': 'queued', 'running': 'running', 'cancelled': 'cancelled'}.get(entry['state'], 'needs_input')
        result.append({'id': entry['id'], 'external': True, 'state': state,
            'phase': entry['kind'], 'created': _time(entry['created_at']),
            'display_title': display.get('title') or entry['title'],
            'source_label': _history_source_label(entry),
            'spec': {'title': entry['title'], 'output': entry['kind']},
            'detail': {'project': entry['project'], 'run_id': entry['run_id'], 'artifact_available': bool(entry['artifact'])},
            'result': {'available': True} if entry['reader'] else None,
            'metrics': {}, 'error': None})
    return result


def history_job(store, job_id):
    value = next((j for j in history_jobs(store) if j['id'] == job_id), None)
    if value is None:
        raise HTTPException(404, 'Agent task not found; its project may have moved or been removed.')
    kind = value['spec']['output']
    if kind in ('companion', 'translate'):
        try:
            if kind == 'companion':
                from alc_companion.service import CompanionService as Service
            else:
                from alc_translate.service import TranslationService as Service
            value['detail']['progress'] = dict(Service(
                Path(value['detail']['project']) / f'.alc/{kind}/jobs'
            ).progress(value['detail']['run_id']))
        except (OSError, ValueError, KeyError, RuntimeError, AcJobsError):
            value['detail']['progress_unavailable'] = True
    return value


def rename_history(store, job_id, title):
    history_job(store, job_id)
    title = title.strip()
    if not title or len(title) > 500:
        raise HTTPException(400, '任务名称请输入1–500个字符。')
    with store.connect() as db:
        db.execute('INSERT INTO job_presentation(job_id,title) VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET title=excluded.title', (job_id,title))
    return history_job(store, job_id)


def reader_translation_title(store, job_id):
    history_job(store, job_id)
    with store.connect() as db:
        row = db.execute(
            'SELECT translated_title FROM reader_presentation WHERE job_id=?',
            (job_id,),
        ).fetchone()
    return row['translated_title'] if row and row['translated_title'] else ''


def rename_history_reader_translation_title(store, job_id, title):
    history_job(store, job_id)
    title = title.strip()
    if not title or len(title) > 500:
        raise HTTPException(400, '译文标题请输入1–500个字符。')
    with store.connect() as db:
        db.execute(
            'INSERT INTO reader_presentation(job_id,translated_title) VALUES(?,?) '
            'ON CONFLICT(job_id) DO UPDATE SET translated_title=excluded.translated_title',
            (job_id, title),
        )
    return title


def delete_history(store, job_id):
    history_job(store, job_id)
    with store.connect() as db:
        db.execute('INSERT INTO job_presentation(job_id,deleted) VALUES(?,1) ON CONFLICT(job_id) DO UPDATE SET deleted=1', (job_id,))
    return {'deleted': True}


def import_project(value):
    project = Path(value).expanduser().resolve()
    entries = project_records(project)
    if not entries:
        raise HTTPException(400, '所选目录中没有可读取的 ALC 任务，请填写原来的项目目录。')
    register_project(project)
    return {'imported': len(entries), 'project': str(project)}


def reader_path(store, job_id):
    entry = next((r for r in records(exclude_root=store.root / 'jobs') if r['id'] == job_id), None)
    if entry is None or not entry['reader']:
        raise HTTPException(404, '该任务尚未生成可打开的 Reader，或结果文件已被移动。')
    path = Path(entry['reader']).resolve()
    if not path.is_relative_to(Path(entry['project']).resolve()) or not path.is_file():
        raise HTTPException(409, 'Reader is no longer inside the registered project.')
    return path


def artifact_path(store, job_id):
    entry = next((r for r in records(exclude_root=store.root / 'jobs') if r['id'] == job_id), None)
    if entry is None or not entry['artifact']:
        raise HTTPException(404, 'Verified task result is unavailable.')
    return Path(entry['artifact'])
