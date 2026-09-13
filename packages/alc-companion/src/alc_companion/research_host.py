"""Optional host-owned research bridge; no research provider dependency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from ac_llm import HostResponse, HostResponseStatus, InvalidRequestError


class ResearchBroker:
    def __init__(self, source, research):
        self.source = source
        self.research = research

    @property
    def execution_identity(self):
        return {"source": self.source.execution_identity, "research": self.research.identity}

    def execute(self, request, *, workspace):
        if request.instruction.startswith("research "):
            return self.research.execute(request, workspace=workspace)
        return self.source.execute(request, workspace=workspace)


class ResearchHost:
    """Use an explicitly configured executable, never a model-selected command."""

    def __init__(self, environment):
        self.environment = environment
        self._env = environment.apply_to()
        self._env.pop("ALC_RESEARCH_HOST_BINDING", None)
        self._identity = None
        self.instructions = ""
        self.command = None
        env = self._env
        configured = env.get("ALC_COMPANION_RESEARCH_HOST", "")
        if not configured:
            return
        path = Path(configured)
        if not path.is_absolute() or not path.is_file():
            return
        self.command = str(path)
        self._argv = [sys.executable, self.command] if path.suffix == ".py" or path.parent.name == "host_adapters" else [self.command]
        try:
            result = subprocess.run([*self._argv, "describe"], env=env,
                capture_output=True, timeout=10, check=False)
            if result.returncode or len(result.stdout) > 16000:
                return
            descriptor = json.loads(result.stdout)
            if descriptor.get("available") is True and isinstance(descriptor.get("instructions"), str):
                self.instructions = descriptor["instructions"]
                self._env["ALC_RESEARCH_HOST_BINDING"] = json.dumps(descriptor.get("identity", {}))
                self._identity = {"contract": "alc.companion.research_host.v1", "command": self.command,
                    "descriptor_sha256": hashlib.sha256(result.stdout).hexdigest(),
                    "executable_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError, RecursionError):
            return

    @property
    def identity(self):
        return self._identity

    def execute(self, request, *, workspace):
        if not self.instructions:
            return self._refused()
        payload = request.instruction.removeprefix("research ")
        try:
            if len(payload.encode()) > 8000 or not isinstance(json.loads(payload), dict):
                raise ValueError("Invalid research request")
            result = subprocess.run([*self._argv, "execute"], input=payload.encode(),
                cwd=workspace, env=self._env, capture_output=True,
                timeout=120, check=False)
            # Do not pass a truncated JSON document off as usable evidence.
            if result.returncode or len(result.stdout) > 128000:
                raise ValueError("Research host failed or response exceeded limit")
            value = json.loads(result.stdout, parse_constant=_reject_constant)
            if not isinstance(value, dict):
                raise ValueError("Invalid research response")
            return HostResponse(HostResponseStatus.COMPLETED, result=value)
        except (OSError, subprocess.TimeoutExpired, ValueError, RecursionError, InvalidRequestError):
            return self._refused()

    @staticmethod
    def _refused():
        return HostResponse(HostResponseStatus.REFUSED, reason_code="research_host_unavailable",
            reason="Research unavailable or invalid response; continue with available evidence.",
            retryable=False, retry_condition="The host configuration or research request must change.")


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")
