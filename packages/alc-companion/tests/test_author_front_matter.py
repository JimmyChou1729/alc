from __future__ import annotations

import hashlib
import json

import pytest
from ac_document import (
    RichDocumentParserService, SourceFormat, SourceOrigin, SourceOriginKind,
    SourceRepository,
)
from ac_jobs import ImmutableArtifactStore, RunStatus
from ac_llm import HostAuthority, HostCoordinator, HostTaskService, LLMExecutionOptions, ModelSelection
from alc_companion.build import _structured_author_evidence
from alc_companion.generation_validation import CompanionContentError, validate_author_identity
from alc_companion.prompts import AUTHOR_IDENTITY_PROMPT_VERSION, author_identity_prompt
from alc_companion.request_contracts import CompanionBuildRequest, CompanionExecutionOptions, CompanionGenerationRecipe
from alc_companion.service import CompanionService
from alc_companion.source_identity import resolve_document_identity


def _source(tmp_path, *, authors=True):
    byline = '''<div class="ltx_authors" id="authors">
        <span class="ltx_creator ltx_role_author"><span class="ltx_personname">Ada Lovelace</span></span>
        <span class="ltx_creator ltx_role_author"><span class="ltx_personname">Grace Hopper</span></span>
    </div>''' if authors else ''
    repo = SourceRepository(tmp_path / 'paper')
    artifact = repo.store_bytes(
        f'<article><h1>Paper</h1>{byline}<p>We explain an algorithm.</p></article>'.encode(),
        source_format=SourceFormat.HTML,
        origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT, locator='paper.html'),
    )
    return RichDocumentParserService(repo).parse_source(artifact)


def test_structured_author_candidates_preserve_order_and_provenance(tmp_path):
    source = _source(tmp_path)
    identity = resolve_document_identity(source)
    assert identity.candidate_authors == ('Ada Lovelace', 'Grace Hopper')
    assert identity.author_basis == 'metadata.source_front_matter'
    assert resolve_document_identity(source, include_front_matter=False).candidate_authors == ()
    evidence = _structured_author_evidence(source)
    original = source.metadata['source_front_matter']['entries'][0]
    assert evidence[0]['front_matter_id'] == original['front_matter_id']
    assert evidence[0]['locator'] == original['locator']
    assert 'block_id' not in evidence[0]
    assert _structured_author_evidence(source, max_bytes=30) == ()


def test_missing_authors_remain_unknown(tmp_path):
    source = _source(tmp_path, authors=False)
    assert resolve_document_identity(source).candidate_authors == ()
    assert _structured_author_evidence(source) == ()
    uncertain = {'authors': [], 'confidence': 'low', 'basis': 'No authored byline.',
                 'anchor_block_ids': [], 'anchor_front_matter_ids': []}
    assert validate_author_identity(uncertain, block_ids=[], front_matter_ids=[]) == uncertain
    with pytest.raises(CompanionContentError, match='source anchors'):
        validate_author_identity({**uncertain, 'authors': ['Guessed Author'], 'confidence': 'high'},
                                 block_ids=[], front_matter_ids=[])


@pytest.mark.parametrize('bad_anchor', ['made-up', 'body-block'])
def test_metadata_anchors_are_not_guessed_or_interchangeable(bad_anchor):
    output = {'authors': ['Ada'], 'confidence': 'high', 'basis': 'Source byline.',
              'anchor_block_ids': [], 'anchor_front_matter_ids': [bad_anchor]}
    with pytest.raises(CompanionContentError, match='supplied metadata IDs'):
        validate_author_identity(output, block_ids=['body-block'], front_matter_ids=['front-1'])
    with pytest.raises(CompanionContentError, match='existing block IDs'):
        validate_author_identity({**output, 'anchor_block_ids': ['front-1'], 'anchor_front_matter_ids': []},
                                 block_ids=['body-block'], front_matter_ids=['front-1'])


