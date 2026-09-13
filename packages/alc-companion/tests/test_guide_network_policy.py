from ac_llm import LLMExecutionOptions, LLMExecutionProfile, ModelSelection
from alc_companion.build import _guide_llm_options


def test_native_search_is_guide_only_and_preserves_isolation():
    source = LLMExecutionOptions(profile=LLMExecutionProfile.LOCAL_APP, internet=False)
    guide = _guide_llm_options(source, ModelSelection(provider='codex', model='test'))
    assert guide.internet
    assert not source.internet
    assert guide.profile is LLMExecutionProfile.LOCAL_APP
    assert guide.host_authority == source.host_authority
    assert guide.host_broker == source.host_broker


def test_other_provider_policy_is_unchanged():
    source = LLMExecutionOptions(profile=LLMExecutionProfile.LOCAL_APP, internet=False)
    assert _guide_llm_options(source, ModelSelection(provider='other',model='test')) is source
