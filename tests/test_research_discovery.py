from pathlib import Path
import runpy
import subprocess
import time

import pytest
from alc_web.runtime import research_host_environment

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'plugins/alc/skills/alc/scripts/companion-research-host'
BUNDLED = ROOT/'packages/alc-web/src/alc_web/host_adapters/companion-research-host'


def adapter(monkeypatch):
    for key in ('ALC_ARC_PAPER','ALC_RESEARCH_HOST_BINDING'):
        monkeypatch.delenv(key,raising=False)
    values = runpy.run_path(str(SCRIPT))
    return values['runtime'].__globals__


def test_bundled_adapter_matches_skill_source():
    assert BUNDLED.read_bytes() == SCRIPT.read_bytes()


def test_web_default_and_explicit_disable():
    empty = {}
    result = research_host_environment(empty)
    assert Path(result['ALC_COMPANION_RESEARCH_HOST']).is_file()
    assert empty == {}
    assert research_host_environment({'ALC_COMPANION_RESEARCH_HOST':''})['ALC_COMPANION_RESEARCH_HOST'] == ''
    assert research_host_environment({'ALC_COMPANION_RESEARCH_HOST':'/custom'})['ALC_COMPANION_RESEARCH_HOST'] == '/custom'


def test_absent_arc_falls_back_without_install(monkeypatch):
    a=adapter(monkeypatch)
    monkeypatch.setattr(a['shutil'],'which',lambda _:None)
    a['_installed_skills']=lambda _:iter(())
    monkeypatch.setattr(a['subprocess'],'run',lambda *args,**kwargs:pytest.fail('Unexpected executable'))
    assert a['runtime']() is None


def test_path_capability_is_preferred(monkeypatch,tmp_path):
    a=adapter(monkeypatch);binary=tmp_path/'bin/arc-paper';binary.parent.mkdir();binary.touch()
    monkeypatch.setattr(a['shutil'],'which',lambda name:str(binary) if name=='arc-paper' else None)
    calls=[]
    a['_capable']=lambda cmd,deadline:calls.append(cmd) or True
    a['_installed_skills']=lambda _:pytest.fail('Registry should not be needed')
    assert a['runtime']()==[str(binary)]
    assert calls==[[str(binary)]]


def test_plugin_wrapper_uses_doctor_before_command(monkeypatch,tmp_path):
    a=adapter(monkeypatch);binary=tmp_path/'bin/arc-paper';binary.parent.mkdir();binary.touch()
    skill=tmp_path/'skills/arc';(skill/'scripts').mkdir(parents=True);(skill/'scripts/arc-runtime').touch()
    monkeypatch.setattr(a['shutil'],'which',lambda _:str(binary))
    a['_ready_skill']=lambda found,deadline:None
    a['_installed_skills']=lambda _:iter(())
    a['_capable']=lambda *args:pytest.fail('Unready wrapper must not execute')
    assert a['runtime']() is None


@pytest.mark.parametrize('enabled,installed,version,expected',[(True,True,'2.0.3',1),(False,True,'2.0.3',0),(True,False,'2.0.3',0),(True,True,'../other',0)])
def test_only_exact_enabled_installed_plugin(monkeypatch,tmp_path,enabled,installed,version,expected):
    a=adapter(monkeypatch);monkeypatch.setenv('CODEX_HOME',str(tmp_path))
    monkeypatch.setattr(a['shutil'],'which',lambda _: '/bin/codex')
    monkeypatch.setattr(a['Path'],'home',classmethod(lambda cls:tmp_path/'empty-home'))
    a['_run_json']=lambda *args:{'installed':[{'name':'arc','installed':installed,'enabled':enabled,'marketplaceName':'official','version':version}]}
    paths=list(a['_installed_skills'](time.monotonic()+8))
    assert len(paths)==expected
    if expected:assert paths==[tmp_path/'plugins/cache/official/arc/2.0.3/skills/arc']


@pytest.mark.parametrize('ready',[False,True])
def test_ready_runtime_only(monkeypatch,tmp_path,ready):
    a=adapter(monkeypatch);skill=tmp_path/'skill';(skill/'scripts').mkdir(parents=True);(skill/'scripts/arc-runtime').touch()
    runtime=tmp_path/'runtime with spaces';(runtime/'venv/bin').mkdir(parents=True);(runtime/'venv/bin/arc-paper').touch()
    calls=[]
    a['_run_json']=lambda argv,deadline:calls.append(argv) or {'ready':ready,'runtime':str(runtime)}
    a['_capable']=lambda *args:True
    result=a['_ready_skill'](skill,time.monotonic()+8)
    assert bool(result)==ready
    assert calls==[[str(skill/'scripts/arc-runtime'),'doctor']]


