"""Bounded read-only host broker for Companion source evidence."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import RLock
from typing import Any

from ac_jobs import RunContext

from ac_llm import (
    AcRuntimeEnvironment,
    HostRequest,
    HostResponse,
    HostResponseStatus,
)


_BROKER_CONTRACT = "alc.companion.read_only_source_broker.v2"
_MAX_OUTPUT_BYTES = 64_000
_MAX_SEARCH_TERM_BYTES = 1_000


class CompanionSourceHostBroker:
    """Execute only source-read commands registered by the bound build."""

    def __init__(self, environment: AcRuntimeEnvironment) -> None:
        self._environment = environment
        self._exact: set[tuple[str, ...]] = set()
        self._search_prefixes: set[tuple[str, ...]] = set()
        self._lock = RLock()
        self._context: RunContext | None = None
        self._successful: set[tuple[str, ...]] = set()
        self._failed: set[tuple[str, ...]] = set()

    def bind_context(self, context: RunContext) -> None:
        self._context = context

    def _receipt_id(self, argv: tuple[str, ...]) -> str:
        digest = hashlib.sha256(json.dumps(argv).encode()).hexdigest()
        return f"source-read-receipts/{digest}"

    def _record(self, argv: tuple[str, ...], successful: bool) -> None:
        with self._lock:
            if not successful:
                self._failed.add(argv)
                return
            self._successful.add(argv)
            if self._context is not None:
                artifact_id = self._receipt_id(argv)
                if self._context.artifacts.find(artifact_id) is None:
                    self._context.artifacts.publish_json(
                        artifact_id, {"argv": list(argv), "complete": True}
                    )

    def validate_reads(self, commands: Mapping[str, Any], *, require_complete: bool) -> None:
        """Require successful source and translation coverage independently."""
        groups = [commands.get("source", ())]
        translation = commands.get("translation")
        if isinstance(translation, Mapping):
            groups.append(translation.get("parts", ()))
        with self._lock:
            for group in groups:
                expected: set[int] = set()
                covered: set[int] = set()
                failed = False
                for descriptor in group:
                    argv = tuple(descriptor.get("argv", ()))
                    parts = set(descriptor.get("part_numbers", ()))
                    if not parts:
                        continue
                    expected.update(parts)
                    successful = argv in self._successful
                    if not successful and self._context is not None:
                        ref = self._context.artifacts.find(self._receipt_id(argv))
                        if ref is not None:
                            value = json.loads(self._context.artifacts.read_bytes(ref))
                            successful = value == {"argv": list(argv), "complete": True}
                    if successful:
                        covered.update(parts)
                    failed = failed or argv in self._failed
                if (require_complete or failed) and not expected.issubset(covered):
                    raise ValueError("Complete chapter source reads lack successful receipts")

    @property
    def execution_identity(self) -> Mapping[str, Any]:
        return {"contract": _BROKER_CONTRACT}

    def register_commands(self, value: Any) -> None:
        """Register command descriptors emitted by Companion itself."""

        exact: set[tuple[str, ...]] = set()
        search_prefixes: set[tuple[str, ...]] = set()
        for argv in _command_argv(value):
            _validate_read_command(argv)
            if argv[-1].startswith("<term") and argv[-1].endswith(">"):
                search_prefixes.add(argv[:-1])
            else:
                exact.add(argv)
        with self._lock:
            self._exact.update(exact)
            self._search_prefixes.update(search_prefixes)

    def execute(
        self, request: HostRequest, *, workspace: Path, record_receipt: bool = True
    ) -> HostResponse:
        try:
            argv = tuple(shlex.split(request.instruction.strip()))
        except ValueError:
            return _refused(
                "host_instruction_invalid",
                "Host instruction is not valid shell syntax.",
            )
        if not self._allowed(argv):
            return _refused(
                "host_operation_not_predeclared",
                "Only exact read-only source commands declared by this "
                "Companion build are allowed.",
            )
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                env=self._environment.apply_to(),
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if record_receipt:
                self._record(argv, False)
            return _refused(
                "host_operation_failed",
                f"The predeclared source read could not complete: {type(exc).__name__}.",
                retryable=True,
                retry_condition="Retry after the local ac-document runtime is available.",
            )
        stdout, stdout_truncated = _bounded_output(completed.stdout)
        stderr, stderr_truncated = _bounded_output(completed.stderr)
        successful = (
            completed.returncode == 0
            and bool(stdout.strip())
            and not stdout_truncated
            and not stderr_truncated
        )
        if record_receipt:
            self._record(argv, successful)
        if completed.returncode != 0:
            return _refused(
                "host_operation_failed",
                f"Source read exited with status {completed.returncode}.",
                retryable=True,
                retry_condition="Retry after the source command failure is resolved.",
            )
        return HostResponse(
            HostResponseStatus.PARTIAL
            if stdout_truncated or stderr_truncated
            else HostResponseStatus.COMPLETED,
            result={
                "exit_code": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_truncated or stderr_truncated,
            },
        )

    def _allowed(self, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        with self._lock:
            if argv in self._exact:
                return True
            if argv[:-1] not in self._search_prefixes:
                return False
        term = argv[-1]
        return bool(term) and len(term.encode("utf-8")) <= _MAX_SEARCH_TERM_BYTES


def _command_argv(value: Any) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    if isinstance(value, Mapping):
        argv = value.get("argv")
        if isinstance(argv, Sequence) and not isinstance(argv, (str, bytes)):
            if argv and all(isinstance(item, str) for item in argv):
                commands.append(tuple(argv))
        for item in value.values():
            commands.extend(_command_argv(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            commands.extend(_command_argv(item))
    return tuple(commands)


def _validate_read_command(argv: tuple[str, ...]) -> None:
    if len(argv) < 2 or argv[0] != "ac-document":
        raise ValueError("Companion broker commands must use ac-document")
    if argv[1] not in {
        "get-table-of-contents",
        "get-section",
        "read-cached-source-range",
        "search-full-text",
    }:
        raise ValueError("Companion broker command is not read-only")


def _bounded_output(value: bytes) -> tuple[str, bool]:
    truncated = len(value) > _MAX_OUTPUT_BYTES
    return (
        value[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        truncated,
    )


def _refused(
    code: str,
    reason: str,
    *,
    retryable: bool = False,
    retry_condition: str = "Use one of the predeclared read-only source commands.",
) -> HostResponse:
    return HostResponse(
        HostResponseStatus.REFUSED,
        reason_code=code,
        reason=reason,
        retryable=retryable,
        retry_condition=retry_condition,
    )


__all__ = ["CompanionSourceHostBroker"]
