import pytest
from ac_jobs import RunContext, RunRepository, RunSpec, ResumeReason, Paused
from ac_llm import LLMPaused, LLMRequest, JsonOutput, LLMExecutionOptions
import alc_companion.llm_runtime as runtime


@pytest.mark.parametrize('code,continues,reason', [('output_invalid',True,ResumeReason.SUPERVISION_REQUIRED),('output_formatting_failed',True,ResumeReason.SUPERVISION_REQUIRED),('authentication',False,ResumeReason.SUPERVISION_REQUIRED),('output_invalid',False,ResumeReason.EXTERNAL_CONDITION)])
def test_optional_author_output_failure_does_not_hide_auth(tmp_path,monkeypatch,code,continues,reason):
    repo=RunRepository(tmp_path/'jobs')
    ctx=RunContext(repo,repo.create(RunSpec('optional','test',{})),resume_input=None)
    outcome=LLMPaused(reason,'key',{'code':code,'automatic_retry_exhausted':True})
    monkeypatch.setattr(runtime,'execute_task',lambda *a,**k:outcome)
    fallback={'authors':[]}
    result=runtime.execute_semantically_validated_task(None,ctx,
        LLMRequest('author','prompt',JsonOutput({'type':'object'})),
        candidate_id='author',description='author',validate=lambda v:v,
        resume_input=None,options=LLMExecutionOptions(),fallback=fallback)
    if continues:
        assert isinstance(result,runtime.SemanticTaskCompleted)
        assert result.value==fallback
        assert result.candidate_paths[0].is_file()
    else:
        assert isinstance(result,Paused)


def test_saved_optional_failure_replays_without_model_call(tmp_path, monkeypatch):
    repo=RunRepository(tmp_path/'jobs')
    ctx=RunContext(repo,repo.create(RunSpec('replay','test',{})),resume_input=None)
    ctx.working.write_candidate_json('author-unavailable', {'output_unavailable':True})
    def unexpected(*args,**kwargs):
        raise AssertionError('must not call the model on replay')
    monkeypatch.setattr(runtime,'execute_task',unexpected)
    result=runtime.execute_semantically_validated_task(None,ctx,
        LLMRequest('author','prompt',JsonOutput({'type':'object'})),candidate_id='author',
        description='author',validate=lambda v:v,resume_input=None,
        options=LLMExecutionOptions(),fallback={'authors':[]})
    assert result.value == {'authors':[]}
