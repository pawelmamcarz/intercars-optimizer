"""
rate_limit_backend.py — pluggable storage for rate limiting.

Current production runs a single Railway replica, so the in-memory
store in main.py is correct and fast. When we scale horizontally the
memory store will under-count per-IP across replicas; this module
carries the Redis-backed implementation that plugs in without touching
the middleware.

Usage (when horizontally scaled):
    os.environ["FLOW_RATE_LIMIT_BACKEND"] = "redis"
    os.environ["FLOW_REDIS_URL"] = "redis://..."
    # middleware auto-detects and uses the Redis backend
"""
from __future__ import annotations

import logging
import os
import time
from typing import Protocol

log = logging.getLogger(__name__)


class RateLimitBackend(Protocol):
    """Contract every backend implements. `allow` returns True when the
    caller may proceed, False to 429."""
    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool: ...


class MemoryBackend:
    """Single-replica sliding window. Identical behaviour to the
    middleware's in-process _RateLimitStore — kept here so callers can
    swap backends via a single import."""
    def __init__(self):
        self.hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        hits = [h for h in self.hits.get(key, []) if now - h < window_s]
        if len(hits) >= limit:
            self.hits[key] = hits
            return False
        hits.append(now)
        self.hits[key] = hits
        return True


class RedisBackend:
    """Distributed sliding window via Redis sorted sets. Works across N
    replicas — use when `FLOW_RATE_LIMIT_BACKEND=redis`.

    Requires `redis>=5` installed and `FLOW_REDIS_URL` set. Falls back
    to MemoryBackend if the Redis connection fails at init — logs a
    warning so ops notice."""
    def __init__(self, url: str):
        try:
            import redis as _redis
        except ImportError as exc:
            raise RuntimeError("redis package required for Redis backend") from exc
        self.client = _redis.Redis.from_url(url, decode_responses=True)
        # Sanity check connection eagerly — we want the error at boot,
        # not on the first throttled request.
        self.client.ping()

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - window_s
        pipe = self.client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, int(window_s) + 1)
        _, count, _, _ = pipe.execute()
        # count is the pre-add size; +1 the current request
        return count < limit


def build_backend() -> RateLimitBackend:
    """Pick a backend based on env vars. Falls back to MemoryBackend
    when Redis isn't configured or fails to connect."""
    choice = os.environ.get("FLOW_RATE_LIMIT_BACKEND", "memory").lower()
    if choice == "redis":
        url = os.environ.get("FLOW_REDIS_URL", "")
        if not url:
            log.warning("FLOW_RATE_LIMIT_BACKEND=redis but FLOW_REDIS_URL missing; "
                        "falling back to memory")
            return MemoryBackend()
        try:
            return RedisBackend(url)
        except Exception as exc:
            log.error("Redis rate-limit backend failed (%s) — using memory", exc)
            return MemoryBackend()
    return MemoryBackend()
