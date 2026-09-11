from copy import deepcopy
from alc_web.ocr_notices import summarize_notices


def test_only_real_ambiguity_shown_without_changing_original():
    source={'pages':[{'page_number':1,'uncertainties':[
        {'excerpt':'','reason':'Visual comparison is incomplete: all_visible_text.'},
        {'excerpt':'1','reason':'The page number has no corresponding editable node.'},
        {'excerpt':'CHAPTER 1','reason':'Visible heading is absent from the OCR HTML.'},
        {'excerpt':'Helo','reason':'Edit does not change the source text.','proposed_edit':{}},
        {'excerpt':'x or y','reason':'The scan is blurred; either letter is plausible.'},
    ]}]}
    before=deepcopy(source)
    result=summarize_notices(source)
    assert result['display_count']==1 and result['items'][0]['excerpt']=='x or y'
    assert source==before


def test_explicit_typed_policy_is_shared_by_presentation():
    result=summarize_notices({'pages':[{'page_number':3,'uncertainties':[
        {'kind':'irrelevant','excerpt':'label','reason':'Layout only'},
        {'kind':'limitation','excerpt':'known missing token','reason':'Cannot preserve structure'},
        {'kind':'ambiguous','excerpt':'0/O','reason':'Both readings fit the visible glyph'},
    ]}]})
    assert result['display_count']==1 and result['items'][0]['pages']==[3]


def test_unapplied_edits_are_separate_from_ambiguity():
    from alc_web.ocr_notices import summarize_notices
    result = summarize_notices({'pages': [{'page_number': 2, 'uncertainties': [], 'diagnostics': [
        {'excerpt': 'x', 'proposed_edit': {'before': 'x', 'after': 'y', 'reason': 'Printed y'}, 'reason': 'span missing'},
        {'excerpt': 'x', 'proposed_edit': {'before': 'x', 'after': 'x'}, 'reason': 'no change'},
        {'excerpt': '', 'reason': 'Visual comparison is incomplete: all_visible_text.'},
        {'excerpt': 'Section title', 'kind': 'limitation', 'reason': 'Missing heading'},
    ]}]})
    assert result['display_count'] == 0
    assert len(result['unapplied_items']) == 2
    assert result['unapplied_items'][0]['reason'] == 'Printed y'


def test_notice_explanations_are_chinese_without_changing_evidence():
    from alc_web.ocr_notices import summarize_notices
    result = summarize_notices({'pages': [{'page_number': 1, 'uncertainties': [
        {'kind': 'ambiguous', 'excerpt': 'x', 'reason': 'The symbol is unclear.'}],
        'diagnostics': [{'kind': 'limitation', 'excerpt': 'Title', 'reason': 'The heading is missing.'}]}]})
    record = result['items'][0]['records'][0]
    assert record['reason'] == 'The symbol is unclear.'
    assert '无法' in record['display_reason']
    assert '标题' in result['unapplied_items'][0]['display_reason']


def test_input_limit_is_not_reported_as_connection_failure():
    from alc_web.errors import explain_error
    message = explain_error({'resume': {'details': {'provider_failure': {
        'ac_error_code': 'provider_invalid_request', 'detail_code': 'input_too_large'}}}})
    assert '输入容量' in message
    assert '连接' not in message


def test_local_ocr_unknown_failure_does_not_claim_timeout():
    from alc_web.errors import explain_error
    message = explain_error({'code': 'mineru_local_failed',
        'message': 'Local OCR failed (exit code 1, provider_error_without_details)'})
    assert '未报告具体异常' in message
    memory = explain_error({'code': 'mineru_local_failed',
        'message': 'Local OCR failed (exit code 1, memory_exhausted)'})
    assert '内存不足' in memory