def test_old_command_and_timeout_fall_back(monkeypatch):
    a=adapter(monkeypatch)
    monkeypatch.setattr(a['subprocess'],'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,2,b'',b''))
    assert not a['_capable'](['/bin/arc-paper'],time.monotonic()+8)
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args,1)
    monkeypatch.setattr(a['subprocess'],'run',timeout)
    assert a['_run_json'](['/bin/codex','plugin','list','--json'],time.monotonic()+8) is None


def test_external_runtime_does_not_inherit_python_overlay(monkeypatch):
    a=adapter(monkeypatch);monkeypatch.setenv('PYTHONPATH','/local/web/overlay');monkeypatch.setenv('PYTHONHOME','/wrong')
    assert 'PYTHONPATH' not in a['_process_environment']()
    assert 'PYTHONHOME' not in a['_process_environment']()


@pytest.mark.parametrize('enabled',[True,False])
def test_cached_path_wrapper_respects_registry_even_through_symlink(monkeypatch,tmp_path,enabled):
    a=adapter(monkeypatch);home=tmp_path/'codex';monkeypatch.setenv('CODEX_HOME',str(home))
    plugin=home/'plugins/cache/test/arc/2.0.3';skill=plugin/'skills/arc'
    (skill/'scripts').mkdir(parents=True);(skill/'scripts/arc-runtime').touch()
    binary=plugin/'bin/arc-paper';binary.parent.mkdir();binary.touch()
    link=tmp_path/'arc-paper';link.symlink_to(binary)
    monkeypatch.setattr(a['shutil'],'which',lambda name:str(link) if name=='arc-paper' else None)
    a['_installed_skills']=lambda _:iter([skill] if enabled else [])
    calls=[];a['_ready_skill']=lambda *args:calls.append(args) or ['/ready/arc-paper']
    assert bool(a['runtime']())==enabled
    assert bool(calls)==enabled


def test_doctor_does_not_inherit_alc_checkout_override(monkeypatch):
    a=adapter(monkeypatch)
    for key in ('AC_INSTALL_SOURCE','AC_PRODUCT_REPO_ROOT','AC_FOUNDATION_REPO_ROOT'):
        monkeypatch.setenv(key,'ALC-specific')
        assert key not in a['_process_environment']()


@pytest.mark.parametrize('enabled',[True,False])
def test_claude_user_plugin_requires_enabled_registration(monkeypatch,tmp_path,enabled):
    import json
    a=adapter(monkeypatch);monkeypatch.setattr(a['Path'],'home',classmethod(lambda cls:tmp_path))
    monkeypatch.setattr(a['shutil'],'which',lambda _:None)
    home=tmp_path/'.claude';(home/'plugins').mkdir(parents=True)
    installed=home/'plugins/cache/market/arc/2.0.3'
    (home/'plugins/installed_plugins.json').write_text(json.dumps({'plugins':{'arc@market':[{'scope':'user','installPath':str(installed)}]}}))
    (home/'settings.json').write_text(json.dumps({'enabledPlugins':{'arc@market':enabled}}))
    found=list(a['_installed_skills'](time.monotonic()+8))
    assert found==([installed/'skills/arc'] if enabled else [])


def test_private_python_does_not_change_arc_doctor_fingerprint(monkeypatch,tmp_path):
    a=adapter(monkeypatch);private=tmp_path/'alc-venv'
    monkeypatch.setattr(a['sys'],'prefix',str(private));monkeypatch.setattr(a['sys'],'base_prefix',str(tmp_path/'python'))
    monkeypatch.setenv('PATH',str(private/'bin')+a['os'].pathsep+'/usr/bin')
    assert a['_process_environment']()['PATH']=='/usr/bin'


def test_plugin_entrypoint_provides_host_without_modifying_generated_launcher():
    wrapper=(ROOT/'plugins/alc/bin/alc-companion').read_text()
    assert 'export ALC_COMPANION_RESEARCH_HOST=' in wrapper
    assert 'ALC_ARC_PAPER=' not in wrapper
    launcher=(ROOT/'plugins/alc/skills/alc/scripts/alc-runtime').read_text()
    assert 'ALC_COMPANION_RESEARCH_HOST' not in launcher
