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


def test_unapplied_notice_explains_counts_and_separates_structure():
    result = summarize_notices({'pages': [{'page_number': 5, 'diagnostics': [
        {'excerpt': 'x', 'reason': 'Edit does not identify a single editable text node on this page. Requested occurrence 2; found 1 matching spans.',
         'proposed_edit': {'before': 'x', 'after': 'y'}},
        {'kind': 'limitation', 'excerpt': 'title', 'reason': 'Missing heading'},
    ]}]})
    first, second = result['unapplied_items']
    assert '第 2 处' in first['display_reason'] and '1 处' in first['display_reason']
    assert first['after'] == 'y' and first['category'] == 'revision'
    assert second['category'] == 'structure' and second['after'] is None


def test_structure_notice_categories_do_not_hide_content_or_mutate_evidence():
    source = {"pages": [{"page_number": 4, "diagnostics": [
        {"kind": "limitation", "excerpt": "f(x).", "reason": "The source includes a terminal period after the displayed equation; no editable node contains it."},
        {"kind": "limitation", "excerpt": "<sup>4</sup>", "reason": "The source shows a superscript footnote marker; the OCR has literal sup tags."},
        {"kind": "limitation", "excerpt": "seminorm", "reason": "The footnote contains the seminorm notation; restoring it requires missing mathematical structure."},
        {"kind": "limitation", "excerpt": "If is", "reason": "The omitted mathematical D has no corresponding editable math node."},
    ]}]}
    before = deepcopy(source)
    result = summarize_notices(source)
    assert source == before
    items = result["unapplied_items"]
    assert len(items) == 4
    assert [i["detail_kind"] for i in items] == ["punctuation", "footnote", "math", "math"]
    assert all(i["category"] == "structure" for i in items)
    assert "整段内容缺失" in items[0]["display_reason"]
    assert items[2]["category_label"] == "数学内容待核对"
