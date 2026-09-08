"""Application provider profiles and operating-system credential references."""

from __future__ import annotations

import os
import json
import hashlib
import tomllib
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any

from ac_llm import codex_model_catalog
from ac_llm.config import DEFAULT_MODELS

from .models import ProviderInput


class SecretVault:
    def __init__(self, project: Path):
        self._service = "alc-web:" + hashlib.sha256(str(project.resolve()).encode()).hexdigest()
        self._values: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _backend():
        import keyring

        backend = keyring.get_keyring()
        if type(backend).__module__ not in {
            "keyring.backends.macOS",
            "keyring.backends.Windows",
            "keyring.backends.SecretService",
        }:
            raise ValueError(
                "A supported OS credential store is unavailable. Use session-only storage."
            )
        return backend

    @staticmethod
    def validate_secret(secret: str) -> None:
        if not secret or len(secret) > 8192 or "\n" in secret or "\r" in secret:
            raise ValueError("Invalid API key.")

    def put(self, provider_id: str, secret: str, *, remember: bool) -> None:
        self.validate_secret(secret)
        if remember:
            try:
                self._backend().set_password(self._service, provider_id, secret)
            except Exception as exc:
                raise ValueError(
                    "The OS credential store could not save this key. Use session-only storage or unlock it."
                ) from exc
        with self._lock:
            self._values[provider_id] = secret

    def get(self, provider_id: str, *, remember: bool) -> str | None:
        with self._lock:
            if provider_id in self._values:
                return self._values[provider_id]
        if remember:
            try:
                return self._backend().get_password(self._service, provider_id)
            except Exception:
                return None
        return None

    def availability(self, provider_id: str, *, remember: bool) -> bool | None:
        """Inspect session state without prompting to unlock an OS credential."""
        with self._lock:
            if provider_id in self._values:
                return True
        return None if remember else False

    def forget_saved(self, reference: str) -> None:
        try:
            backend = self._backend()
            if backend.get_password(self._service, reference) is not None:
                backend.delete_password(self._service, reference)
        except Exception as exc:
            raise ValueError(
                "Could not remove the saved credential. Unlock the OS credential store before switching to session-only storage."
            ) from exc


def cli_profiles() -> list[dict[str, Any]]:
    profiles = []
    for name in ("codex", "claude"):
        executable = shutil.which(name)
        version, supported = None, False
        if executable:
            try:
                result = subprocess.run(
                    [executable, "--version"], capture_output=True, text=True, timeout=5
                )
                version = (
                    result.stdout.strip()[:120] if result.returncode == 0 else None
                )
                help_args = (
                    [executable, "exec", "--help"]
                    if name == "codex"
                    else [executable, "--help"]
                )
                help_result = subprocess.run(
                    help_args, capture_output=True, text=True, timeout=5
                )
                expected = (
                    (
                        "--ignore-user-config",
                        "--json",
                        "--sandbox",
                        "--skip-git-repo-check",
                    )
                    if name == "codex"
                    else (
                        "--tools",
                        "--strict-mcp-config",
                        "--setting-sources",
                        "--output-format",
                    )
                )
                supported = help_result.returncode == 0 and all(
                    flag in help_result.stdout for flag in expected
                )
            except (OSError, subprocess.SubprocessError):
                pass
        warning = _routing_warning(name)
        models: list[dict[str, object]] = []
        catalog_status = "unavailable"
        catalog_message = "此 CLI 没有提供可验证的模型清单。"
        if name == "codex" and executable and supported and warning is None:
            catalog = codex_model_catalog(executable)
            models = [model.to_document() for model in catalog.models]
            catalog_status = catalog.status
            catalog_message = catalog.message
        default_model = DEFAULT_MODELS[name]["medium"]
        if models and default_model not in {model["id"] for model in models}:
            default_model = str(
                next(
                    (model["id"] for model in models if model["provider_default"]),
                    models[0]["id"],
                )
            )
        profiles.append(
            {
                "id": name,
                "name": (
                    "Codex CLI · OpenAI"
                    if name == "codex"
                    else "Claude Code CLI · Anthropic"
                ),
                "protocol": "cli",
                "available": bool(executable),
                "compatible": supported and warning is None,
                "version": version,
                "authentication": "not_verified",
                "billing": "cli_managed",
                "model": "",
                "default_model": default_model,
                "models": models,
                "model_catalog_status": catalog_status,
                "model_catalog_message": catalog_message,
                "reasoning_efforts": (
                    ["low", "medium", "high", "xhigh"]
                    if name == "codex"
                    else ["low", "medium", "high", "max"]
                ),
                "vision": name == "codex",
                "configuration_warning": warning,
                "credential_override_present": (
                    bool(
                        os.environ.get("CODEX_API_KEY")
                        or os.environ.get("OPENAI_API_KEY")
                    )
                    if name == "codex"
                    else bool(
                        os.environ.get("ANTHROPIC_API_KEY")
                        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                    )
                ),
            }
        )
    return profiles