@pytest.mark.parametrize('version,digest', [
    ('v3', 'd8ae8352a51ad630a2da065d3b1c5334fca5fce5e9fa2d85b1739ba795ec20fd'),
    ('v4', 'e5e901f89fdcc7c263bb1b54ed8ab39130abaf551f61bc1183cdda8a72c9699e'),
])
def test_historical_author_prompts_keep_exact_pending_request_bytes(version, digest):
    prompt = author_identity_prompt(
        title='Paper', auto_candidates=[], front_matter_evidence=[{'block_id': 'b1', 'text': 'Body.'}],
        structured_front_matter=[{'front_matter_id': 'new-evidence'}],
        version='alc.companion.author-identity-prompt.' + version,
    )
    assert hashlib.sha256(prompt.encode()).hexdigest() == digest


@pytest.mark.parametrize('version', [AUTHOR_IDENTITY_PROMPT_VERSION, 'alc.companion.author-identity-prompt.v4'])
def test_host_author_evidence_submit_and_owner_resume(tmp_path, version):
    source = _source(tmp_path)
    service = CompanionService(tmp_path / 'jobs')
    recipe = CompanionGenerationRecipe(model=ModelSelection(provider='host'), author_identity_prompt=version)
    prepared = service.prepare(CompanionBuildRequest(source, target_language='zh-CN'), recipe=recipe)
    execution = CompanionExecutionOptions(
        workers=1, pipeline_chapters=False, document_cache_root=tmp_path / 'paper',
        llm=LLMExecutionOptions(host_coordinator=HostCoordinator('test'), host_authority=HostAuthority.UNRESTRICTED),
    )
    first = service.execute(prepared.run_id, execution=execution)
    assert first.status is RunStatus.PAUSED, first.error
    details = first.awaiting.details
    location = dict(run_root=details['run_root'], run_id=details['run_id'])
    host = HostTaskService()
    task = host.export(**location, task_id=details['host_task_id'])
    assert task['request']['task_prompt'].startswith('Contract: ' + version)
    payload = json.loads(task['request']['task_prompt'].split('Input JSON:\n', 1)[1])
    if version == AUTHOR_IDENTITY_PROMPT_VERSION:
        evidence = payload['structured_front_matter'][0]
        assert [a['name'] for a in evidence['authors']] == ['Ada Lovelace', 'Grace Hopper']
        assert evidence['locator']['selector'] == '#authors'
        output = {'authors': ['Ada Lovelace', 'Grace Hopper'], 'confidence': 'high',
                  'basis': 'Authored HTML byline.', 'anchor_block_ids': [],
                  'anchor_front_matter_ids': [evidence['front_matter_id']]}
    else:
        assert 'structured_front_matter' not in payload
        assert payload['auto_candidates'] == []
        output = {'authors': [], 'confidence': 'low', 'basis': 'No visible byline in legacy evidence.', 'anchor_block_ids': []}
    # Reconstruct the owning service as after an interrupted host turn.
    service = CompanionService(tmp_path / 'jobs')
    pending = service.resume(prepared.run_id, execution=execution)
    assert pending.awaiting.details['host_task_id'] == task['task_id']
    assert host.export(**location, task_id=task['task_id'])['request_sha256'] == task['request_sha256']
    host.submit(**location, response={
        'schema_version': 'ac.llm.host_response.v1', 'task_id': task['task_id'],
        'request_sha256': task['request_sha256'],
        'actor': {'actor_id': 'fixture', 'kind': 'fake', 'context_id': task['task_id']}, 'output': output,
    })
    resumed = service.resume(prepared.run_id, execution=execution)
    assert resumed.status is RunStatus.PAUSED, resumed.error
    assert resumed.awaiting.details['host_task_id'] != task['task_id']
    store = ImmutableArtifactStore(service.repository.run_directory(prepared.run_id))
    saved = json.loads(store.read_bytes(store.find('identity/authors')))
    assert saved == output
