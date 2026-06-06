"""
接口限流中间件——滑动窗口计数器

用 Redis Lua 脚本实现基于 ZSET 的滑动窗口限流，
同时解决两个问题：
  1. INCR + EXPIRE 的竞态窗口（之前已修）
  2. 固定窗口边界 2x 突发（本次修复）

滑动窗口原理：
  每请求 = ZADD key now now（score=member=now）
  检查时 = ZCOUNT key (now - window, +inf)
  清理过期 = ZREMRANGEBYSCORE key 0 (now - window)

  窗口是"最近 N 秒"，不是"第 N 分钟"。
  没有固定边界，突发最多 1x 限制。
"""
from fastapi import HTTPException, Request, status
from app.utils.redis_client import redis_client


# Lua：先清理过期 → 计数 → 判断 → 超限则回滚
_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])

-- 1. 清理窗口外的旧记录
redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)

-- 2. 统计当前窗口内的请求数
local count = redis.call('ZCARD', key)

-- 3. 超限则拒绝
if count >= max_requests then
    return 0
end

-- 4. 记录本次请求（score 用毫秒时间戳，member 用 score+随机后缀保证唯一）
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
            return  # Redis 中途挂了，跳过限流

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many requests",
            )


def rate_limit(prefix: str, max_requests: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(prefix, max_requests, window_seconds)
