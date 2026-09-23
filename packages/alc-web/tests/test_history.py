import json
from fastapi.testclient import TestClient
from alc_catalog import register_project
from alc_web.app import create_app


def test_agent_history_import_authentication_and_local_controls(tmp_path, monkeypatch):
    project = tmp_path / 'plugin-project'
    run = project / '.alc/companion/jobs/runs/run-one'
    run.mkdir(parents=True)
    (run / 'snapshot.json').write_text(json.dumps({'run_id': 'run-one', 'status': 'succeeded', 'created_at': '2026-09-10T01:00:00Z', 'updated_at': '2026-09-10T02:00:00Z'}))
    (run / 'spec.json').write_text(json.dumps({'run_id': 'run-one', 'semantic_input': {'request': {'source_bundle': {'requested_url': 'https://arxiv.org/html/2609.10568v1'}}}}))
    (project / '.alc/companion/project.json').write_text(json.dumps({'current_run_id': 'run-one'}))
    (project / 'companion.html').write_text('<html>Saved Reader</html>')
    source_bundle = project / 'source-bundle'
    source_bundle.mkdir()
    (source_bundle / 'manifest.json').write_text(json.dumps({
        'bundle': {'requested_url': 'https://arxiv.org/html/2609.10568v1'},
    }))
    origin = 'http://127.0.0.1:8765'
    app = create_app(tmp_path / 'web', token='test-token', origin=origin, run_scheduler=False, discovered=[])
    with TestClient(app, base_url=origin) as client:
        assert client.post('/api/history/projects', json={'path': str(project)}).status_code in (401,403)
        client.headers.update({'Origin': origin, 'Authorization': 'Bearer test-token'})
        response = client.post('/api/history/projects', json={'path': str(project)})
        assert response.status_code == 200, response.text
        for _ in range(2): register_project(project)
        rows = client.get('/api/jobs').json()
        assert len(rows) == 1 and rows[0]['external']
        assert rows[0]['source_label'] == '2609.10568v1'
        assert rows[0]['source_type'] == 'https'
        assert rows[0]['completed'] == rows[0]['created'] + 3600
        job_id = rows[0]['id']
        detail = client.get('/api/jobs/'+job_id).json()
        assert detail['state'] == 'completed'
        assert detail['detail']['progress_unavailable'] is True
        from alc_companion.service import CompanionService
        progress = {'phase': 'guides', 'completed_units': 2, 'total_units': 4}
        monkeypatch.setattr(CompanionService, 'progress', lambda self, run_id: dict(progress))
        assert client.get('/api/jobs/'+job_id).json()['detail']['progress']['completed_units'] == 2
        progress['completed_units'] = 3
        assert client.get('/api/jobs/'+job_id).json()['detail']['progress']['completed_units'] == 3
        download = client.get(f'/api/jobs/{job_id}/reader?download=true')
        assert download.status_code == 200 and 'Saved Reader' in download.text
        assert 'sandbox' in download.headers['content-security-policy']
        assert client.post(f'/api/jobs/{job_id}/control', json={'action':'resume'}).status_code == 409
        assert client.patch('/api/jobs/'+job_id, json={'title':'My Agent task'}).status_code == 200
        snapshot = run / 'snapshot.json'
        original = snapshot.read_text()
        updated = json.loads(original)
        updated['status'] = 'running'
        snapshot.write_text(json.dumps(updated))
        detail = client.get('/api/jobs/'+job_id).json()
        assert detail['state'] == 'running'
        assert detail['completed'] is None
        assert detail['display_title'] == 'My Agent task'
        assert client.patch('/api/jobs/'+job_id, json={'title':' '}).status_code == 400
        assert client.delete('/api/jobs/'+job_id).status_code == 200
        assert snapshot.read_text() == json.dumps(updated)
        assert (project / 'companion.html').exists()
        assert client.get('/api/jobs').json() == []
        register_project(project)
        assert client.get('/api/jobs').json() == []
        assert client.get('/api/jobs/'+job_id).status_code == 404
        assert app.state.store.list() == []
        (project / 'companion.html').unlink()
        assert client.get(f'/api/jobs/{job_id}/reader?download=true').status_code == 404


def test_history_ignores_local_web_projects_from_other_workspaces(tmp_path, monkeypatch):
    catalog = tmp_path / 'catalog'
    monkeypatch.setenv('ALC_CATALOG_DIR', str(catalog))
    project = tmp_path / 'older-web' / '.alc' / 'web' / 'jobs' / 'job-one' / 'project'
    run = project / '.alc' / 'companion' / 'jobs' / 'runs' / 'run-one'
    run.mkdir(parents=True)
    (run / 'snapshot.json').write_text(json.dumps({'run_id': 'run-one', 'status': 'succeeded'}))
    (run / 'spec.json').write_text(json.dumps({'run_id': 'run-one', 'semantic_input': {}}))
    register_project(project)
    app = create_app(tmp_path / 'new-web', token='test-token', origin='http://127.0.0.1:8765', run_scheduler=False, discovered=[])
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers.update({'Origin': 'http://127.0.0.1:8765', 'Authorization': 'Bearer test-token'})
        assert client.get('/api/jobs').json() == []


def test_agent_history_uses_each_runs_frozen_source_not_project_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv('ALC_CATALOG_DIR', str(tmp_path / 'catalog'))
    project = tmp_path / 'agent-project'
    for run_id, url in [('run-a', 'https://arxiv.org/html/2609.10568v1'),
                        ('run-b', 'https://doi.org/10.1234/different'),
                        ('run-c', None)]:
        run = project / '.alc/companion/jobs/runs' / run_id
        run.mkdir(parents=True)
        (run / 'snapshot.json').write_text(json.dumps({'run_id': run_id, 'status': 'succeeded'}))
        request = {'source_bundle': {'requested_url': url}} if url else {}
        (run / 'spec.json').write_text(json.dumps({'run_id': run_id, 'semantic_input': {'request': request}}))
    bundle = project / 'source-bundle'
    bundle.mkdir()
    (bundle / 'manifest.json').write_text(json.dumps({'bundle': {'requested_url': 'https://wrong.example/current'}}))
    register_project(project)
    app = create_app(tmp_path / 'web', token='test-token', origin='http://127.0.0.1:8765', run_scheduler=False, discovered=[])
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.headers.update({'Origin': 'http://127.0.0.1:8765', 'Authorization': 'Bearer test-token'})
        jobs = {job['detail']['run_id']: job for job in client.get('/api/jobs').json()}
    assert jobs['run-a']['source_label'] == '2609.10568v1'
    assert jobs['run-b']['source_label'] == '10.1234/different'
    assert jobs['run-a']['source_type'] == jobs['run-b']['source_type'] == 'https'
    assert jobs['run-c']['source_label'] == ''
    assert jobs['run-c']['source_type'] == 'other'
