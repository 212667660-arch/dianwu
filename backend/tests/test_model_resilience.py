from __future__ import annotations

import httpx
import pytest

from backend.errors import (
    ModelCapabilityUnsupportedError,
    ModelFailoverExhaustedError,
    ModelProfileDisabledError,
    ModelProfileNeedsAttentionError,
    ModelProfileNotFoundError,
    ModelRuntimeApplyFailedError,
    ModelRuntimeSnapshotInvalidError,
    ModelStreamInterruptedError,
)
from backend.services.model_resilience import (
    AttemptBudget,
    CircuitBreaker,
    RetryClass,
    classify_error,
)


def test_breaker_opens_after_three_retryable_failures_and_half_opens_once() -> None:
    now = [100.0]
    breaker = CircuitBreaker(clock=lambda: now[0])

    for _ in range(3):
        breaker.record_failure(RetryClass.RETRYABLE)

    assert breaker.state == "open"
    assert breaker.allow_request() is False
    now[0] += 31
    assert breaker.allow_request() is True
    assert breaker.state == "half_open"
    assert breaker.allow_request() is False
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.consecutive_failures == 0


def test_breaker_uses_progressive_cooldown_and_terminal_errors_do_not_open() -> None:
    now = [10.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    breaker.record_failure(RetryClass.TERMINAL)
    assert breaker.state == "closed"
    assert breaker.consecutive_failures == 0

    for _ in range(3):
        breaker.record_failure(RetryClass.RETRYABLE)
    first_until = breaker.cooldown_until
    now[0] = first_until + 1
    assert breaker.allow_request() is True
    breaker.record_failure(RetryClass.RETRYABLE)
    assert breaker.state == "open"
    assert breaker.cooldown_until - now[0] == pytest.approx(60)


def test_breaker_uses_retry_after_as_immediate_rate_limit_cooldown() -> None:
    now = [100.0]
    breaker = CircuitBreaker(clock=lambda: now[0])

    breaker.record_failure(RetryClass.RETRYABLE, retry_after_seconds=90.0)

    assert breaker.state == "open"
    assert breaker.consecutive_failures == 1
    assert breaker.cooldown_until == pytest.approx(190.0)
    assert breaker.allow_request() is False


@pytest.mark.parametrize("status", [408, 429, 502, 503, 504])
def test_retryable_http_statuses_are_classified(status: int) -> None:
    assert classify_error(status) is RetryClass.RETRYABLE


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_terminal_http_statuses_are_classified(status: int) -> None:
    assert classify_error(status) is RetryClass.TERMINAL


def test_network_and_timeout_failures_are_retryable() -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat")
    assert classify_error(httpx.ConnectError("offline", request=request)) is RetryClass.RETRYABLE
    assert classify_error(httpx.ReadTimeout("slow", request=request)) is RetryClass.RETRYABLE
    assert classify_error(ValueError("bad input")) is RetryClass.TERMINAL


def test_attempt_budget_limits_total_attempts_profiles_and_deadline() -> None:
    budget = AttemptBudget(deadline=50.0)
    assert budget.consume("primary", now=10.0) is True
    assert budget.consume("primary", now=11.0) is True
    assert budget.consume("backup", now=12.0) is True
    assert budget.consume("third", now=13.0) is False
    assert budget.attempts == 3
    assert budget.profile_ids == {"primary", "backup"}

    expired = AttemptBudget(deadline=5.0)
    assert expired.consume("primary", now=5.0) is False


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (ModelProfileNotFoundError(), "MODEL_PROFILE_NOT_FOUND", False),
        (ModelProfileDisabledError(), "MODEL_PROFILE_DISABLED", False),
        (ModelProfileNeedsAttentionError(), "MODEL_PROFILE_NEEDS_ATTENTION", False),
        (ModelCapabilityUnsupportedError(), "MODEL_CAPABILITY_UNSUPPORTED", False),
        (ModelFailoverExhaustedError(), "MODEL_FAILOVER_EXHAUSTED", True),
        (ModelRuntimeSnapshotInvalidError(), "MODEL_RUNTIME_SNAPSHOT_INVALID", False),
        (ModelRuntimeApplyFailedError(), "MODEL_RUNTIME_APPLY_FAILED", False),
        (ModelStreamInterruptedError(), "MODEL_STREAM_INTERRUPTED", True),
    ],
)
def test_model_runtime_errors_have_stable_public_contract(error, code: str, retryable: bool) -> None:
    assert error.code == code
    assert error.retryable is retryable
    assert error.public_message
    assert error.http_status >= 400
