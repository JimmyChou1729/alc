import pytest
from alc_web.errors import explain_error
from alc_web.models import ProviderInput


def test_nested_http_error_is_explained_without_provider_secrets():
    result = explain_error({'code':'workflow_attention','resume':{'details':{'http_status':404,'response_body':'secret-test-value'}}})
    assert '404' in result and 'Base URL' in result and '新建任务' in result
    assert 'secret-test-value' not in result


@pytest.mark.parametrize('path', ['/v1/chat/completions','/v1/responses','/v1/messages', '/v1/chat/completions/'])
def test_endpoint_is_not_accepted_as_base_url(path):
    with pytest.raises(ValueError, match='Base URL 应填写'):
        ProviderInput(id='api-test',name='test',protocol='responses',model='test',base_url='https://example.com'+path)


def test_root_api_url_is_accepted():
    assert ProviderInput(id='api-test',name='test',protocol='chat-completions',model='test',base_url='https://example.com/v1').base_url.endswith('/v1')


def test_frozen_endpoint_configuration_gives_specific_cause():
    result = explain_error({'workflow_error': {'details': {'http_status':404}}},
        {'base_url':'https://example.com/v1/chat/completions','protocol':'responses'})
    assert '完整 API 接口地址' in result and '新建任务' in result
    assert 'example.com' not in result
