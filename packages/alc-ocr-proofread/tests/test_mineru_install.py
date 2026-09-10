from pathlib import Path
import json
import pytest
from alc_ocr_proofread import mineru_install as module


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root=tmp_path/'managed'
    monkeypatch.setattr(module,'installation_root',lambda:root)
    monkeypatch.setattr(module.platform,'system',lambda:'Linux')
    monkeypatch.setattr(module,'DISK_RESERVE',0)
    monkeypatch.setattr(module,'doctor_configured_mineru',lambda **kw: {'available':True})
    def process(argv, root, stage):
        target=root/'venv/bin';target.mkdir(parents=True,exist_ok=True)
        for name in ['python','mineru']:
            p=target/name;p.write_text('executable');p.chmod(0o700)
    monkeypatch.setattr(module,'_run',process)
    def parse(pdf, **kw):
        assert Path(pdf).read_bytes().startswith(b'%PDF-1.4')
        source=tmp_path/'source.html';source.write_text('<p>12345</p>')
        return {'status':'completed','source':str(source)}
    monkeypatch.setattr(module,'parse_pdf_configured_mineru',parse)
    return tmp_path/'project',root


def test_plan_and_missing_consent_do_not_install(setup):
    project,root=setup
    assert module.plan(project)['version']=='3.4.5'
    assert not root.exists()
    with pytest.raises(ValueError,match='accept-downloads'):module.install(project)
    assert not root.exists()


def test_verified_install_adopts_and_reuses(setup, monkeypatch):
    project,root=setup
    result=module.install(project,accept_downloads=True)
    assert result['inference_verified'] and result['configured']
    assert json.loads((project/'.ac/mineru.json').read_text())['executable']==str(root/'venv/bin/mineru')
    monkeypatch.setattr(module,'_run',lambda *a:pytest.fail('reuse must not reinstall'))
    assert module.install(project,accept_downloads=True)['inference_verified']


def test_bad_ocr_never_adopts(setup, monkeypatch):
    project,root=setup
    monkeypatch.setattr(module,'parse_pdf_configured_mineru',lambda *a,**kw: (_ for _ in ()).throw(ValueError('OCR failed')))
    with pytest.raises(ValueError,match='OCR failed'):module.install(project,accept_downloads=True)
    assert not (project/'.ac/mineru.json').exists()
    assert json.loads((root/'install-state.json').read_text())['stage']=='failed'


def test_unowned_directory_and_remote_configuration_preserved(setup):
    project,root=setup;root.mkdir();(root/'user.txt').write_text('keep')
    with pytest.raises(ValueError,match='not owned'):module.install(project,accept_downloads=True)
    assert (root/'user.txt').read_text()=='keep'
    config=project/'.ac/mineru.json';config.parent.mkdir(parents=True)
    config.write_text(json.dumps({'api_url':'https://example.test','executable':None,'token_env':None,'language':'en'}))
    with pytest.raises(ValueError,match='remote'):module.install(project,accept_downloads=True)


def test_failed_verification_preserves_existing_config(setup, monkeypatch):
    project,root=setup
    executable=project/'bin/mineru';executable.parent.mkdir(parents=True)
    executable.write_text('existing');executable.chmod(0o700)
    config=project/'.ac/mineru.json';config.parent.mkdir()
    original=json.dumps({'executable':str(executable),'api_url':None,'token_env':None,'language':'ch'})
    config.write_text(original)
    monkeypatch.setattr(module,'doctor_configured_mineru',lambda **kw: (_ for _ in ()).throw(ValueError('bad version')))
    with pytest.raises(ValueError,match='bad version'):module.install(project,accept_downloads=True)
    assert config.read_text()==original
