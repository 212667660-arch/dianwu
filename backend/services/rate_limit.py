from __future__ import annotations

import math
import time
from collections import deque
from threading import RLock


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = {}
        self._lock = RLock()

    def check(self, key: str, maximum: int, window_seconds: float = 60.0, now: float | None = None) -> int | None:
        if maximum <= 0:
            return None
        current = time.monotonic() if now is None else now
        with self._lock:
            requests = self._requests.setdefault(key, deque())
            while requests and current - requests[0] >= window_seconds:
                requests.popleft()
            if len(requests) >= maximum:
                return max(1, math.ceil(window_seconds - (current - requests[0])))
            requests.append(current)
            return None

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()


rate_limiter = SlidingWindowRateLimiter()
