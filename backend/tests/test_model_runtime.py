from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.errors import ModelAccessError, ModelAuthenticationError, ModelFailoverExhaustedError, ModelNotFoundError, ModelProfileNeedsAttentionError, ModelRateLimitError, ModelRuntimeApplyFailedError, ModelTimeoutError, ModelUnavailableError
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


def profile(
    profile_id: str,
    *,
    models: list[ModelDefinition] | None = None,
    request_timeout_seconds: int = 60,
) -> ModelProfileSecret:
    model_values = models or [definition()]
    return ModelProfileSecret(
        id=profile_id,
        label=profile_id,
        enabled=True,
        provider="openai",
        base_url=f"https://{profile_id}.example.test/v1",
        api_key=f"{profile_id}-secret-key",
        request_timeout_seconds=request_timeout_seconds,
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


def test_reviewer_candidates_prefer_a_different_enabled_profile() -> None:
    async def exercise() -> None:
        router = ModelRuntimeRouter(
            gateway_factory=lambda _value: ScriptedGateway(completions=["OK"]),
        )
        await router.apply_snapshot(snapshot(
            profile("primary"),
            profile("backup"),
            profile("third"),
        ))

        assert router.reviewer_candidate_ids("primary") == ("backup", "third", "primary")
        assert router.reviewer_candidate_ids("backup") == ("primary", "third", "backup")

    asyncio.run(exercise())


def test_complete_calls_share_global_two_request_limit() -> None:
    async def exercise() -> None:
        entered_two = asyncio.Event()
        release = asyncio.Event()

        class ConcurrentGateway(ScriptedGateway):
            def __init__(self) -> None:
                super().__init__()
                self.active = 0
                self.max_active = 0

            async def complete(self, *args, **kwargs) -> str:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.active >= 2:
                    entered_two.set()
                try:
                    await release.wait()
                    return "OK"
                finally:
                    self.active -= 1

        gateway = ConcurrentGateway()
        router = ModelRuntimeRouter(gateway_factory=lambda _value: gateway)
        await router.apply_snapshot(snapshot(profile("primary")))
        tasks = [
            asyncio.create_task(router.complete(
                selection(),
                [{"role": "user", "content": str(index)}],
            ))
            for index in range(3)
        ]

        await entered_two.wait()
        await asyncio.sleep(0)
        assert gateway.max_active == 2
        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(exercise())


def test_stream_calls_hold_global_slot_for_stream_lifetime() -> None:
    async def exercise() -> None:
        entered_two = asyncio.Event()
        release = asyncio.Event()

        class ConcurrentStreamGateway(ScriptedGateway):
            def __init__(self) -> None:
                super().__init__()
                self.active = 0
                self.max_active = 0

            async def stream(self, *args, **kwargs):
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.active >= 2:
                    entered_two.set()
                try:
                    await release.wait()
                    yield "OK"
                finally:
                    self.active -= 1

        gateway = ConcurrentStreamGateway()
        router = ModelRuntimeRouter(gateway_factory=lambda _value: gateway)
        await router.apply_snapshot(snapshot(profile("primary")))

        async def consume(index: int):
            return [event async for event in router.stream(
                selection(),
                [{"role": "user", "content": str(index)}],
            )]

        tasks = [asyncio.create_task(consume(index)) for index in range(3)]
        await entered_two.wait()
        await asyncio.sleep(0)
        assert gateway.max_active == 2
        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(exercise())


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


def test_rate_limit_waits_for_retry_after_and_retries_same_profile_within_deadline() -> None:
    async def exercise() -> None:
        now = [100.0]
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        gateways = {
            "primary": ScriptedGateway(completions=[ModelRateLimitError(2.0), "OK"]),
            "backup": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(
            gateway_factory=lambda value: gateways[value.id],
            clock=lambda: now[0],
            sleeper=sleep,
        )
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))

        result = await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)

        assert result.text == "OK"
        assert result.profile_id == "primary"
        assert sleeps == [2.0]
        assert len(gateways["primary"].calls) == 2
        assert gateways["backup"].calls == []
    asyncio.run(exercise())


def test_rate_limit_longer_than_remaining_deadline_uses_backup_without_waiting() -> None:
    async def exercise() -> None:
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        gateways = {
            "primary": ScriptedGateway(completions=[ModelRateLimitError(6.0)]),
            "backup": ScriptedGateway(completions=["OK"]),
        }
        router = ModelRuntimeRouter(
            gateway_factory=lambda value: gateways[value.id],
            clock=lambda: 100.0,
            sleeper=sleep,
        )
        await router.apply_snapshot(snapshot(
            profile("primary", request_timeout_seconds=5),
            profile("backup"),
        ))

        result = await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)

        assert result.profile_id == "backup"
        assert sleeps == []
        assert len(gateways["primary"].calls) == 1
        assert len(gateways["backup"].calls) == 1
    asyncio.run(exercise())


def test_rate_limit_retry_wait_is_cancellable_without_starting_backup() -> None:
    async def exercise() -> None:
        entered_sleep = asyncio.Event()

        async def sleep(_delay: float) -> None:
            entered_sleep.set()
            await asyncio.Event().wait()

        gateways = {
            "primary": ScriptedGateway(completions=[ModelRateLimitError(2.0)]),
            "backup": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(
            gateway_factory=lambda value: gateways[value.id],
            sleeper=sleep,
        )
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))
        running = asyncio.create_task(router.complete(
            selection(),
            [{"role": "user", "content": "hello"}],
            0.2,
        ))

        await entered_sleep.wait()
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert gateways["backup"].calls == []
    asyncio.run(exercise())


