from alc_web.event_labels import event_label


def test_nested_event_has_user_facing_label():
    assert event_label({'kind':'package.event','data':{'event':'llm_provider_failed'}}) == '模型请求失败'


def test_unknown_event_never_exposes_raw_details():
    assert event_label({'kind':'internal.secret-id','data':{'message':'private'}}) == '任务进度已更新'


def test_control_label_distinguishes_pause_from_resume():
    assert event_label({'kind':'job.control','data':{'action':'pause'}}) != event_label({'kind':'job.control','data':{'action':'resume'}})
