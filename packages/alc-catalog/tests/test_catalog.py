import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from alc_catalog import register_project, projects, project_records, records


def task(root, name='run-one'):
    run = root / '.alc/companion/jobs/runs' / name
    run.mkdir(parents=True)
    (run / 'snapshot.json').write_text(json.dumps({'run_id': name, 'status': 'succeeded', 'created_at': '2026-09-10T01:00:00Z'}))
    (run / 'spec.json').write_text(json.dumps({'run_id': name, 'semantic_input': {}}))
    (root / '.alc/companion/project.json').write_text(json.dumps({'current_run_id': name}))
    (root / 'companion.html').write_text('<p>Reader</p>')
    return run


def test_later_web_install_discovers_old_runs_and_deduplicates(tmp_path):
    project = tmp_path / 'old-project'
    task(project)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(register_project, [project] * 8))
    assert projects() == [project]
    rows = records()
    assert len(rows) == 1 and rows[0]['reader'] == str(project / 'companion.html')
    task(project, 'run-two')
    rows = records()
    assert len(rows) == 2
    assert next(r for r in rows if r['run_id'] == 'run-one')['reader'] is None
    assert not (project / '.alc/web').exists()


def test_damaged_and_escaping_runs_do_not_hide_healthy_records(tmp_path):
    project = tmp_path / 'project'
    run = task(project)
    broken = run.parent / 'broken'; broken.mkdir()
    (broken / 'snapshot.json').write_text('bad')
    assert len(project_records(project)) == 1
    (project / 'companion.html').unlink()
    outside = tmp_path / 'private.html'; outside.write_text('private')
    (project / 'companion.html').symlink_to(outside)
    assert all(r['reader'] is None for r in project_records(project))


def test_excludes_owned_web_jobs(tmp_path):
    project = tmp_path / 'web/jobs/one/project'
    task(project); register_project(project)
    assert not records(exclude_root=tmp_path / 'web/jobs')


def test_result_digest_and_live_state_are_checked(tmp_path):
    import hashlib
    project = tmp_path / 'project'
    run = task(project)
    output = run / 'artifacts/result.json'
    output.parent.mkdir()
    output.write_text('{"result": "ready"}')
    snapshot = json.loads((run / 'snapshot.json').read_text())
    snapshot['result_ref'] = {'media_type':'application/json', 'relative_path':'artifacts/result.json',
        'digest':{'value':hashlib.sha256(output.read_bytes()).hexdigest()}}
    (run / 'snapshot.json').write_text(json.dumps(snapshot))
    assert project_records(project)[0]['artifact'] == str(output)
    output.write_text('changed')
    snapshot['status'] = 'failed'
    (run / 'snapshot.json').write_text(json.dumps(snapshot))
    entry = project_records(project)[0]
    assert entry['artifact'] is None and entry['state'] == 'failed'