@pytest.mark.parametrize(
    "failure",
    [
        ModelTimeoutError(),
        ModelUnavailableError(),
        ModelRateLimitError(),
        httpx.ConnectError(
            "offline",
            request=httpx.Request("POST", "https://primary.example.test/v1/chat"),
        ),
    ],
)
def test_retryable_fault_matrix_uses_at_most_one_backup_attempt(failure) -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(completions=[failure]),
            "backup": ScriptedGateway(completions=["OK"]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))

        result = await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)

        assert result.profile_id == "backup"
        assert len(gateways["primary"].calls) == 1
        assert len(gateways["backup"].calls) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize(
    "failure",
    [ModelAuthenticationError(), ModelAccessError(), ModelNotFoundError()],
)
def test_terminal_fault_matrix_never_uses_backup(failure) -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(completions=[failure]),
            "backup": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))

        with pytest.raises(type(failure)):
            await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)

        assert len(gateways["primary"].calls) == 1
        assert gateways["backup"].calls == []
    asyncio.run(exercise())


def test_attempt_budget_stops_after_retry_and_one_backup_profile() -> None:
    async def exercise() -> None:
        now = [100.0]

        async def sleep(delay: float) -> None:
            now[0] += delay

        gateways = {
            "primary": ScriptedGateway(completions=[
                ModelRateLimitError(1.0),
                ModelUnavailableError(),
            ]),
            "backup": ScriptedGateway(completions=[ModelUnavailableError()]),
            "third": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(
            gateway_factory=lambda value: gateways[value.id],
            clock=lambda: now[0],
            sleeper=sleep,
        )
        await router.apply_snapshot(snapshot(
            profile("primary"),
            profile("backup"),
            profile("third"),
        ))

        with pytest.raises(ModelFailoverExhaustedError) as exc_info:
            await router.complete(selection(), [{"role": "user", "content": "hello"}], 0.2)

        assert getattr(exc_info.value, "code", None) == "MODEL_FAILOVER_EXHAUSTED"
        assert len(gateways["primary"].calls) == 2
        assert len(gateways["backup"].calls) == 1
        assert gateways["third"].calls == []
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


def test_profile_needing_attention_blocks_later_calls_until_snapshot_replaced() -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(completions=[ModelAuthenticationError()]),
            "backup": ScriptedGateway(completions=["must-not-run"]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))

        with pytest.raises(ModelAuthenticationError):
            await router.complete(selection(), [{"role": "user", "content": "first"}], 0.2)
        with pytest.raises(ModelProfileNeedsAttentionError):
            await router.complete(selection(), [{"role": "user", "content": "second"}], 0.2)

        assert len(gateways["primary"].calls) == 1
        assert gateways["backup"].calls == []
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


def test_zero_output_stream_failure_switches_before_emitting_one_backup_meta() -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(streams=[[ModelUnavailableError()]]),
            "backup": ScriptedGateway(streams=[["A", "B"]]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))
        events = [event async for event in router.stream(
            selection(),
            [{"role": "user", "content": "hello"}],
            0.2,
        )]
        assert [event.event for event in events] == ["meta", "delta", "delta"]
        assert events[0].profile_id == "backup"
        assert events[0].failover_used is True
        assert [event.content for event in events[1:]] == ["A", "B"]
    asyncio.run(exercise())


def test_stream_failure_after_output_is_interrupted_without_backup_text() -> None:
    async def exercise() -> None:
        gateways = {
            "primary": ScriptedGateway(streams=[["partial", ModelUnavailableError()]]),
            "backup": ScriptedGateway(streams=[["must-not-run"]]),
        }
        router = ModelRuntimeRouter(gateway_factory=lambda value: gateways[value.id])
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))
        events = [event async for event in router.stream(
            selection(),
            [{"role": "user", "content": "hello"}],
            0.2,
        )]
        assert [event.event for event in events] == ["meta", "delta", "interrupted"]
        assert events[1].content == "partial"
        assert events[2].code == "MODEL_STREAM_INTERRUPTED"
        assert events[2].can_continue_with_backup is True
        assert gateways["backup"].calls == []
    asyncio.run(exercise())


def test_zero_output_stream_rate_limit_waits_then_retries_same_profile() -> None:
    async def exercise() -> None:
        now = [100.0]
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        gateways = {
            "primary": ScriptedGateway(streams=[
                [ModelRateLimitError(1.0)],
                ["A", "B"],
            ]),
            "backup": ScriptedGateway(streams=[["must-not-run"]]),
        }
        router = ModelRuntimeRouter(
            gateway_factory=lambda value: gateways[value.id],
            clock=lambda: now[0],
            sleeper=sleep,
        )
        await router.apply_snapshot(snapshot(profile("primary"), profile("backup")))

        events = [event async for event in router.stream(
            selection(),
            [{"role": "user", "content": "hello"}],
            0.2,
        )]

        assert [event.event for event in events] == ["meta", "delta", "delta"]
        assert events[0].profile_id == "primary"
        assert sleeps == [1.0]
        assert len(gateways["primary"].calls) == 2
        assert gateways["backup"].calls == []
    asyncio.run(exercise())
