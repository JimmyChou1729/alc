from alc_translate.workflow import _merge_glossary_candidates, _validate_glossary_window, _has_forbidden_glossary_control


def test_retry_preserves_valid_neighbors_and_replaces_bad_entry():
    terms=[{'term_id':str(i),'term':f'term{i}'} for i in range(3)]
    good=lambda i: {'term_id':str(i),'preferred_translation':f'术语{i}','target_definition':'有效释义'}
    first={'entries':[good(0),{**good(1),'preferred_translation':'$x$'},good(2)]}
    second={'entries':[good(1)]}
    merged=_merge_glossary_candidates(first,second,terms)
    assert len(_validate_glossary_window(merged,terms))==3
    assert merged['entries']==[good(0),good(1),good(2)]


def test_escaped_control_is_not_accepted_as_tex():
    assert _has_forbidden_glossary_control(r'振幅 $\u0012sigma_{12}$')
    assert not _has_forbidden_glossary_control(r'振幅 $\sigma_{12}$')


def test_partial_retry_error_does_not_bypass_control_recovery(tmp_path, monkeypatch):
    import alc_translate.workflow as w
    from ac_jobs import RunContext, RunRepository, RunSpec
    from ac_llm import LLMCompleted, LLMRequest, JsonOutput, LLMExecutionOptions
    terms=[{'term_id':str(i),'term':f'term{i}'} for i in range(3)]
    good=lambda i: {'term_id':str(i),'preferred_translation':f'术语{i}','target_definition':'释义'}
    bad={**good(1),'target_definition':'振幅 $'+'\x00'+r'\sigma$'}
    replies=iter([{'entries':[good(0),bad,good(2)]},{'entries':[bad]}])
    monkeypatch.setattr(w,'_execute',lambda *a,**kw: LLMCompleted(next(replies),'fake','fake',None,None))
    repo=RunRepository(tmp_path/'jobs');ctx=RunContext(repo,repo.create(RunSpec('run','test',{})),resume_input=None)
    result=w._validated_generation(None,ctx,LLMRequest('r','p',JsonOutput({'type':'object'})),
        validator=lambda value:w._validated_glossary_document(value,terms),candidate_id='candidate',
        resume_input=None,options=LLMExecutionOptions(),stopped_message='stopped',
        retry_candidate_merger=lambda a,b:w._merge_glossary_candidates(a,b,terms),
        retry_diagnostic_validator=lambda value:value)
    assert result.error.code=='glossary_control_character_invalid'
    accepted,recovered,dropped=w._salvaged_glossary_fallback(result.candidate,terms)
    assert len(accepted)==3 and recovered==['1'] and not dropped
