from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    ModelDefinition,
    ModelProfileSecret,
    ModelRuntimeSnapshotInput,
)
from backend.services.model_capabilities import effective_effort, reasoning_payload


def model_definition(**overrides: object) -> ModelDefinition:
    value: dict[str, object] = {
        "id": "reasoning-model",
        "provider_model_name": "reasoning-model-v1",
        "label": "深入思考模型",
        "max_output_tokens": 4096,
        "supported_reasoning_efforts": ["auto", "off", "low", "medium", "high"],
        "reasoning_adapter": "openai_reasoning_effort",
    }
    value.update(overrides)
    return ModelDefinition.model_validate(value)


def model_profile(**overrides: object) -> ModelProfileSecret:
    value: dict[str, object] = {
        "id": "primary",
        "label": "主模型服务",
        "enabled": True,
        "provider": "openai",
        "base_url": "https://example.test/v1",
        "api_key": "test-secret-key",
        "anthropic_version": "2023-06-01",
        "request_timeout_seconds": 60,
        "default_model_id": "reasoning-model",
        "models": [model_definition()],
    }
    value.update(overrides)
    return ModelProfileSecret.model_validate(value)


def test_reasoning_effort_uses_nearest_supported_lower_level() -> None:
    assert effective_effort("xhigh", ["auto", "off", "low", "medium", "high"]) == "high"
    assert effective_effort("high", ["auto", "off", "medium"]) == "medium"
    assert effective_effort("low", ["auto", "off", "high"]) == "off"
    assert effective_effort("auto", ["auto", "off", "medium", "high"]) == "auto"


def test_reasoning_adapters_emit_only_whitelisted_fields() -> None:
    assert reasoning_payload("openai_reasoning_effort", "high") == {
        "reasoning_effort": "high"
    }
    assert reasoning_payload("anthropic_thinking", "medium") == {
        "thinking": {"type": "enabled", "budget_tokens": 4096}
    }
    assert reasoning_payload("none", "high") == {}
    assert reasoning_payload("openai_reasoning_effort", "auto") == {}
    assert reasoning_payload("anthropic_thinking", "off") == {}


def test_model_definition_rejects_unknown_fields_control_characters_and_missing_auto() -> None:
    with pytest.raises(ValidationError):
        model_definition(arbitrary_payload={"temperature": 0})
    with pytest.raises(ValidationError):
        model_definition(provider_model_name="unsafe\nmodel")
    with pytest.raises(ValidationError):
        model_definition(supported_reasoning_efforts=["off", "low"])


def test_snapshot_rejects_duplicate_profile_and_model_ids() -> None:
    duplicate_profile = model_profile(label="备用服务")
    with pytest.raises(ValidationError):
        ModelRuntimeSnapshotInput(
            default_profile_id="primary",
            auto_failover=True,
            fallback_profile_ids=[],
            profiles=[model_profile(), duplicate_profile],
        )

    with pytest.raises(ValidationError):
        model_profile(models=[model_definition(), model_definition(label="重复模型")])


def test_snapshot_requires_enabled_default_existing_models_and_unique_fallbacks() -> None:
    with pytest.raises(ValidationError):
        model_profile(default_model_id="missing")
    with pytest.raises(ValidationError):
        ModelRuntimeSnapshotInput(
            default_profile_id="primary",
            auto_failover=True,
            fallback_profile_ids=[],
            profiles=[model_profile(enabled=False)],
        )
    with pytest.raises(ValidationError):
        ModelRuntimeSnapshotInput(
            default_profile_id="missing",
            auto_failover=True,
            fallback_profile_ids=[],
            profiles=[model_profile()],
        )
    with pytest.raises(ValidationError):
        ModelRuntimeSnapshotInput(
            default_profile_id="primary",
            auto_failover=True,
            fallback_profile_ids=["backup", "backup"],
            profiles=[model_profile(), model_profile(id="backup", label="备用服务")],
        )


def test_empty_install_snapshot_is_valid_but_nonempty_snapshot_requires_default() -> None:
    empty = ModelRuntimeSnapshotInput(
        default_profile_id=None,
        auto_failover=True,
        fallback_profile_ids=[],
        profiles=[],
    )
    assert empty.profiles == []
    assert empty.default_profile_id is None

    with pytest.raises(ValidationError):
        ModelRuntimeSnapshotInput(
            default_profile_id=None,
            auto_failover=True,
            fallback_profile_ids=[],
            profiles=[model_profile()],
        )
