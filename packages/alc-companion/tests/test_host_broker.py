from __future__ import annotations

import subprocess
import shlex
from pathlib import Path

from ac_llm import (
    AcRuntimeEnvironment,
    HostRequest,
    HostResponseStatus,
)
from alc_companion.host_broker import CompanionSourceHostBroker


def _environment() -> AcRuntimeEnvironment:
    return AcRuntimeEnvironment(
        {
            "AC_HOME": None,
            "AC_RUNTIME_HOME": None,
            "AC_DOCUMENT_CACHE": None,
            "PATH": "/usr/bin:/bin",
        }
    )


def test_broker_executes_only_registered_read_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker = CompanionSourceHostBroker(_environment())
    command = [
        "ac-document",
        "read-cached-source-range",
        "--document-ref",
        "{}",
        "--cache-root",
        str(tmp_path),
        "--text-only",
        "1",
        "10",
    ]
    broker.register_commands({"argv": command})
    calls: list[tuple[str, ...]] = []

    def fake_run(argv, **_kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, b"source", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    response = broker.execute(
        HostRequest(
            "read-1",
            " ".join(shlex.quote(item) for item in command),
            "read source",
        ),
        workspace=tmp_path,
    )

    assert response.status is HostResponseStatus.COMPLETED
    assert response.result["stdout"] == "source"
    assert calls == [tuple(command)]
    refused = broker.execute(
        HostRequest("write-1", "rm -rf data", "write"),
        workspace=tmp_path,
    )
    assert refused.status is HostResponseStatus.REFUSED
    assert calls == [tuple(command)]


def test_broker_allows_only_bounded_term_for_registered_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker = CompanionSourceHostBroker(_environment())
    template = [
        "ac-document",
        "search-full-text",
        "--document-ref",
        "{}",
        "--cache-root",
        str(tmp_path),
        "--term",
        "<term>",
    ]
    broker.register_commands({"argv": template})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, b"match", b""
        ),
    )

    command = [*template[:-1], "symbiotic star"]
    response = broker.execute(
        HostRequest(
            "search-1",
            " ".join(shlex.quote(item) for item in command),
            "search",
        ),
        workspace=tmp_path,
    )
    assert response.status is HostResponseStatus.COMPLETED
    refused = broker.execute(
        HostRequest(
            "search-2",
            " ".join(
                shlex.quote(item)
                for item in [*template[:-1], "x" * 1001]
            ),
            "search",
        ),
        workspace=tmp_path,
    )
    assert refused.status is HostResponseStatus.REFUSED


def _read_commands(tmp_path):
    def descriptor(ref, start, end, parts):
        return {"argv": ["ac-document", "read-cached-source-range", "--document-ref", ref,
                         "--cache-root", str(tmp_path), "--text-only", str(start), str(end)],
                "part_numbers": parts}
    return {"source": [descriptor("source", 1, 1, [1]), descriptor("source", 2, 2, [2]),
                        descriptor("source", 1, 2, [1, 2])],
            "translation": {"parts": [descriptor("translation", 1, 2, [1, 2])]}}


def _execute_read(broker, descriptor, tmp_path):
    return broker.execute(HostRequest("read", shlex.join(descriptor["argv"]), "read source"), workspace=tmp_path)


def test_read_receipts_cover_source_and_translation_separately(monkeypatch, tmp_path):
    import pytest
    broker = CompanionSourceHostBroker(_environment())
    commands = _read_commands(tmp_path)
    broker.register_commands(commands)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"text", b""))
    with pytest.raises(ValueError):
        broker.validate_reads(commands, require_complete=True)
    _execute_read(broker, commands["source"][0], tmp_path)
    _execute_read(broker, commands["translation"]["parts"][0], tmp_path)
    with pytest.raises(ValueError):
        broker.validate_reads(commands, require_complete=True)
    _execute_read(broker, commands["source"][1], tmp_path)
    broker.validate_reads(commands, require_complete=True)


def test_receipts_survive_handler_recreation(monkeypatch, tmp_path):
    from ac_jobs import RunContext, RunRepository, RunSpec
    repo = RunRepository(tmp_path / "jobs")
    context = RunContext(repo, repo.create(RunSpec("read-run", "handler", {})), resume_input=None)
    broker = CompanionSourceHostBroker(_environment())
    broker.bind_context(context)
    commands = _read_commands(tmp_path)
    broker.register_commands(commands)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"text", b""))
    _execute_read(broker, commands["source"][2], tmp_path)
    _execute_read(broker, commands["translation"]["parts"][0], tmp_path)
    fresh = CompanionSourceHostBroker(_environment())
    fresh.bind_context(context)
    fresh.register_commands(commands)
    fresh.validate_reads(commands, require_complete=True)


def test_failed_reads_cannot_be_certified(monkeypatch, tmp_path):
    import pytest
    commands = _read_commands(tmp_path)
    for mode in ("missing", "exit", "truncated", "empty"):
        broker = CompanionSourceHostBroker(_environment())
        broker.register_commands(commands)
        def run(argv, **kwargs):
            if mode == "missing":
                raise FileNotFoundError()
            return subprocess.CompletedProcess(argv, 1 if mode == "exit" else 0,
                b"x" * 64001 if mode == "truncated" else b"", b"")
        monkeypatch.setattr(subprocess, "run", run)
        response = _execute_read(broker, commands["source"][2], tmp_path)
        if mode in ("missing", "exit"):
            assert response.status is HostResponseStatus.REFUSED
        with pytest.raises(ValueError):
            broker.validate_reads(commands, require_complete=True)
        with pytest.raises(ValueError):
            broker.validate_reads(commands, require_complete=False)


def test_python_symlink_preserves_virtualenv_cli(monkeypatch, tmp_path):
    import os
    import sys
    from alc_companion.build import _companion_llm_options
    from alc_companion.request_contracts import CompanionExecutionOptions
    from ac_llm import LLMExecutionOptions
    system = tmp_path / "system"
    system.mkdir()
    python = system / "python"
    python.touch()
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(python)
    cli = venv / "ac-document"
    cli.write_text("#!/bin/sh\nexit 0\n")
    cli.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(venv / "python"))
    result = _companion_llm_options(CompanionExecutionOptions(
        document_cache_root=tmp_path / "cache",
        llm=LLMExecutionOptions(runtime_environment=_environment()),
    ))
    assert result.runtime_environment.values["PATH"].split(os.pathsep)[0] == str(venv)
