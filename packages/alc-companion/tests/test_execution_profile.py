import pytest

from ac_llm import LLMExecutionOptions, LLMExecutionProfile
from alc_companion import cli


@pytest.mark.parametrize('command', ['build', 'resume'])
def test_explicit_execution_profile_selects_local_app(command):
    args = ['--project-dir', '/tmp/companion-profile-test']
    if command == 'build':
        args = ['fixture.md', *args, '--target-language', 'zh-CN']
    parsed = cli._parser().parse_args([command, *args])
    assert cli._execution_options(parsed).llm.profile is LLMExecutionProfile.STANDARD
    parsed = cli._parser().parse_args([command, *args, '--execution-profile', 'local-app'])
    assert cli._execution_options(parsed).llm.profile is LLMExecutionProfile.LOCAL_APP
    injected = LLMExecutionOptions()
    parsed.llm_options = injected
    assert cli._execution_options(parsed).llm is injected
