from __future__ import annotations

import asyncio

import pytest

from backend.errors import ModelAuthenticationError, ModelRuntimeApplyFailedError, ModelTimeoutError
from backend.models.schemas import ModelDefinition, ModelProfileSecret, ModelRuntimeSnapshotInput
from backend.services.model_runtime import ModelRuntimeRouter, RuntimeSelection
from backend.tests.fake_model_gateway import ScriptedGateway


def definition(
    model_id: str = "model-a",
    *,
    supported: list[str] | None = None,
    adapter: str = "openai_reasoning_effort",
) -> ModelDefinition:
    return ModelDefinition.model_validate({
        "id": model_id,
        "provider_model_name": model_id + "-provider",
        "label": model_id,
        "max_output_tokens": 4096,
        "supported_reasoning_efforts": supported or ["auto", "off", "low", "medium", "high"],
        "reasoning_adapter": adapter,
    })


def profile(profile_id: str, *, models: list[ModelDefinition] | None = None) -> ModelProfileSecret:
    model_values = models or [definition()]
    return ModelProfileSecret(
        id=profile_id,
        label=profile_id,
        enabled=True,
        provider="openai",
        base_url=f"https://{profile_id}.example.test/v1",
        api_key=f"{profile_id}-secret-key",
        request_timeout_seconds=60,
        default_model_id=model_values[0].id,
        models=model_values,
    )


def snapshot(*profiles: ModelProfileSecret) -> ModelRuntimeSnapshotInput:
    return ModelRuntimeSnapshotInput(
        default_profile_id=profiles[0].id,
        auto_failover=True,
        fallback_profile_ids=[value.id for value in profiles[1:]],
        profiles=list(profiles),
    )


def selection(**overrides: object) -> RuntimeSelection:
    value: dict[str, object] = {
        "profile_mode": "auto",
        "preferred_profile_id": None,
        "model_id": None,
        "reasoning_effort": "auto",
        "failover_enabled": None,
    }
    value.update(overrides)
    return RuntimeSelection(**value)


def test_retryable_primary_failure_uses_backup_once() -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(completions=[ModelTimeoutError()]),
            "backup": ScriptedGateway(completions=["OK"]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))
        result = await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)
        assert result.text == "OK"
        assert result.profile_id == "backup"
        assert result.failover_used is True
        assert len(gateways["primary"].calls) == 1
        assert len(gateways["backup"].calls) == 1
    asyncio.run(exercise())


def test_authentication_error_does_not_use_backup() -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(completions=[ModelAuthenticationError()]),
            "backup": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))
        with pytest.raises(ModelAuthenticationError):
            await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)
        assert gateways["backup"].calls == []
        assert router.status().profiles[0].needs_attention is True
    asyncio.run(exercise())


def test_manual_profile_model_and_reasoning_are_applied_with_safe_downgrade() -> None:
    async def exercise() -> None:
        primary = ScriptedGateway(completions=["OK"])
        router = ModelRuntimeRouter(gateway_factory=lambda _value: primary)
        await router.apply_snapshot(snapshot(profile("primary", models=[definition(supported=["auto", "off", "low", "medium", "high"])])))
        result = await router.complete(selection(profile_mode="manual", preferred_profile_id="primary", model_id="model-a", reasoning_effort="xhigh", failover_enabled=False), [{"role": "user", "content": "hello"}], 0.2)
        assert result.requested_reasoning_effort == "xhigh"
        assert result.effective_reasoning_effort == "high"
        assert primary.calls[0]["model_name"] == "model-a-provider"
        assert primary.calls[0]["reasoning"] == {"reasoning_effort": "high"}
    asyncio.run(exercise())


def test_snapshot_swap_closes_old_gateway_only_after_active_request_finishes() -> None:
    async def exercise() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class BlockingGateway(ScriptedGateway):
            async def complete(self, *args, **kwargs) -> str:
                entered.set()
                await release.wait()
                return "old"

        old = BlockingGateway()
        new = ScriptedGateway(completions=["new"])
        gateways = iter([old, new])
        router = ModelRuntimeRouter(gateway_factory=lambda _value: next(gateways))
        await router.apply_snapshot(snapshot(profile("primary")))
        running = asyncio.create_task(router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2))
        await entered.wait()
        await router.apply_snapshot(snapshot(profile("primary")))
        assert old.closed is False
        assert (await router.complete(selection(), [{"role": "user", "content": "new"}], 0.2)).text == "new"
        release.set()
        assert (await running).text == "old"
        await asyncio.sleep(0)
        assert old.closed is True
    asyncio.run(exercise())


def test_failed_candidate_snapshot_keeps_existing_runtime_active() -> None:
    async def exercise() -> None:
        current = ScriptedGateway(completions=["still-active"])
        calls = 0
        def factory(_value):
            nonlocal calls
            calls += 1
            if calls == 1:
                return current
            raise RuntimeError("factory failed with test-secret-key")
        router = ModelRuntimeRouter(gateway_factory=factory)
        await router.apply_snapshot(snapshot(profile("primary")))
        with pytest.raises(ModelRuntimeApplyFailedError) as exc_info:
            await router.apply_snapshot(snapshot(profile("replacement")))
        assert "test-secret-key" not in str(exc_info.value)
        assert (await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)).text == "still-active"
    asyncio.run(exercise())
