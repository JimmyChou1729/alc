"""Closed public HTTP input contracts; secrets are write-only inputs."""

from __future__ import annotations

from typing import Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobInput(InputModel):
    source_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    source_url: str | None = Field(default=None, max_length=4096)
    target_language: str = Field(
        default="zh-CN", pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"
    )
    output: Literal["reader", "companion", "source"] = "reader"
    speed: Literal["economy", "standard", "fast"] | None = "standard"
    processing_workers: int | None = Field(default=None, ge=1, le=8, strict=True)
    review_rounds: int | None = Field(default=None, ge=0, le=2, strict=True)
    mode: Literal["fast", "standard", "deep"] = "standard"
    provider_id: str = Field(default="codex", pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    model: str = Field(default="", max_length=200)
    reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
        | None
    ) = None
    user_intent: str = Field(default="", max_length=8000)
    strict_delivery: bool = Field(default=False, exclude=True)  # Legacy input, no longer controls delivery.

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.source_id) == bool(self.source_url):
            raise ValueError("Choose one uploaded source or URL.")
        if (self.processing_workers is None) != (self.review_rounds is None):
            raise ValueError("Provide both processing_workers and review_rounds.")
        self.model = self.model.strip()
        return self


class ProviderInput(InputModel):
    id: str = Field(pattern=r"^api-[a-z0-9][a-z0-9_-]{0,58}$")
    name: str = Field(min_length=1, max_length=100)
    protocol: Literal["responses", "chat-completions", "anthropic"]
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    key: SecretStr | None = None
    remember_key: bool = False
    reasoning_efforts: list[str] = Field(default_factory=list, max_length=8)
    vision: bool = False
    max_output_tokens: int = Field(default=8192, ge=128, le=131072)
    price_currency: Literal["USD", "CNY", "EUR", "GBP", "JPY", "HKD"] = "USD"
    input_price: float | None = Field(
        default=None, ge=0, le=100000, allow_inf_nan=False
    )
    output_price: float | None = Field(
        default=None, ge=0, le=100000, allow_inf_nan=False
    )
    cache_read_price: float | None = Field(
        default=None, ge=0, le=100000, allow_inf_nan=False
    )
    cache_write_price: float | None = Field(
        default=None, ge=0, le=100000, allow_inf_nan=False
    )

    @field_validator("reasoning_efforts")
    @classmethod
    def efforts(cls, value):
        allowed = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
        if len(set(value)) != len(value) or any(v not in allowed for v in value):
            raise ValueError("Unsupported or duplicate reasoning effort.")
        return value

    @model_validator(mode="after")
    def connection(self):
        from ac_llm.providers.http_api import HTTPProviderConfig

        from urllib.parse import urlsplit
        if urlsplit(self.base_url).path.rstrip("/").endswith(("/chat/completions", "/responses", "/messages")):
            raise ValueError("Base URL 应填写服务根地址（例如 https://api.example.com/v1），不要包含 /chat/completions、/responses 或 /messages；接口路径由所选协议自动添加。")

        HTTPProviderConfig(
            self.id,
            self.protocol,
            self.base_url,
            self.max_output_tokens,
            tuple(self.reasoning_efforts),
            self.vision,
        )
        if not self.model.strip():
            raise ValueError("A model ID is required.")
        if (self.input_price is None) != (self.output_price is None):
            raise ValueError("Provide both input and output prices or neither.")
        return self


class ControlInput(InputModel):
    action: Literal["pause", "resume", "cancel", "retry_delivery"]
    resume_input: dict | None = None


class ResourceInput(InputModel):
    max_jobs: int = Field(default=2, ge=1, le=4)
    api_slots: int = Field(default=8, ge=1, le=16)
    cli_slots: int = Field(default=8, ge=1, le=16)
    translation_window_workers: int = Field(default=1, ge=1, le=16)
    companion_workers: int = Field(default=2, ge=1, le=16)
