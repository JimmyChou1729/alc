#!/usr/bin/env python3
"""Cold-install a portable ALC ZIP, then check Host protocol and Reader delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from plugin_bundle import read_zip, validate_files

PROBE = r'''
import importlib, json, sys
from pathlib import Path
from ac_llm import HostCoordinator, HostTaskService, JsonOutput, LLMClient, LLMCompleted, LLMPaused, LLMRequest, ModelSelection
root = Path(sys.argv[1])
for name in ('ac_jobs', 'ac_llm', 'ac_document', 'ac_proposer_reviewer', 'alc_render', 'alc_translate', 'alc_companion', 'alc_ocr_proofread'):
    path = Path(importlib.import_module(name).__file__).resolve()
    assert path.is_relative_to(Path(sys.prefix).resolve()), (name, str(path))
from alc_companion.request_contracts import CompanionGenerationRecipe, freeze_generation_recipe
selection = freeze_generation_recipe(CompanionGenerationRecipe()).model
assert selection.provider == 'host' and selection.model == 'inherit' and selection.reasoning_effort is None
client, host = LLMClient(), HostTaskService()
where = dict(run_root=root / 'host-runs', run_id='offline-protocol')
request = LLMRequest('fixture', 'Offline fixture: return answer 42.', JsonOutput({'type':'object', 'properties':{'answer':{'const':42}}, 'required':['answer'], 'additionalProperties':False}), ModelSelection('host'))
paused = client.generate(request, **where)
assert isinstance(paused.outcome, LLMPaused)
task = host.export(**where, task_id=host.pending(**where)[0]['task_id'])
response = {'schema_version':'ac.llm.host_response.v1', 'task_id':task['task_id'], 'request_sha256':task['request_sha256'], 'actor':{'actor_id':'cold-fixture','kind':'fake'}, 'output':{'schema_version':'ac.llm.host_turn.v1','state':'complete','result':{'answer':42},'host_request':None}}
host.submit(**where, response=response)
assert isinstance(client.resume(**where).outcome, LLMCompleted)
assert host.submit(**where,response=response)['reused']
assert isinstance(client.resume(**where).outcome, LLMCompleted)
# Exercise the product boundary too: the coordinator may only use public replies.
import contextlib, io
from alc_translate.cli import main as translate
from ac_llm.cli import main as llm
def invoke(main, args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(args)
    value = json.loads(output.getvalue())
    assert code in (0, 1) and value['status'] != 'failed', value
    return value
source = root / 'handoff-source.md'
source.write_text('# Energy\n\nEnergy is conserved: $E=mc^2$.\n')
project = root / 'translation-handoff'
reply = invoke(translate, ['detect-language', str(source), '--project-dir', str(project), '--target-language', 'zh-CN', '--provider', 'host'])
assert reply['status'] == 'paused'
details = reply['resume']['details']
status = invoke(translate, ['status', '--project-dir', str(project)])
assert status['data']['run']['resume']['details'] == details
location = ['--run-root', details['run_root'], '--run-id', details['run_id']]
task = invoke(llm, ['host-export', *location, '--task-id', details['host_task_id']])['data']['task']
response = root / 'language-response.json'
response.write_text(json.dumps({'schema_version':'ac.llm.host_response.v1', 'task_id':task['task_id'], 'request_sha256':task['request_sha256'], 'actor':{'actor_id':'cold-fixture','kind':'fake'}, 'output':{'schema_version':'ac.llm.host_turn.v1','state':'complete','result':{'language_tag':'en','classification':'known','confidence':0.99},'host_request':None}}))
invoke(llm, ['host-submit', *location, '--response', str(response)])
completed = invoke(translate, ['resume', '--project-dir', str(project)])
assert completed['status'] == 'completed' and completed['run']['id'] == reply['run']['id']
print(json.dumps({'protocol_passed':True, 'translation_cli_handoff_passed':True, 'source_imports_verified':True, 'model_calls':0, 'ocr_accuracy_verified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.expanduser().resolve()
    if root.exists():
        parser.error('output-dir must not exist; use fresh state for a cold check')
    files = read_zip(args.zip)
    validation = validate_files(files, 'public-skills')
    if not validation['valid']:
        print(json.dumps(validation)); return 1
    root.mkdir(parents=True)
    plugin = root / 'plugin'
    for relative, data in files.items():
        path = plugin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if relative.startswith('skills/alc/scripts/') and (data.startswith(b'#!') or relative.endswith('.py')):
            path.chmod(0o755)
    launcher = ['bash', str(plugin / 'skills/alc/scripts/alc-runtime')]
    env = dict(os.environ)
    for name in ('AC_FOUNDATION_REPO_ROOT','AC_PRODUCT_REPO_ROOT','ALC_REQUIRE_REPO_ROOT','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','AC_RUNTIME_SOURCES_FILE','AC_RUNTIME_CONSTRAINTS_FILE','AC_LLM_PROVIDER_CONFIG'):
        env.pop(name, None)
    env.update(AC_INSTALL_SOURCE='git', AC_HOME=str(root/'ac'), AC_RUNTIME_HOME=str(root/'runtimes'),
               AC_DOCUMENT_CACHE=str(root/'document-cache'), ALC_CATALOG_DIR=str(root/'catalog'),
               AC_INSTALL_PYTHON_BIN=sys.executable, PYTHONDONTWRITEBYTECODE='1',
               AC_LLM_HOST_COORDINATOR=json.dumps({'coordinator_id':'cold-fixture','default_provider':'host','native_fallback':False}))
    report = {'schema_version':'alc.cold_plugin.v1','zip_sha256':hashlib.sha256(args.zip.read_bytes()).hexdigest(),
              'passed':False,'commands':[], 'real_host_tested':False,'ocr_accuracy_verified':False}
    def command(label, argv, expected=0):
        result = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=900)
        (root/f'{label}.stdout').write_text(result.stdout)
        (root/f'{label}.stderr').write_text(result.stderr)
        report['commands'].append({'name':label,'exit_code':result.returncode})
        if result.returncode != expected:
            raise RuntimeError(f'{label} failed; see retained stdout/stderr')
        return result.stdout
    try:
        before = json.loads(command('doctor-before', [*launcher,'doctor'], expected=1))
        assert before['ready'] is False and not (root/'runtimes').exists()
        command('setup', [*launcher,'setup'])
        doctor = json.loads(command('doctor-after', [*launcher,'doctor']))
        assert doctor['ready'] and doctor['source_mode']=='git'
        report['runtime'] = doctor
        marker = Path(doctor['runtime'])/'install.ok'
        original_marker = marker.read_bytes()
        command('setup-repeat', [*launcher,'setup'])
        command('setup-retry-ready', [*launcher,'setup','--retry'])
        assert marker.read_bytes()==original_marker
        command('host-doctor', [*launcher,'ac-llm','doctor','--provider','host','--environment'])
        command('companion-launcher', ['bash', str(plugin/'skills/alc/scripts/alc-companion'),'--help'])
        probe = root/'probe.py'; probe.write_text(PROBE)
        report['host'] = json.loads(command('host-protocol', [*launcher,'script',str(probe),str(root)]))
        source = root/'source.html'
        (root/'figure.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"><rect width="64" height="32" fill="blue"/></svg>')
        source.write_text('<html><body><h1>原文 Reader 验证</h1><p>This is a deterministic source fixture, not generated research.</p>'
                          '<p>公式 <math alttext="E=mc^2"></math> 与中文应完整保留。</p>'
                          '<table><caption> </caption><tr><td>1.25</td><td>kg</td></tr></table>'
                          '<figure><img src="figure.svg" alt="Original fixture"><figcaption></figcaption></figure></body></html>')
        publication = root/'publication'
        command('document-export', [*launcher,'ac-document','export-rich-document',str(source),'--output-dir',str(publication)])
        command('reader-compose', [*launcher,'alc-render','compose','--source',str(publication/'rich-source.json'),'--metadata',str(publication/'metadata.json'),'--output',str(publication/'publication.json')])
        html = publication/'reader.html'
        command('reader-render', [*launcher,'alc-render','render','--publication',str(publication/'publication.json'),'--html',str(html)])
        command('reader-validate', [*launcher,'alc-render','validate','--publication',str(publication/'publication.json'),'--html',str(html)])
        assert html.is_file() and html.stat().st_size>1000
        report.update(passed=True,reader=str(html),reader_sha256=hashlib.sha256(html.read_bytes()).hexdigest())
    except Exception as exc:
        report.update(error_type=type(exc).__name__,error=str(exc))
    (root/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
