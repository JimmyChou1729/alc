from alc_web.errors import explain_error


def test_nested_source_layout_error_is_explained_without_echoing_content():
    error = {'code': 'workflow_attention', 'workflow_error': {'code': 'internal_error', 'message': 'Figure panel layout has ambiguous direct graphics'}}
    message = explain_error(error)
    assert '解析阶段' in message
    assert '当前记录不足' not in message
    assert 'direct graphics' not in message


def test_unknown_error_is_not_mislabeled_as_source_error():
    assert '当前记录不足' in explain_error({'code': 'workflow_attention', 'workflow_error': {'message': 'Other failure'}})


def test_chapter_read_failure_is_specific_and_does_not_link_missing_details():
    message = explain_error({'code':'workflow_attention','workflow_error':{'code':'chapter_source_read_incomplete'}})
    assert '原文读取完整性' in message
    assert '技术详情' not in message
    assert '技术详情' not in explain_error({'code':'workflow_attention'})


def test_preload_failures_have_distinct_next_steps():
    assert '恢复重试' in explain_error({'code':'chapter_evidence_unavailable'})
    assert '拆分' in explain_error({'code':'chapter_evidence_too_large'})