def _routing_warning(
    name: str, *, config_path: Path | None = None, environment: dict | None = None
) -> str | None:
    values = os.environ if environment is None else environment
    message = "检测到自定义 CLI provider 或认证配置。隔离运行不会加载它；请使用明确的 API 连接，避免切换到其他服务或计费方式。"
    try:
        if name == "codex":
            if any(values.get(k) for k in ("OPENAI_BASE_URL", "CODEX_BASE_URL")):
                return message
            path = (
                config_path
                or Path(values.get("CODEX_HOME", str(Path.home() / ".codex")))
                / "config.toml"
            )
            if path.is_file():
                if path.stat().st_size > 256 * 1024:
                    return "CLI 配置过大，无法验证隔离调用的服务归属。"
                config = tomllib.loads(path.read_text())
                selected = config.get("model_provider", "openai")
                if selected != "openai" or config.get("model_providers", {}).get(
                    selected
                ):
                    return message
        else:
            if any(
                values.get(k)
                for k in (
                    "ANTHROPIC_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_USE_VERTEX",
                    "CLAUDE_CODE_USE_FOUNDRY",
                )
            ):
                return message
            path = (
                config_path
                or Path(values.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
                / "settings.json"
            )
            if path.is_file():
                if path.stat().st_size > 256 * 1024:
                    return "CLI 配置过大，无法验证隔离调用的服务归属。"
                config = json.loads(path.read_text())
                if any(
                    config.get(k)
                    for k in ("apiKeyHelper", "forceLoginMethod", "forceLoginOrgUUID")
                ) or any(
                    k in config.get("env", {})
                    for k in (
                        "ANTHROPIC_API_KEY",
                        "ANTHROPIC_AUTH_TOKEN",
                        "ANTHROPIC_BASE_URL",
                        "CLAUDE_CODE_USE_BEDROCK",
                        "CLAUDE_CODE_USE_VERTEX",
                        "CLAUDE_CODE_USE_FOUNDRY",
                    )
                ):
                    return message
    except (OSError, ValueError, TypeError, AttributeError):
        return "无法验证 CLI 配置；请检查配置或使用明确的 API 连接。"
    return None


def save_provider(store: Any, vault: SecretVault, value: ProviderInput) -> dict:
    with vault._lock:
        document = value.model_dump(exclude={"key"})
        previous = store.setting("providers", {}).get(value.id, {})
        binding = (value.protocol, value.base_url.rstrip("/"))
        same = (
            previous.get("protocol"),
            previous.get("base_url", "").rstrip("/"),
        ) == binding
        reference = (
            previous.get("secret_ref", value.id)
            if same
            else value.id
            + ":"
            + hashlib.sha256(json.dumps(binding).encode()).hexdigest()
        )
        document["secret_ref"] = reference
        key = value.key.get_secret_value() if value.key is not None else None
        if same and value.remember_key and not previous.get("remember_key") and key is None:
            key = vault.get(reference, remember=False)
            if key is None:
                raise ValueError("当前会话没有可用密钥，请重新填写 API key 后再保存到系统密钥库。")
        forget = same and previous.get("remember_key") and not value.remember_key
        if forget and key is None:
            key = vault.get(reference, remember=True)
            if key is None:
                raise ValueError(
                    "Unlock the saved key or enter it before switching to session-only storage."
                )
        if forget:
            vault.validate_secret(key)
            vault.forget_saved(reference)
        if key is not None:
            vault.put(reference, key, remember=value.remember_key)
        store.merge_setting("providers", value.id, document)
        return {
            **present_profile(document),
            "key_available": bool(vault.get(reference, remember=value.remember_key)),
            "authentication": "not_verified",
        }


def resolve_profile(store: Any, provider_id: str, discovered: list[dict]) -> dict:
    candidates = {p["id"]: p for p in discovered}
    candidates.update(store.setting("providers", {}))
    if provider_id not in candidates:
        raise ValueError("Configure the selected provider first.")
    result = present_profile(candidates[provider_id])
    if result["protocol"] == "cli" and not result.get("compatible"):
        raise ValueError(
            result.get("configuration_warning")
            or "The selected CLI is missing or does not support the required isolation flags."
        )
    return dict(result)


def present_profile(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get("protocol") != "cli" and result.get("model"):
        model = str(result["model"])
        efforts = list(result.get("reasoning_efforts", ()))
        result.update(
            default_model=model,
            models=[
                {
                    "id": model,
                    "name": model,
                    "description": "此 API 连接已配置的模型。",
                    "reasoning_efforts": efforts,
                    "default_reasoning_effort": None,
                    "provider_default": True,
                }
            ],
            model_catalog_status="configured",
            model_catalog_message=None,
        )
    return result


def runtime_profile(value: dict[str, Any]) -> dict[str, Any]:
    presentation = {
        "default_model",
        "models",
        "model_catalog_status",
        "model_catalog_message",
    }
    return {key: item for key, item in value.items() if key not in presentation}


def validate_model_effort(
    profile: dict[str, Any], model: str, effort: str | None
) -> None:
    options = [
        item
        for item in profile.get("models", ())
        if isinstance(item, dict) and item.get("id") == model
    ]
    if profile.get("model_catalog_status") == "available" and not options:
        raise ValueError("The selected model is not available from this CLI.")
    if effort and options and effort not in options[0].get("reasoning_efforts", ()):
        raise ValueError(
            "This reasoning effort is not available for the selected model."
        )
