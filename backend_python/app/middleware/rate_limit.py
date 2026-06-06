# -*- coding: utf-8 -*-
"""
API rate limiting middleware -- sliding window counter.

Uses Redis Lua script for ZSET-based sliding window rate limiting.
Solves two problems simultaneously:
  1. INCR + EXPIRE race window (previously fixed)
  2. Fixed window boundary 2x burst (this fix)

Sliding window principle:
  Per request = ZADD key now now (score=member=now)
  Check = ZCOUNT key (now - window, +inf)
  Cleanup = ZREMRANGEBYSCORE key 0 (now - window)

  Window is "last N seconds", not "the Nth minute".
  No fixed boundary, burst capped at 1x limit.
"""
from fastapi import HTTPException, Request, status
from app.utils.redis_client import redis_client


# Lua: cleanup expired -> count -> check -> rollback if over limit
_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])

-- 1. Remove records outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)

-- 2. Count requests within current window
local count = redis.call('ZCARD', key)

-- 3. Reject if over limit
if count >= max_requests then
    return 0
end

-- 4. Record this request (score = ms timestamp, member = score + random suffix for uniqueness)
redis.call('ZADD', key, now, now .. ':' .. count)
redis.call('EXPIRE', key, window * 2)
return 1
"""


class RateLimiter:

    def __init__(self, prefix: str, max_requests: int, window_seconds: int):
        self.prefix = prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request):
        if not redis_client.available:
            return

        import time
        subject = request.client.host if request.client else "unknown"
        key = f"feedsystem:ratelimit:{self.prefix}:{subject}"
        now_ms = int(time.time() * 1000)

        if not redis_client._available:
            return

        try:
            script = redis_client._redis.register_script(_SLIDING_WINDOW_SCRIPT)
            allowed = await script(
                keys=[key],
                args=[now_ms, self.window_seconds, self.max_requests],
            )
        except Exception:
            return  # Redis died mid-flight, skip rate limiting

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many requests",
            )


def rate_limit(prefix: str, max_requests: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(prefix, max_requests, window_seconds)
