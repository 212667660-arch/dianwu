from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time
from typing import Literal

from backend.config import Settings
from backend.errors import (
    ModelAccessError,
    ModelAuthenticationError,
    ModelFailoverExhaustedError,
    ModelRateLimitError,
    ModelProfileDisabledError,
    ModelProfileNeedsAttentionError,
    ModelProfileNotFoundError,
    ModelRuntimeApplyFailedError,
)
from backend.models.schemas import ModelConnectionTestResponse, ModelDefinition, ModelProfileSecret, ModelRuntimeSnapshotInput, ModelSettingsResponse
from backend.services.content_safety.concurrency import model_call_slot
from backend.services.llm_service import ModelGateway
from backend.services.model_capabilities import ReasoningEffort, effective_effort, reasoning_payload
from backend.services.model_resilience import AttemptBudget, CircuitBreaker, RetryClass, classify_error


@dataclass(frozen=True)
class RuntimeSelection:
    profile_mode: Literal["auto", "manual"] = "auto"
    preferred_profile_id: str | None = None
    model_id: str | None = None
    reasoning_effort: ReasoningEffort = "auto"
    failover_enabled: bool | None = None


@dataclass(frozen=True)
class RoutedCompletion:
    text: str
    profile_id: str
    model_id: str
    requested_reasoning_effort: ReasoningEffort
    effective_reasoning_effort: ReasoningEffort
    failover_used: bool


@dataclass(frozen=True)
class RoutedStreamEvent:
    event: Literal["meta", "delta", "interrupted"]
    profile_id: str | None = None
    model_id: str | None = None
    requested_reasoning_effort: ReasoningEffort | None = None
    effective_reasoning_effort: ReasoningEffort | None = None
    failover_used: bool = False
    content: str | None = None
    code: str | None = None
    can_continue_with_backup: bool = False


@dataclass(frozen=True)
class RuntimeProfileStatus:
    profile_id: str
    enabled: bool
    needs_attention: bool
    circuit_state: str
    cooldown_until: float
    consecutive_failures: int


@dataclass(frozen=True)
class RuntimeStatus:
    ready: bool
    default_profile_id: str | None
    auto_failover: bool
    fallback_profile_ids: tuple[str, ...]
    profiles: tuple[RuntimeProfileStatus, ...]


@dataclass
class _RuntimeProfile:
    definition: ModelProfileSecret
    gateway: object
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    needs_attention: bool = False


@dataclass
class _RuntimeSnapshot:
    value: ModelRuntimeSnapshotInput
    profiles: dict[str, _RuntimeProfile]
    active_requests: int = 0
    retired: bool = False
    closed: bool = False


def _default_gateway_factory(profile: ModelProfileSecret) -> ModelGateway:
    return ModelGateway(Settings(
        model_provider=profile.provider,
        model_api_key=profile.api_key,
        model_base_url=profile.base_url,
        model_name=next(
            model.provider_model_name
            for model in profile.models
            if model.id == profile.default_model_id
        ),
        anthropic_version=profile.anthropic_version,
        request_timeout_seconds=profile.request_timeout_seconds,
    ))


