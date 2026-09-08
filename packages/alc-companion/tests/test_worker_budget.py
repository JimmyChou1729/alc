import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from types import SimpleNamespace

import pytest
from ac_document import RichDocumentParserService, SourceFormat, SourceOrigin, SourceOriginKind, SourceRepository
from ac_jobs import RunContext, RunRepository, RunSpec
from ac_llm import LLMCompleted, ModelSelection
from alc_translate import GlossaryResult, LanguageResult
from alc_translate.prompts import TEXT_SLOT_RESULT_SCHEMA
from alc_companion.build import CompanionBuildHandler
from alc_companion.concurrency import BudgetedTaskService
from alc_companion.request_contracts import CompanionBuildRequest, CompanionExecutionOptions, CompanionGenerationRecipe


class WindowTasks:
    def __init__(self, expected_overlap):
        self.lock = Lock()
        self.barrier = Barrier(expected_overlap)
        self.expected_overlap = expected_overlap
        self.active = self.peak = self.calls = 0
        self.ids = []

    def execute_or_resume(self, context, request, **kwargs):
        with self.lock:
            self.calls += 1
            call = self.calls
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.ids.append(request.task_id)
        try:
            if call <= self.expected_overlap:
                self.barrier.wait(timeout=5)
            Event().wait(.02)
            if request.prompt == 'guide':
                return 'guide-done'
            payload = json.loads(request.prompt.split('Input JSON:\n', 1)[1])
            translations = {}
            for block in payload['blocks']:
                slots = {part['slot_id']: part['text'] for part in block['content']['parts'] if part['kind'] == 'text_slot'}
                translations[block['block_id']] = {'text_slots': slots}
            return LLMCompleted({'schema_version': TEXT_SLOT_RESULT_SCHEMA, 'translations': translations}, 'fake', 'fake', None, None)
        finally:
            with self.lock:
                self.active -= 1


def inputs(tmp_path, count):
    repository = SourceRepository(tmp_path / 'cache')
    html = '<article>' + ''.join(f'<p id="p{i}">Block {i} '+('ordinary source prose ' * 850)+'</p>' for i in range(count)) + '</article>'
    artifact = repository.store_bytes(html.encode(), source_format=SourceFormat.HTML, origin=SourceOrigin(SourceOriginKind.LOCAL_IMPORT))
    source = RichDocumentParserService(repository).parse_source(artifact)
    runs = RunRepository(tmp_path / 'runs')
    context = RunContext(runs, runs.create(RunSpec('budget-test', 'test', {})), resume_input=None)
    language = LanguageResult(source.document_digest, source.source.artifact_digest, 'en', 'known', 1., 'zh-CN', 'enabled').to_document()
    glossary = GlossaryResult(source.document_digest, source.source.artifact_digest, 'zh-CN', 1, 'd' * 64, ()).to_document()
    return source, context, language, glossary


def translate(handler, context, source, language, glossary, blocks, prefix):
    return handler.translation_adapter.translate_blocks(context, source, block_ids=blocks, language=language, glossary=glossary, target_language='zh-CN', model=ModelSelection(), execution=handler.llm_options, resume_input=None, artifact_prefix=prefix)


@pytest.mark.parametrize('workers', [1, 2, 8])
def test_real_single_chapter_translation_windows_use_worker_budget(tmp_path, workers):
    source, context, language, glossary = inputs(tmp_path, 4)
    tasks = WindowTasks(workers)
    request = CompanionBuildRequest(source, target_language='zh-CN')
    recipe = CompanionGenerationRecipe(review_rounds=0)
    handler = CompanionBuildHandler(request, recipe, execution=CompanionExecutionOptions(workers=workers), task_service=tasks)
    blocks = [b.block_id for b in source.blocks]
    result = translate(handler, context, source, language, glossary, blocks, 'chapter-one')
    assert isinstance(result, dict)
    assert tasks.calls == 8
    assert len(set(tasks.ids)) == 8
    assert tasks.peak == workers
    resumed = CompanionBuildHandler(request, recipe, execution=CompanionExecutionOptions(workers=2 if workers == 1 else 1), task_service=tasks)
    assert resumed.semantic_input() == handler.semantic_input()
    assert translate(resumed, context, source, language, glossary, blocks, 'chapter-one') == result
    assert tasks.calls == 8
    assert len(set(tasks.ids)) == 8


def test_multiple_chapters_and_guide_share_one_budget(tmp_path):
    source, context, language, glossary = inputs(tmp_path, 8)
    tasks = WindowTasks(2)
    handler = CompanionBuildHandler(CompanionBuildRequest(source, target_language='zh-CN'), CompanionGenerationRecipe(review_rounds=0), execution=CompanionExecutionOptions(workers=2), task_service=tasks)
    blocks = [b.block_id for b in source.blocks]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(translate, handler, context, source, language, glossary, blocks[:4], 'chapter-a'), pool.submit(translate, handler, context, source, language, glossary, blocks[4:], 'chapter-b'), pool.submit(handler.task_service.execute_or_resume, context, SimpleNamespace(task_id='guide', prompt='guide'))]
        results = [f.result(timeout=10) for f in futures]
    assert all(isinstance(result, dict) for result in results[:2])
    assert results[2] == 'guide-done'
    assert tasks.calls == 17
    assert tasks.peak == 2


@pytest.mark.parametrize('method', ['execute', 'execute_or_resume', 'resume', 'adopt_and_revalidate'])
def test_budget_releases_after_exception_and_delegates_options(method):
    seen = []
    def invoke(context, *args, **kwargs):
        seen.append((args, kwargs))
        if len(seen) == 1:
            raise TimeoutError('fixture')
        return 'done'
    service = BudgetedTaskService(SimpleNamespace(**{method: invoke}), 1)
    context = SimpleNamespace(checkpoint=lambda: None)
    with pytest.raises(TimeoutError):
        getattr(service, method)(context, 'request', input='host-turn', options='policy')
    assert getattr(service, method)(context, 'request', input='host-turn', options='policy') == 'done'
    assert seen == [(('request',), {'input': 'host-turn', 'options': 'policy'})] * 2


def test_waiting_for_budget_obeys_stop():
    entered, release, waiting = Event(), Event(), Event()
    class StopWaiting(Exception):
        pass
    def execute(context, request):
        entered.set()
        assert release.wait(3)
    service = BudgetedTaskService(SimpleNamespace(execute_or_resume=execute), 1)
    normal = SimpleNamespace(checkpoint=lambda: None)
    checks = 0
    def checkpoint():
        nonlocal checks
        checks += 1
        if checks > 1:
            waiting.set()
            raise StopWaiting()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.execute_or_resume, normal, 'active')
        assert entered.wait(2)
        second = pool.submit(service.execute_or_resume, SimpleNamespace(checkpoint=checkpoint), 'queued')
        with pytest.raises(StopWaiting):
            second.result(timeout=2)
        release.set()
        first.result(timeout=2)
    assert waiting.is_set()
