import json
from pathlib import Path
import sys
import subprocess

import pytest
from ac_llm import AcRuntimeEnvironment, HostRequest, HostResponseStatus
from alc_companion.host_broker import CompanionSourceHostBroker
from alc_companion.research_host import ResearchHost, ResearchBroker

ADAPTER = Path(__file__).resolve().parents[1] / 'plugins/alc/skills/alc/scripts/companion-research-host'


def env():
    return AcRuntimeEnvironment.capture()


def test_absent_host_does_not_spawn(monkeypatch):
    monkeypatch.delenv('ALC_COMPANION_RESEARCH_HOST', raising=False)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('unexpected process'))
    assert ResearchHost(env()).instructions == ''


def configure(monkeypatch, tmp_path):
    executable = tmp_path/'arc-paper'
    executable.write_text(f'#!{sys.executable}\nimport json,sys\nprint(json.dumps({{"status":"completed","argv":sys.argv[1:]}}))\n')
    executable.chmod(0o755)
    monkeypatch.setenv('ALC_COMPANION_RESEARCH_HOST', str(ADAPTER))
    monkeypatch.setenv('ALC_ARC_PAPER', str(executable))
    return ResearchHost(env())


def test_host_routes_research_without_weakening_source_broker(monkeypatch, tmp_path):
    host = configure(monkeypatch, tmp_path)
    assert 'INSPIRE' in host.instructions
    broker = ResearchBroker(CompanionSourceHostBroker(env()), host)
    request = HostRequest('r1', 'research '+json.dumps({'operation':'read','reference':'https://arxiv.org/html/2503.14738','ordinal':3}), 'Read evidence')
    response = broker.execute(request, workspace=tmp_path)
    assert response.status is HostResponseStatus.COMPLETED
    assert response.result['response']['argv'] == ['get-section','--reference','arXiv:2503.14738','--ordinal','3']
    assert broker.execute(HostRequest('r2','rm -rf anything','bad'),workspace=tmp_path).status is HostResponseStatus.REFUSED


@pytest.mark.parametrize('value', [
    {'operation':'read','reference':'/etc/passwd','ordinal':0},
    {'operation':'read','reference':'https://example.org','ordinal':True},
    {'operation':'search','query':'--help'},
    {'operation':'acquire','reference':'https://example.org','argv':['rm']},
    {'operation':'write','reference':'https://example.org'},
])
def test_adapter_rejects_undeclared_arguments(monkeypatch,tmp_path,value):
    host = configure(monkeypatch,tmp_path)
    response = host.execute(HostRequest('r','research '+json.dumps(value),'test'),workspace=tmp_path)
    assert 'error' in response.result
    assert 'response' not in response.result


def test_missing_arc_disables_capability(monkeypatch,tmp_path):
    monkeypatch.setenv('ALC_COMPANION_RESEARCH_HOST',str(ADAPTER))
    monkeypatch.setenv('ALC_ARC_PAPER',str(tmp_path/'missing'))
    assert ResearchHost(env()).instructions == ''


def test_failed_adapter_is_nonfatal(monkeypatch,tmp_path):
    host = configure(monkeypatch,tmp_path)
    Path(host.command)  # Host command is fixed before the model request.
    monkeypatch.setattr(subprocess,'run',lambda *a,**k: subprocess.CompletedProcess(a,1,b'',b'private error'))
    result = host.execute(HostRequest('r','research {}','test'),workspace=tmp_path)
    assert result.status is HostResponseStatus.REFUSED
    assert 'private error' not in str(result)


def test_nested_json_cannot_interrupt_research_broker(monkeypatch,tmp_path):
    host = configure(monkeypatch,tmp_path)
    nested = '{"x":' + '['*1500 + '0' + ']'*1500 + '}'
    response = host.execute(HostRequest('nested','research '+nested,'test'),workspace=tmp_path)
    assert response.status is HostResponseStatus.REFUSED


def test_research_broker_is_only_attached_to_guide_options(monkeypatch,tmp_path):
    from ac_llm import LLMExecutionOptions, LLMExecutionProfile, ModelSelection
    from alc_companion.build import _guide_llm_options
    host = configure(monkeypatch,tmp_path)
    source = CompanionSourceHostBroker(env())
    original = LLMExecutionOptions(profile=LLMExecutionProfile.LOCAL_APP,host_broker=source)
    guide = _guide_llm_options(original,ModelSelection(provider='codex',model='test'),host)
    assert isinstance(guide.host_broker,ResearchBroker)
    assert original.host_broker is source
    monkeypatch.setenv('ALC_ARC_PAPER',str(tmp_path/'missing'))
    disabled = _guide_llm_options(original,ModelSelection(provider='codex',model='test'),ResearchHost(env()))
    assert disabled.host_broker is source

@pytest.mark.parametrize('constant',['NaN','Infinity','-Infinity','1e999','-1e999'])
def test_nonfinite_adapter_response_is_nonfatal(monkeypatch,tmp_path,constant):
    host = configure(monkeypatch,tmp_path)
    monkeypatch.setattr(subprocess,'run',lambda *a,**k: subprocess.CompletedProcess(a,0,('{"value":'+constant+'}').encode(),b''))
    response = host.execute(HostRequest('r','research {}','test'),workspace=tmp_path)
    assert response.status is HostResponseStatus.REFUSED


@pytest.mark.parametrize('reference', ['https://127.0.0.1/admin', 'https://[::1]/admin', 'https://intranet/admin', 'https://example.org/redirect', 'https://arxiv.org.evil.test/abs/2503.14738'])
@pytest.mark.parametrize('operation', ['acquire', 'contents', 'read'])
def test_arc_acquire_rejects_arbitrary_network_destinations(monkeypatch, tmp_path, reference, operation):
    host = configure(monkeypatch, tmp_path)
    response = host.execute(HostRequest('r', 'research '+json.dumps({'operation':operation,'reference':reference, **({'ordinal':0} if operation == 'read' else {})}), 'test'), workspace=tmp_path)
    assert 'response' not in response.result


@pytest.mark.parametrize('reference,identifier', [('arXiv:2503.14738','2503.14738'), ('https://arxiv.org/html/2503.14738','2503.14738'), ('https://arxiv.org/pdf/hep-ph/0607187v2.pdf','hep-ph/0607187v2')])
def test_arc_acquire_uses_identifier_not_model_url(monkeypatch, tmp_path, reference, identifier):
    host = configure(monkeypatch, tmp_path)
    response = host.execute(HostRequest('r', 'research '+json.dumps({'operation':'acquire','reference':reference}), 'test'), workspace=tmp_path)
    assert response.result['response']['argv'] == ['acquire-reference','--arxiv-id',identifier]
