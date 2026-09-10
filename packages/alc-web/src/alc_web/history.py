"""Read-only Web projections of package-owned Agent tasks."""
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from alc_catalog import project_records, records, register_project


def _time(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


def history_jobs(store):
    result = []
    for entry in records(exclude_root=store.root / 'jobs'):
        state = {'succeeded': 'completed', 'failed': 'needs_input', 'paused': 'paused',
                 'pending': 'queued', 'running': 'running', 'cancelled': 'cancelled'}.get(entry['state'], 'needs_input')
        result.append({'id': entry['id'], 'external': True, 'state': state,
            'phase': entry['kind'], 'created': _time(entry['created_at']),
            'display_title': entry['title'], 'spec': {'title': entry['title'], 'output': entry['kind']},
            'detail': {'project': entry['project'], 'run_id': entry['run_id'], 'artifact_available': bool(entry['artifact'])},
            'result': {'available': True} if entry['reader'] else None,
            'metrics': {}, 'error': None})
    return result


def history_job(store, job_id):
    value = next((j for j in history_jobs(store) if j['id'] == job_id), None)
    if value is None:
        raise HTTPException(404, 'Agent task not found; its project may have moved or been removed.')
    return value


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
