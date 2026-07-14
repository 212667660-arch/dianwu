from backend.services.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_limiter_expires_old_requests_and_reports_retry_after() -> None:
    limiter = SlidingWindowRateLimiter()

    assert limiter.check("client", maximum=2, window_seconds=60, now=0) is None
    assert limiter.check("client", maximum=2, window_seconds=60, now=10) is None
    assert limiter.check("client", maximum=2, window_seconds=60, now=20) == 40
    assert limiter.check("client", maximum=2, window_seconds=60, now=60) is None
