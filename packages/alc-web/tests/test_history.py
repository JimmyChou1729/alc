import json
from fastapi.testclient import TestClient
from alc_catalog import register_project
from alc_web.app import create_app


def test_agent_history_import_authentication_and_local_controls(tmp_path, monkeypatch):
    project = tmp_path / 'plugin-project'
    run = project / '.alc/companion/jobs/runs/run-one'
    run.mkdir(parents=True)
    (run / 'snapshot.json').write_text(json.dumps({'run_id': 'run-one', 'status': 'succeeded', 'created_at': '2026-09-10T01:00:00Z'}))
    (run / 'spec.json').write_text(json.dumps({'run_id': 'run-one', 'semantic_input': {}}))
    (project / '.alc/companion/project.json').write_text(json.dumps({'current_run_id': 'run-one'}))
    (project / 'companion.html').write_text('<html>Saved Reader</html>')
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
