"""Closed semantic and result contracts for standalone translation steps."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from ac_document import (
    RichDocument,
    rich_document_from_document,
    rich_document_to_document,
)
from ac_jobs import (
    ArtifactDigest,
    ArtifactSourceRef,
    JsonValue,
    decode_artifact_digest,
    encode_artifact_digest,
)
from ac_llm import LLMExecutionOptions, ModelSelection

SOURCE_SCHEMA = "alc.translate.source.v2"
LANGUAGE_REQUEST_SCHEMA = "alc.translate.language_request.v1"
GLOSSARY_REQUEST_SCHEMA = "alc.translate.glossary_request.v1"
BLOCKS_REQUEST_SCHEMA = "alc.translate.blocks_request.v1"
GENERATION_RECIPE_SCHEMA = "alc.translate.generation_recipe.v1"
GENERATION_RECIPE_SCHEMA_V2 = "alc.translate.generation_recipe.v2"
GENERATION_RECIPE_SCHEMA_V3 = "alc.translate.generation_recipe.v3"
GENERATION_RECIPE_SCHEMA_V4 = "alc.translate.generation_recipe.v4"
LANGUAGE_RESULT_SCHEMA = "alc.translate.language_result.v1"
GLOSSARY_RESULT_SCHEMA = "alc.translate.glossary_result.v2"
LEGACY_GLOSSARY_RESULT_SCHEMA = "alc.translate.glossary_result.v1"
GLOSSARY_FALLBACK_SUMMARY_SCHEMA = "alc.translate.glossary_fallback_summary.v1"
TRANSLATION_RESULT_SCHEMA = "alc.translate.translation_result.v1"

DEFAULT_GLOSSARY_INPUT_BUDGET_BYTES = 32_000
DEFAULT_TRANSLATION_INPUT_BUDGET_BYTES = 32_000

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class TranslationSource:
    """The immutable RichDocument that exclusively anchors translation."""

    rich: RichDocument

    def __post_init__(self) -> None:
        if not isinstance(self.rich, RichDocument):
            raise ValueError("rich must be a RichDocument")

    @property
    def source_digest(self) -> str:
        return self.rich.source.artifact_digest

    @property
    def document_digest(self) -> str:
        return self.rich.document_digest


@dataclass(frozen=True)
class LanguageRequest:
    source: TranslationSource
    target_language: str

    def __post_init__(self) -> None:
        _require_language(self.target_language, "target_language")
        object.__setattr__(self, "target_language", self.target_language.strip())


@dataclass(frozen=True)
class GlossaryRequest:
    source: TranslationSource
    target_language: str
    approx_count: int
    language_result: ArtifactSourceRef

    def __post_init__(self) -> None:
        _require_language(self.target_language, "target_language")
        if (
            isinstance(self.approx_count, bool)
            or not isinstance(self.approx_count, int)
            or not 1 <= self.approx_count <= 200
        ):
            raise ValueError("approx_count must be between 1 and 200")
        if not isinstance(self.language_result, ArtifactSourceRef):
            raise ValueError("language_result must be an ArtifactSourceRef")
        object.__setattr__(self, "target_language", self.target_language.strip())


@dataclass(frozen=True)
class BlocksRequest:
    source: TranslationSource
    target_language: str
    language_result: ArtifactSourceRef
    glossary_result: ArtifactSourceRef

    def __post_init__(self) -> None:
        _require_language(self.target_language, "target_language")
        if not isinstance(self.language_result, ArtifactSourceRef):
            raise ValueError("language_result must be an ArtifactSourceRef")
        if not isinstance(self.glossary_result, ArtifactSourceRef):
            raise ValueError("glossary_result must be an ArtifactSourceRef")
        object.__setattr__(self, "target_language", self.target_language.strip())


@dataclass(frozen=True)
class GenerationRecipe:
    model: ModelSelection = field(default_factory=ModelSelection)
    glossary_input_budget_bytes: int = DEFAULT_GLOSSARY_INPUT_BUDGET_BYTES
    translation_input_budget_bytes: int = DEFAULT_TRANSLATION_INPUT_BUDGET_BYTES
    processing_mode: str | None = None
    user_intent: str = ""
    review_rounds: int | None = None

    def __post_init__(self) -> None:
        if self.review_rounds is not None and (
            type(self.review_rounds) is not int or self.review_rounds not in (0, 1, 2)
        ):
            raise ValueError("review_rounds must be 0, 1, 2 or None")
        if self.processing_mode not in {None, "fast", "standard", "deep"}:
            raise ValueError("Unsupported processing mode")
        if not isinstance(self.model, ModelSelection):
            raise ValueError("model must be a ModelSelection")
        if not isinstance(self.user_intent, str) or len(self.user_intent) > 8_000:
            raise ValueError("user_intent must be a string of at most 8000 characters")
        object.__setattr__(self, "user_intent", self.user_intent.strip())
        for name in (
            "glossary_input_budget_bytes",
            "translation_input_budget_bytes",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 4_096 <= value <= 1_000_000
            ):
                raise ValueError(f"{name} must be between 4096 and 1000000")


@dataclass(frozen=True)
class ExecutionOptions:
    llm: LLMExecutionOptions = field(default_factory=LLMExecutionOptions)
    window_workers: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.llm, LLMExecutionOptions):
            raise ValueError("llm must be LLMExecutionOptions")
        if (
            isinstance(self.window_workers, bool)
            or not isinstance(self.window_workers, int)
            or not 1 <= self.window_workers <= 32
        ):
            raise ValueError("window_workers must be an integer between 1 and 32")


def source_to_document(source: TranslationSource) -> dict[str, JsonValue]:
    return {
        "schema_version": SOURCE_SCHEMA,
        "rich": rich_document_to_document(source.rich),
    }


def source_from_document(value: Mapping[str, Any]) -> TranslationSource:
    document = _exact(value, {"schema_version", "rich"}, "source")
    if document["schema_version"] != SOURCE_SCHEMA:
        raise ValueError("unsupported translation source schema")
    raw_rich = document["rich"]
    if not isinstance(raw_rich, Mapping):
        raise ValueError("source rich projection must be an object")
    return TranslationSource(rich_document_from_document(raw_rich))


def artifact_source_to_document(
    source: ArtifactSourceRef,
) -> dict[str, JsonValue]:
    return {
        "source_run_id": source.source_run_id,
        "source_artifact_id": source.source_artifact_id,
        "expected_digest": encode_artifact_digest(source.expected_digest),
    }


def artifact_source_from_document(value: Any) -> ArtifactSourceRef:
    document = _exact(
        _mapping(value, "artifact source"),
        {"source_run_id", "source_artifact_id", "expected_digest"},
        "artifact source",
    )
    run_id = _string(document, "source_run_id")
    artifact_id = _string(document, "source_artifact_id")
    digest = decode_artifact_digest(document["expected_digest"])
    return ArtifactSourceRef(run_id, artifact_id, digest)


def recipe_to_document(recipe: GenerationRecipe) -> dict[str, JsonValue]:
    model = {
        "provider": recipe.model.provider,
        "model": recipe.model.model,
        "tier": recipe.model.tier,
    }
    if recipe.model.reasoning_effort is not None:
        model["reasoning_effort"] = recipe.model.reasoning_effort
    document = {
        "schema_version": GENERATION_RECIPE_SCHEMA,
        "model": model,
        "glossary_input_budget_bytes": recipe.glossary_input_budget_bytes,
        "translation_input_budget_bytes": recipe.translation_input_budget_bytes,
    }
    if (
        recipe.processing_mode is not None
        or recipe.user_intent
        or recipe.review_rounds is not None
    ):
        from ac_llm.request import model_selection_to_document

        document.update(
            schema_version=GENERATION_RECIPE_SCHEMA_V2,
            model=model_selection_to_document(recipe.model),
            processing_mode=recipe.processing_mode,
        )
    if recipe.user_intent or recipe.review_rounds is not None:
        document.update(
            schema_version=GENERATION_RECIPE_SCHEMA_V3,
            user_intent=recipe.user_intent,
        )
    if recipe.review_rounds is not None:
        document.update(
            schema_version=GENERATION_RECIPE_SCHEMA_V4,
            review_rounds=recipe.review_rounds,
        )
    return document


def recipe_from_document(value: Mapping[str, Any]) -> GenerationRecipe:
    if value.get("schema_version") == GENERATION_RECIPE_SCHEMA_V4:
        from dataclasses import replace

        raw = dict(value)
        rounds = raw.pop("review_rounds")
        if type(rounds) is not int or rounds not in (0, 1, 2):
            raise ValueError("review_rounds must be 0, 1 or 2")
        raw["schema_version"] = GENERATION_RECIPE_SCHEMA_V3
        return replace(recipe_from_document(raw), review_rounds=rounds)
    if value.get("schema_version") == GENERATION_RECIPE_SCHEMA_V3:
        from dataclasses import replace

        raw = dict(value)
        intent = _string(raw, "user_intent")
        raw.pop("user_intent")
        raw["schema_version"] = GENERATION_RECIPE_SCHEMA_V2
        return replace(recipe_from_document(raw), user_intent=intent)
    if value.get("schema_version") == GENERATION_RECIPE_SCHEMA_V2:
        from dataclasses import replace
        from ac_llm.request import decode_model_selection

        raw = dict(value)
        mode = raw.pop("processing_mode")
        model = decode_model_selection(
            raw["model"], extended="reasoning_effort" in raw["model"]
        )
        raw["schema_version"] = GENERATION_RECIPE_SCHEMA
        raw["model"] = {
            "provider": model.provider,
            "model": model.model,
            "tier": model.tier,
        }
        return replace(recipe_from_document(raw), model=model, processing_mode=mode)
    document = _exact(
        value,
        {
            "schema_version",
            "model",
            "glossary_input_budget_bytes",
            "translation_input_budget_bytes",
        },
        "generation recipe",
    )
    if document["schema_version"] != GENERATION_RECIPE_SCHEMA:
        raise ValueError("unsupported generation recipe schema")
    model = _mapping(document["model"], "generation model")
    if set(model) not in (
        {"provider", "model", "tier"},
        {"provider", "model", "tier", "reasoning_effort"},
    ):
        raise ValueError("generation model contains unknown or missing fields")
    exact_model = model["model"]
    if exact_model is not None and not isinstance(exact_model, str):
        raise ValueError("model.model must be a string or null")
    return GenerationRecipe(
        model=ModelSelection(
            provider=_string(model, "provider"),
            model=exact_model,
            tier=_string(model, "tier"),  # type: ignore[arg-type]
            reasoning_effort=(
                None
                if "reasoning_effort" not in model
                else _string(model, "reasoning_effort")
            ),  # type: ignore[arg-type]
        ),
        glossary_input_budget_bytes=_integer(document, "glossary_input_budget_bytes"),
        translation_input_budget_bytes=_integer(
            document, "translation_input_budget_bytes"
        ),
    )


def language_semantic_input(
    request: LanguageRequest, recipe: GenerationRecipe
) -> dict[str, JsonValue]:
    return {
        "request": {
            "schema_version": LANGUAGE_REQUEST_SCHEMA,
            "source": source_to_document(request.source),
            "target_language": request.target_language,
        },
        "generation_recipe": recipe_to_document(recipe),
    }


def decode_language_semantic_input(
    value: Mapping[str, Any],
) -> tuple[LanguageRequest, GenerationRecipe]:
    outer = _exact(value, {"request", "generation_recipe"}, "semantic input")
    request = _exact(
        _mapping(outer["request"], "language request"),
        {"schema_version", "source", "target_language"},
        "language request",
    )
    if request["schema_version"] != LANGUAGE_REQUEST_SCHEMA:
        raise ValueError("unsupported language request schema")
    return (
        LanguageRequest(
            source_from_document(_mapping(request["source"], "source")),
            _string(request, "target_language"),
        ),
        recipe_from_document(_mapping(outer["generation_recipe"], "generation recipe")),
    )


def glossary_semantic_input(
    request: GlossaryRequest, recipe: GenerationRecipe
) -> dict[str, JsonValue]:
    return {
        "request": {
            "schema_version": GLOSSARY_REQUEST_SCHEMA,
            "source": source_to_document(request.source),
            "target_language": request.target_language,
            "approx_count": request.approx_count,
            "language_result": artifact_source_to_document(request.language_result),
        },
        "generation_recipe": recipe_to_document(recipe),
    }


def decode_glossary_semantic_input(
    value: Mapping[str, Any],
) -> tuple[GlossaryRequest, GenerationRecipe]:
    outer = _exact(value, {"request", "generation_recipe"}, "semantic input")
    request = _exact(
        _mapping(outer["request"], "glossary request"),
        {
            "schema_version",
            "source",
            "target_language",
            "approx_count",
            "language_result",
        },
        "glossary request",
    )
    if request["schema_version"] != GLOSSARY_REQUEST_SCHEMA:
        raise ValueError("unsupported glossary request schema")
    return (
        GlossaryRequest(
            source_from_document(_mapping(request["source"], "source")),
            _string(request, "target_language"),
            _integer(request, "approx_count"),
            artifact_source_from_document(request["language_result"]),
        ),
        recipe_from_document(_mapping(outer["generation_recipe"], "generation recipe")),
    )


def blocks_semantic_input(
    request: BlocksRequest, recipe: GenerationRecipe
) -> dict[str, JsonValue]:
    return {
        "request": {
            "schema_version": BLOCKS_REQUEST_SCHEMA,
            "source": source_to_document(request.source),
            "target_language": request.target_language,
            "language_result": artifact_source_to_document(request.language_result),
            "glossary_result": artifact_source_to_document(request.glossary_result),
        },
        "generation_recipe": recipe_to_document(recipe),
    }


def decode_blocks_semantic_input(
    value: Mapping[str, Any],
) -> tuple[BlocksRequest, GenerationRecipe]:
    outer = _exact(value, {"request", "generation_recipe"}, "semantic input")
    request = _exact(
        _mapping(outer["request"], "blocks request"),
        {
            "schema_version",
            "source",
            "target_language",
            "language_result",
            "glossary_result",
        },
        "blocks request",
    )
    if request["schema_version"] != BLOCKS_REQUEST_SCHEMA:
        raise ValueError("unsupported blocks request schema")
    return (
        BlocksRequest(
            source_from_document(_mapping(request["source"], "source")),
            _string(request, "target_language"),
            artifact_source_from_document(request["language_result"]),
            artifact_source_from_document(request["glossary_result"]),
        ),
        recipe_from_document(_mapping(outer["generation_recipe"], "generation recipe")),
    )


def artifact_source(
    run_id: str, artifact_id: str, digest: ArtifactDigest
) -> ArtifactSourceRef:
    return ArtifactSourceRef(run_id, artifact_id, digest)


def _require_language(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty language tag")


def _exact(
    value: Mapping[str, Any], fields: set[str], description: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{description} has invalid fields")
    return dict(value)


def _mapping(value: Any, description: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{description} must be an object")
    return value


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key} must be a string")
    return item


def _integer(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise ValueError(f"{key} must be an integer")
    return item


__all__ = [
    "DEFAULT_GLOSSARY_INPUT_BUDGET_BYTES",
    "DEFAULT_TRANSLATION_INPUT_BUDGET_BYTES",
    "GLOSSARY_FALLBACK_SUMMARY_SCHEMA",
    "GLOSSARY_RESULT_SCHEMA",
    "LANGUAGE_RESULT_SCHEMA",
    "LEGACY_GLOSSARY_RESULT_SCHEMA",
    "TRANSLATION_RESULT_SCHEMA",
    "BlocksRequest",
    "ExecutionOptions",
    "GenerationRecipe",
    "GlossaryRequest",
    "LanguageRequest",
    "TranslationSource",
    "artifact_source",
    "blocks_semantic_input",
    "decode_blocks_semantic_input",
    "decode_glossary_semantic_input",
    "decode_language_semantic_input",
    "glossary_semantic_input",
    "language_semantic_input",
    "source_from_document",
    "source_to_document",
]
