"""Rate limiter for API calls to respect Meta API limits."""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_hour: int = 200  # Meta's default limit
    requests_per_day: int = 4800  # 200 * 24
    posts_per_day: int = 100  # Instagram/Facebook post limit
    min_interval_seconds: float = 1.0  # Minimum time between requests


@dataclass
class RateLimiter:
    """
    Token bucket rate limiter for API calls.

    Implements both per-hour and per-day limits to comply with Meta API restrictions.
    """

    config: RateLimitConfig = field(default_factory=RateLimitConfig)
    _hourly_timestamps: deque = field(default_factory=deque)
    _daily_timestamps: deque = field(default_factory=deque)
    _post_timestamps: deque = field(default_factory=deque)
    _last_request_time: float = field(default=0.0)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _cleanup_old_timestamps(self) -> None:
        """Remove timestamps older than their respective windows."""
        now = time.time()
        hour_ago = now - 3600
        day_ago = now - 86400

        # Clean hourly timestamps
        while self._hourly_timestamps and self._hourly_timestamps[0] < hour_ago:
            self._hourly_timestamps.popleft()

        # Clean daily timestamps
        while self._daily_timestamps and self._daily_timestamps[0] < day_ago:
            self._daily_timestamps.popleft()

        # Clean post timestamps
        while self._post_timestamps and self._post_timestamps[0] < day_ago:
            self._post_timestamps.popleft()

    def _get_wait_time(self) -> float:
        """Calculate how long to wait before next request is allowed."""
        now = time.time()
        self._cleanup_old_timestamps()

        wait_times = []

        # Check minimum interval
        time_since_last = now - self._last_request_time
        if time_since_last < self.config.min_interval_seconds:
            wait_times.append(self.config.min_interval_seconds - time_since_last)

        # Check hourly limit
        if len(self._hourly_timestamps) >= self.config.requests_per_hour:
            oldest_hourly = self._hourly_timestamps[0]
            wait_until = oldest_hourly + 3600
            if wait_until > now:
                wait_times.append(wait_until - now)

        # Check daily limit
        if len(self._daily_timestamps) >= self.config.requests_per_day:
            oldest_daily = self._daily_timestamps[0]
            wait_until = oldest_daily + 86400
            if wait_until > now:
                wait_times.append(wait_until - now)

        return max(wait_times) if wait_times else 0

    def _get_post_wait_time(self) -> float:
        """Calculate wait time for posting (stricter limit)."""
        now = time.time()
        self._cleanup_old_timestamps()

        if len(self._post_timestamps) >= self.config.posts_per_day:
            oldest = self._post_timestamps[0]
            wait_until = oldest + 86400
            if wait_until > now:
                return wait_until - now

        return 0

    async def acquire(self) -> None:
        """
        Acquire permission to make an API request.

        Blocks until a request slot is available.
        """
        async with self._lock:
            wait_time = self._get_wait_time()

            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

            now = time.time()
            self._hourly_timestamps.append(now)
            self._daily_timestamps.append(now)
            self._last_request_time = now

    async def acquire_post(self) -> None:
        """
        Acquire permission to make a post (stricter limits).

        Blocks until a post slot is available.
        """
        async with self._lock:
            # Check both regular rate limit and post limit
            wait_time = max(self._get_wait_time(), self._get_post_wait_time())

            if wait_time > 0:
                logger.warning(f"Post rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

            now = time.time()
            self._hourly_timestamps.append(now)
            self._daily_timestamps.append(now)
            self._post_timestamps.append(now)
            self._last_request_time = now

    def get_remaining_requests(self) -> dict:
        """Get remaining request counts."""
        self._cleanup_old_timestamps()

        return {
            "hourly": self.config.requests_per_hour - len(self._hourly_timestamps),
            "daily": self.config.requests_per_day - len(self._daily_timestamps),
            "posts_today": self.config.posts_per_day - len(self._post_timestamps),
        }

    def get_status(self) -> dict:
        """Get detailed rate limiter status."""
        remaining = self.get_remaining_requests()
        wait_time = self._get_wait_time()
        post_wait_time = self._get_post_wait_time()

        return {
            "remaining": remaining,
            "wait_time_seconds": wait_time,
            "post_wait_time_seconds": post_wait_time,
            "can_request_now": wait_time == 0,
            "can_post_now": post_wait_time == 0 and wait_time == 0,
        }

    def reset(self) -> None:
        """Reset all rate limit counters (for testing)."""
        self._hourly_timestamps.clear()
        self._daily_timestamps.clear()
        self._post_timestamps.clear()
        self._last_request_time = 0.0


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(config: RateLimitConfig | None = None) -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter

    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config=config or RateLimitConfig())

    return _rate_limiter
