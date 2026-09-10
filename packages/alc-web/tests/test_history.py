import json
from fastapi.testclient import TestClient
from alc_catalog import register_project
from alc_web.app import create_app


def test_agent_history_import_authentication_and_read_only_controls(tmp_path):
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
        assert client.get('/api/jobs/'+job_id).json()['state'] == 'completed'
        download = client.get(f'/api/jobs/{job_id}/reader?download=true')
        assert download.status_code == 200 and 'Saved Reader' in download.text
        assert 'sandbox' in download.headers['content-security-policy']
        assert client.post(f'/api/jobs/{job_id}/control', json={'action':'resume'}).status_code == 409
        assert client.delete('/api/jobs/'+job_id).status_code == 409
        assert app.state.store.list() == []
        (project / 'companion.html').unlink()
        assert client.get(f'/api/jobs/{job_id}/reader?download=true').status_code == 404
