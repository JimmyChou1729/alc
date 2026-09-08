import json
import subprocess

import pytest
from ac_jobs import RunContext, RunRepository, RunSpec
from alc_companion.chapter_evidence import ChapterEvidenceError, evidence_policy, preload_chapter
from ac_llm import AcRuntimeEnvironment

def _environment():
    return AcRuntimeEnvironment({"PATH": "/usr/bin:/bin", "AC_HOME": None, "AC_RUNTIME_HOME": None, "AC_DOCUMENT_CACHE": None})

def _read_commands(tmp_path):
    def part(ref, start, end, parts):
        return {"argv": ["ac-document", "read-cached-source-range", "--document-ref", ref, "--cache-root", str(tmp_path), "--text-only", str(start), str(end)], "part_numbers": parts}
    return {"source": [part("source",1,1,[1]), part("source",2,2,[2]), part("source",1,2,[1,2])], "translation": {"parts": [part("translation",1,2,[1,2])]}}
from alc_companion.host_broker import CompanionSourceHostBroker


def setup(tmp_path):
    repo = RunRepository(tmp_path / 'jobs')
    context = RunContext(repo, repo.create(RunSpec('evidence-run', 'handler', {})), resume_input=None)
    broker = CompanionSourceHostBroker(_environment())
    broker.bind_context(context)
    commands = _read_commands(tmp_path)
    for descriptors in (commands['source'], commands['translation']['parts']):
        descriptors[-1]['command_id'] = 'complete-current-chapter'
    broker.register_commands(commands)
    return context, broker, commands


def test_evidence_is_complete_bound_and_reused(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, argv[3].encode(), b'')
    monkeypatch.setattr(subprocess, 'run', run)
    value = preload_chapter(context, broker, 'one', commands)
    assert value['original']['text'] == 'source'
    assert value['translation']['text'] == 'translation'
    assert len(calls) == 2
    assert preload_chapter(context, broker, 'one', commands) == value
    assert len(calls) == 2
    with pytest.raises(ValueError):
        broker.validate_reads(commands, require_complete=True)
    changed = json.loads(json.dumps(commands))
    changed['translation']['parts'][0]['argv'][3] = 'new-translation'
    broker.register_commands(changed)
    assert preload_chapter(context, broker, 'one', changed)['binding'] != value['binding']
    assert len(calls) == 4


def test_complete_truncation_falls_back_to_ordered_parts(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    commands['translation']['parts'][:0] = commands['source'][:2]
    broker.register_commands(commands)
    def run(argv, **kw):
        body = b'x'*64001 if tuple(argv[-2:]) == ('1','2') else ("part"+argv[-1]).encode()
        return subprocess.CompletedProcess(argv, 0, body, b'')
    monkeypatch.setattr(subprocess, 'run', run)
    evidence = preload_chapter(context, broker, 'one', commands)
    assert evidence['original']['text'] == 'part1\npart2'
    assert evidence['translation']['text'] == 'part1\npart2'
    assert 'argv' not in str(evidence['original']['locations'])


def test_failed_reads_are_retryable_without_cached_null(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 1, b'', b''))
    with pytest.raises(ChapterEvidenceError, match='local document runtime'):
        preload_chapter(context, broker, 'one', commands)
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'ok', b''))
    assert preload_chapter(context, broker, 'one', commands)['translation']['text'] == 'ok'


def test_combined_budget_checked_before_guide(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    monkeypatch.setattr('alc_companion.chapter_evidence._MAX_EVIDENCE_BYTES', 1000)
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'x'*600, b''))
    with pytest.raises(ChapterEvidenceError) as exc:
        preload_chapter(context, broker, 'one', commands)
    assert exc.value.code == 'chapter_evidence_too_large'


def test_large_descriptor_lists_do_not_inflate_evidence(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    commands['source'] *= 300
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'ok', b''))
    value = preload_chapter(context, broker, 'one', commands)
    assert len(json.dumps(value)) < 2000


@pytest.mark.parametrize('legacy', [False, True])
def test_policy_is_frozen_for_resume(tmp_path, legacy):
    context, _, _ = setup(tmp_path)
    if legacy:
        context.artifacts.publish_json('source/model-index', {})
    assert evidence_policy(context, True) is (not legacy)
    assert evidence_policy(context, False) is (not legacy)


def test_legacy_null_retries_only_before_guide_request_is_frozen(monkeypatch, tmp_path):
    import hashlib
    context, broker, commands = setup(tmp_path)
    binding = hashlib.sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest()
    context.artifacts.publish_json(f'chapter-evidence/one/{binding}', {'evidence': None})
    context.artifacts.publish_json('proposer-reviewer/scopes/chapter-one/request', {})
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kw: pytest.fail('Frozen request must not change'))
    assert preload_chapter(context, broker, 'one', commands) is None
    context.artifacts.publish_json(f'chapter-evidence/two/{binding}', {'evidence': None})
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'ok', b''))
    assert preload_chapter(context, broker, 'two', commands)['original']['text'] == 'ok'


def test_larger_range_replaces_earlier_partial_coverage(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    commands['source'][-1]['command_id'] = 'section-complete'
    def run(argv, **kw):
        if argv[3] == 'source' and tuple(argv[-2:]) == ('2','2'):
            return subprocess.CompletedProcess(argv, 1, b'', b'')
        return subprocess.CompletedProcess(argv, 0, b'whole' if tuple(argv[-2:]) == ('1','2') else b'first', b'')
    monkeypatch.setattr(subprocess, 'run', run)
    evidence = preload_chapter(context, broker, 'one', commands)
    assert evidence['original']['text'] == 'whole'
    assert len(evidence['original']['locations']) == 1


def test_oversized_individual_parts_report_size_error(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'x'*64001, b''))
    with pytest.raises(ChapterEvidenceError) as exc:
        preload_chapter(context, broker, 'one', commands)
    assert exc.value.code == 'chapter_evidence_too_large'


def test_global_frozen_null_request_is_preserved(monkeypatch, tmp_path):
    import hashlib
    context, broker, commands = setup(tmp_path)
    binding = hashlib.sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest()
    context.artifacts.publish_json(f'chapter-evidence/one/{binding}', {'evidence': None})
    context.artifacts.publish_json('proposer-reviewer/request', {})
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kw: pytest.fail('Frozen request must not change'))
    assert preload_chapter(context, broker, 'one', commands) is None


def test_same_language_has_explicit_translation_not_required(monkeypatch, tmp_path):
    context, broker, commands = setup(tmp_path)
    commands['translation'] = {'availability': 'not_required', 'parts': []}
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b'original', b''))
    value = preload_chapter(context, broker, 'one', commands)
    assert value['original']['text'] == 'original'
    assert value['translation']['availability'] == 'not_required'


def test_evidence_instruction_keeps_v1_request_bytes():
    from alc_companion.chapter_evidence import EVIDENCE_INSTRUCTION, EVIDENCE_INSTRUCTION_V2, evidence_instruction
    assert evidence_instruction({'verified_chapter_evidence': {'contract': 'alc.companion.chapter-evidence.v1'}}) == EVIDENCE_INSTRUCTION
    assert evidence_instruction({'verified_chapter_evidence': {'contract': 'alc.companion.chapter-evidence.v2'}}) == EVIDENCE_INSTRUCTION_V2
    assert evidence_instruction({}) == ''
