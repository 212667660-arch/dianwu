from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time
from collections.abc import Callable

import httpx

from backend.errors import AppError


class RetryClass(StrEnum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"


_RETRYABLE_HTTP_STATUSES = {408, 429, 502, 503, 504}
_COOLDOWNS = (30.0, 60.0, 120.0, 240.0, 300.0)


def classify_error(error: BaseException | int) -> RetryClass:
    if isinstance(error, int):
        return (
            RetryClass.RETRYABLE
            if error in _RETRYABLE_HTTP_STATUSES
            else RetryClass.TERMINAL
        )
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return RetryClass.RETRYABLE
    if isinstance(error, AppError):
        return RetryClass.RETRYABLE if error.retryable else RetryClass.TERMINAL
    return RetryClass.TERMINAL


@dataclass
class AttemptBudget:
    deadline: float
    max_attempts: int = 3
    max_profiles: int = 2
    attempts: int = 0
    profile_ids: set[str] = field(default_factory=set)

    def consume(self, profile_id: str, now: float) -> bool:
        if now >= self.deadline or self.attempts >= self.max_attempts:
            return False
        if profile_id not in self.profile_ids and len(self.profile_ids) >= self.max_profiles:
            return False
        self.attempts += 1
        self.profile_ids.add(profile_id)
        return True


class CircuitBreaker:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        failure_threshold: int = 3,
    ) -> None:
        self._clock = clock
        self.failure_threshold = failure_threshold
        self.state = "closed"
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self._open_count = 0
        self._half_open_in_flight = False

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self._clock() < self.cooldown_until:
                return False
            self.state = "half_open"
            self._half_open_in_flight = True
            return True
        if self._half_open_in_flight:
            return False
        self._half_open_in_flight = True
        return True

    def record_success(self) -> None:
        self.state = "closed"
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self._open_count = 0
        self._half_open_in_flight = False

    def record_failure(
        self,
        retry_class: RetryClass,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        if retry_class is RetryClass.TERMINAL:
            if self.state == "half_open":
                self.record_success()
            return
        self._half_open_in_flight = False
        if retry_after_seconds is not None and retry_after_seconds > 0:
            self.consecutive_failures += 1
            self._open(cooldown_seconds=min(float(retry_after_seconds), _COOLDOWNS[-1]))
            return
        if self.state == "half_open":
            self._open()
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self._open()

    def _open(self, *, cooldown_seconds: float | None = None) -> None:
        self.state = "open"
        self._open_count += 1
        cooldown = (
            cooldown_seconds
            if cooldown_seconds is not None
            else _COOLDOWNS[min(self._open_count - 1, len(_COOLDOWNS) - 1)]
        )
        self.cooldown_until = self._clock() + cooldown
