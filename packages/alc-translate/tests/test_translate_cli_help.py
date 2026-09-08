from __future__ import annotations

import json

import pytest

from alc_translate.cli import main


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["detect-language", "--help"],
        ["build-glossary", "--help"],
        ["translate-blocks", "--help"],
        ["status", "--help"],
        ["resume", "--help"],
        ["stop", "--help"],
        ["validate", "--help"],
        ["get-result", "--help"],
    ],
)
def test_root_and_subcommand_help_is_human_readable(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("usage: alc-translate")
    assert "ac.command_result.v2" not in captured.out


def test_generation_and_resume_help_expose_explicit_host_authority(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in ("detect-language", "build-glossary", "translate-blocks", "resume"):
        assert main([command, "--help"]) == 0
        assert "--host-authority" in capsys.readouterr().out


def test_generation_help_exposes_optional_user_intent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in ("detect-language", "build-glossary", "translate-blocks"):
        assert main([command, "--help"]) == 0
        assert "--user-intent" in capsys.readouterr().out


def test_generation_and_resume_expose_window_concurrency(capsys):
    from alc_translate.cli import _parser, _execution

    for command in ("detect-language", "build-glossary", "translate-blocks", "resume"):
        assert main([command, "--help"]) == 0
        assert "--window-workers" in capsys.readouterr().out
    args = _parser().parse_args(
        ["resume", "--project-dir", "example", "--window-workers", "2"]
    )
    assert _execution(args).window_workers == 2


def test_help_has_no_obsolete_json_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status", "--help"]) == 0
    output = capsys.readouterr().out
    assert "--json" not in output


def test_only_paper_access_commands_accept_a_document_cache_root(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in (
        "detect-language",
        "build-glossary",
        "translate-blocks",
        "resume",
    ):
        assert main([command, "--help"]) == 0
        assert "--document-cache-root" in capsys.readouterr().out
    for command in ("status", "stop", "validate", "get-result"):
        assert main([command, "--help"]) == 0
        assert "--document-cache-root" not in capsys.readouterr().out


def test_usage_error_points_to_contextual_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["error"]["code"] == "invalid_request"
    assert result["error"]["details"] == {"help_command": "alc-translate status --help"}


def test_execution_profile_is_explicit_and_preserves_injected_options():
    from alc_translate.cli import _parser, _execution
    from ac_llm import LLMExecutionOptions, LLMExecutionProfile

    for command in ("detect-language", "build-glossary", "translate-blocks", "resume"):
        parser = _parser()
        prefix = [command, "--project-dir", "example"]
        if command != "resume":
            prefix += ["source.md"]
        if command == "detect-language":
            prefix += ["--target-language", "zh-CN"]
        if command in {"build-glossary", "translate-blocks"}:
            # Inspect flags through help; generation prerequisite options are
            # independently covered by durable workflow tests.
            action = parser._subparsers._group_actions[0].choices[command]
            profile = next(a for a in action._actions if a.dest == "execution_profile")
            assert profile.default == "standard"
            assert profile.choices == ("standard", "local-app")
            continue
        args = parser.parse_args(prefix)
        assert _execution(args).llm.profile is LLMExecutionProfile.STANDARD
        args = parser.parse_args(prefix + ["--execution-profile", "local-app"])
        assert _execution(args).llm.profile is LLMExecutionProfile.LOCAL_APP
        injected = LLMExecutionOptions()
        args.llm_options = injected
        assert _execution(args).llm is injected