class ModelRuntimeRouter:
    def __init__(
        self,
        *,
        gateway_factory: Callable[[ModelProfileSecret], object] = _default_gateway_factory,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway_factory = gateway_factory
        self._clock = clock
        self._sleeper = sleeper
        self._snapshot = _RuntimeSnapshot(
            value=ModelRuntimeSnapshotInput(
                default_profile_id=None,
                auto_failover=True,
                fallback_profile_ids=[],
                profiles=[],
            ),
            profiles={},
        )
        self._swap_lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._snapshot.value.default_profile_id is not None

    async def apply_snapshot(self, value: ModelRuntimeSnapshotInput) -> RuntimeStatus:
        candidate_profiles: dict[str, _RuntimeProfile] = {}
        try:
            for profile in value.profiles:
                candidate_profiles[profile.id] = _RuntimeProfile(
                    definition=profile,
                    gateway=self._gateway_factory(profile),
                    breaker=CircuitBreaker(clock=self._clock),
                )
        except Exception as exc:
            await self._close_gateways(candidate_profiles.values())
            raise ModelRuntimeApplyFailedError() from exc
        candidate = _RuntimeSnapshot(value=value, profiles=candidate_profiles)
        async with self._swap_lock:
            previous = self._snapshot
            self._snapshot = candidate
            previous.retired = True
        if previous.active_requests == 0:
            await self._close_snapshot(previous)
        return self.status()

    async def test_profile(self, profile: ModelProfileSecret) -> ModelConnectionTestResponse:
        started = self._clock()
        gateway = self._gateway_factory(profile)
        model = self._model_for(profile, profile.default_model_id)
        try:
            await gateway.complete(
                [{"role": "user", "content": "Reply with OK."}],
                0.0,
                model_name=model.provider_model_name,
                reasoning={},
                max_output_tokens=512,
            )
        finally:
            close = getattr(gateway, "aclose", None)
            if close is not None:
                await close()
        return ModelConnectionTestResponse(
            provider=profile.provider,
            model_name=model.provider_model_name,
            status="connected",
            latency_ms=max(0, round((self._clock() - started) * 1000)),
        )

    def status(self) -> RuntimeStatus:
        snapshot = self._snapshot
        return RuntimeStatus(
            ready=self.is_ready,
            default_profile_id=snapshot.value.default_profile_id,
            auto_failover=snapshot.value.auto_failover,
            fallback_profile_ids=tuple(snapshot.value.fallback_profile_ids),
            profiles=tuple(
                RuntimeProfileStatus(
                    profile_id=profile.id,
                    enabled=profile.enabled,
                    needs_attention=snapshot.profiles[profile.id].needs_attention,
                    circuit_state=snapshot.profiles[profile.id].breaker.state,
                    cooldown_until=snapshot.profiles[profile.id].breaker.cooldown_until,
                    consecutive_failures=snapshot.profiles[profile.id].breaker.consecutive_failures,
                )
                for profile in snapshot.value.profiles
            ),
        )

    def reviewer_candidate_ids(
        self,
        generation_profile_id: str | None = None,
    ) -> tuple[str, ...]:
        snapshot = self._snapshot
        ordered: list[str] = []
        if snapshot.value.default_profile_id is not None:
            ordered.append(snapshot.value.default_profile_id)
        ordered.extend(snapshot.value.fallback_profile_ids)
        ordered.extend(profile.id for profile in snapshot.value.profiles)
        enabled = [
            profile_id
            for profile_id in dict.fromkeys(ordered)
            if (
                profile_id in snapshot.profiles
                and snapshot.profiles[profile_id].definition.enabled
                and not snapshot.profiles[profile_id].needs_attention
            )
        ]
        if generation_profile_id in enabled:
            enabled = [
                profile_id for profile_id in enabled
                if profile_id != generation_profile_id
            ] + [generation_profile_id]
        return tuple(enabled)

    def generation_candidate_id(
        self,
        selection: RuntimeSelection,
    ) -> str | None:
        snapshot = self._snapshot
        if not snapshot.profiles:
            return None
        try:
            candidates = self._candidate_ids(snapshot, selection)
        except Exception:
            return None
        return candidates[0] if candidates else None

    def legacy_model_settings(self) -> ModelSettingsResponse | None:
        snapshot = self._snapshot
        profile_id = snapshot.value.default_profile_id
        if profile_id is None:
            return None
        runtime_profile = snapshot.profiles.get(profile_id)
        if runtime_profile is None:
            return None
        profile = runtime_profile.definition
        model = next(
            (value for value in profile.models if value.id == profile.default_model_id),
            None,
        )
        if model is None:
            return None
        return ModelSettingsResponse(
            provider=profile.provider,
            base_url=profile.base_url,
            model_name=model.provider_model_name,
            api_key_configured=True,
            api_key_hint="configured",
            anthropic_version=profile.anthropic_version,
            request_timeout_seconds=profile.request_timeout_seconds,
        )

    @asynccontextmanager
    async def _lease(self):
        async with self._swap_lock:
            snapshot = self._snapshot
            snapshot.active_requests += 1
        try:
            yield snapshot
        finally:
            should_close = False
            async with self._swap_lock:
                snapshot.active_requests -= 1
                should_close = snapshot.retired and snapshot.active_requests == 0
            if should_close:
                await self._close_snapshot(snapshot)

    def _candidate_ids(
        self,
        snapshot: _RuntimeSnapshot,
        selection: RuntimeSelection,
    ) -> list[str]:
        default_id = snapshot.value.default_profile_id
        if default_id is None:
            raise ModelProfileNotFoundError()
        primary_id = default_id
        if selection.profile_mode == "manual":
            if selection.preferred_profile_id is None:
                raise ModelProfileNotFoundError()
            primary_id = selection.preferred_profile_id
            profile = snapshot.profiles.get(primary_id)
            if profile is None:
                raise ModelProfileNotFoundError()
            if not profile.definition.enabled:
                raise ModelProfileDisabledError()
        allow_failover = (
            snapshot.value.auto_failover
            if selection.failover_enabled is None
            else selection.failover_enabled
        )
        values = [primary_id]
        if allow_failover:
            values.append(default_id)
            values.extend(snapshot.value.fallback_profile_ids)
        return list(dict.fromkeys(values))

    @staticmethod
    def _model_for(
        profile: ModelProfileSecret,
        requested_model_id: str | None,
    ) -> ModelDefinition:
        if requested_model_id is not None:
            for model in profile.models:
                if model.id == requested_model_id:
                    return model
        return next(model for model in profile.models if model.id == profile.default_model_id)

    @staticmethod
    def _retry_after_seconds(error: BaseException) -> float | None:
        if not isinstance(error, ModelRateLimitError):
            return None
        return error.retry_after_seconds

    def _can_retry_after(
        self,
        budget: AttemptBudget,
        retry_after_seconds: float | None,
        retry_used: bool,
    ) -> bool:
        if retry_used or retry_after_seconds is None:
            return False
        remaining = budget.deadline - self._clock()
        return (
            retry_after_seconds < remaining
            and budget.attempts < budget.max_attempts
        )

    async def complete(
        self,
        selection: RuntimeSelection,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> RoutedCompletion:
        async with model_call_slot():
            return await self._complete_within_slot(
                selection,
                messages,
                temperature,
            )

    async def _complete_within_slot(
        self,
        selection: RuntimeSelection,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> RoutedCompletion:
        async with self._lease() as snapshot:
            candidates = self._candidate_ids(snapshot, selection)
            first_profile_id = candidates[0]
            primary = snapshot.profiles.get(first_profile_id)
            if primary is None:
                raise ModelProfileNotFoundError()
            budget = AttemptBudget(
                deadline=self._clock() + primary.definition.request_timeout_seconds,
            )
            for profile_id in candidates:
                runtime_profile = snapshot.profiles.get(profile_id)
                if runtime_profile is None or not runtime_profile.definition.enabled:
                    continue
                if runtime_profile.needs_attention:
                    if profile_id == first_profile_id:
                        raise ModelProfileNeedsAttentionError()
                    continue
                model = self._model_for(runtime_profile.definition, selection.model_id)
                effective = effective_effort(
                    selection.reasoning_effort,
                    model.supported_reasoning_efforts,
                )
                reasoning = reasoning_payload(model.reasoning_adapter, effective)
                retry_after_used = False
                while runtime_profile.breaker.allow_request():
                    if not budget.consume(profile_id, self._clock()):
                        break
                    try:
                        text = await runtime_profile.gateway.complete(
                            messages,
                            temperature,
                            model_name=model.provider_model_name,
                            reasoning=reasoning,
                            max_output_tokens=model.max_output_tokens,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        retry_class = classify_error(exc)
                        retry_after_seconds = self._retry_after_seconds(exc)
                        runtime_profile.breaker.record_failure(
                            retry_class,
                            retry_after_seconds=retry_after_seconds,
                        )
                        if isinstance(exc, (ModelAuthenticationError, ModelAccessError)):
                            runtime_profile.needs_attention = True
                        if retry_class is RetryClass.TERMINAL:
                            raise
                        if self._can_retry_after(budget, retry_after_seconds, retry_after_used):
                            retry_after_used = True
                            await self._sleeper(retry_after_seconds)
                            continue
                        break
                    runtime_profile.breaker.record_success()
                    runtime_profile.needs_attention = False
                    return RoutedCompletion(
                        text=text,
                        profile_id=profile_id,
                        model_id=model.id,
                        requested_reasoning_effort=selection.reasoning_effort,
                        effective_reasoning_effort=effective,
                        failover_used=profile_id != first_profile_id,
                    )
        raise ModelFailoverExhaustedError()

    async def stream(
        self,
        selection: RuntimeSelection,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ):
        async with model_call_slot():
            async for event in self._stream_within_slot(
                selection,
                messages,
                temperature,
            ):
                yield event

    async def _stream_within_slot(
        self,
        selection: RuntimeSelection,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ):
        async with self._lease() as snapshot:
            candidates = self._candidate_ids(snapshot, selection)
            first_profile_id = candidates[0]
            primary = snapshot.profiles.get(first_profile_id)
            if primary is None:
                raise ModelProfileNotFoundError()
            budget = AttemptBudget(deadline=self._clock() + primary.definition.request_timeout_seconds)
            for index, profile_id in enumerate(candidates):
                runtime_profile = snapshot.profiles.get(profile_id)
                if runtime_profile is None or not runtime_profile.definition.enabled:
                    continue
                if runtime_profile.needs_attention:
                    if profile_id == first_profile_id:
                        raise ModelProfileNeedsAttentionError()
                    continue
                model = self._model_for(runtime_profile.definition, selection.model_id)
                effective = effective_effort(selection.reasoning_effort, model.supported_reasoning_efforts)
                reasoning = reasoning_payload(model.reasoning_adapter, effective)
                retry_after_used = False
                while runtime_profile.breaker.allow_request():
                    if not budget.consume(profile_id, self._clock()):
                        break
                    emitted = False
                    try:
                        async for delta in runtime_profile.gateway.stream(
                            messages,
                            temperature,
                            model_name=model.provider_model_name,
                            reasoning=reasoning,
                            max_output_tokens=model.max_output_tokens,
                        ):
                            if not emitted:
                                emitted = True
                                yield RoutedStreamEvent(
                                    event="meta",
                                    profile_id=profile_id,
                                    model_id=model.id,
                                    requested_reasoning_effort=selection.reasoning_effort,
                                    effective_reasoning_effort=effective,
                                    failover_used=profile_id != first_profile_id,
                                )
                            yield RoutedStreamEvent(event="delta", content=delta)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        retry_class = classify_error(exc)
                        retry_after_seconds = self._retry_after_seconds(exc)
                        runtime_profile.breaker.record_failure(
                            retry_class,
                            retry_after_seconds=retry_after_seconds,
                        )
                        if isinstance(exc, (ModelAuthenticationError, ModelAccessError)):
                            runtime_profile.needs_attention = True
                        if emitted and retry_class is RetryClass.RETRYABLE:
                            yield RoutedStreamEvent(
                                event="interrupted",
                                profile_id=profile_id,
                                model_id=model.id,
                                requested_reasoning_effort=selection.reasoning_effort,
                                effective_reasoning_effort=effective,
                                failover_used=profile_id != first_profile_id,
                                code="MODEL_STREAM_INTERRUPTED",
                                can_continue_with_backup=index + 1 < len(candidates),
                            )
                            return
                        if retry_class is RetryClass.TERMINAL:
                            raise
                        if self._can_retry_after(budget, retry_after_seconds, retry_after_used):
                            retry_after_used = True
                            await self._sleeper(retry_after_seconds)
                            continue
                        break
                    if emitted:
                        runtime_profile.breaker.record_success()
                        runtime_profile.needs_attention = False
                        return
                    break
        raise ModelFailoverExhaustedError()

    async def stream_text(
        self,
        selection: RuntimeSelection,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ):
        async for event in self.stream(selection, messages, temperature):
            if event.event == "delta" and event.content:
                yield event.content

    async def close(self) -> None:
        async with self._swap_lock:
            snapshot = self._snapshot
            snapshot.retired = True
            self._snapshot = _RuntimeSnapshot(
                value=ModelRuntimeSnapshotInput(
                    default_profile_id=None,
                    auto_failover=True,
                    fallback_profile_ids=[],
                    profiles=[],
                ),
                profiles={},
            )
        if snapshot.active_requests == 0:
            await self._close_snapshot(snapshot)

    async def _close_snapshot(self, snapshot: _RuntimeSnapshot) -> None:
        if snapshot.closed:
            return
        snapshot.closed = True
        await self._close_gateways(snapshot.profiles.values())

    @staticmethod
    async def _close_gateways(profiles) -> None:
        seen: set[int] = set()
        for runtime_profile in profiles:
            gateway = runtime_profile.gateway
            if id(gateway) in seen:
                continue
            seen.add(id(gateway))
            close = getattr(gateway, "aclose", None)
            if close is not None:
                await close()


model_runtime_router = ModelRuntimeRouter()


def legacy_snapshot_from_settings(settings: Settings) -> ModelRuntimeSnapshotInput:
    if not settings.is_model_configured:
        return ModelRuntimeSnapshotInput()
    model = ModelDefinition(
        id="legacy-model",
        provider_model_name=settings.resolved_model_name,
        label=settings.resolved_model_name,
        max_output_tokens=4096,
        supported_reasoning_efforts=["auto", "off"],
        reasoning_adapter="none",
    )
    profile = ModelProfileSecret(
        id="legacy-development",
        label="开发环境模型",
        enabled=True,
        provider=settings.resolved_provider,
        base_url=settings.resolved_base_url,
        api_key=settings.resolved_api_key,
        anthropic_version=settings.anthropic_version,
        request_timeout_seconds=settings.request_timeout_seconds,
        default_model_id=model.id,
        models=[model],
    )
    return ModelRuntimeSnapshotInput(
        default_profile_id=profile.id,
        auto_failover=False,
        fallback_profile_ids=[],
        profiles=[profile],
    )
