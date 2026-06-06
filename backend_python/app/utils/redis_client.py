# -*- coding: utf-8 -*-
"""
Redis client wrapper -- the single Redis entry point for the entire project.

Design principle: Redis is an optional acceleration layer, not a hard dependency.

  Redis connected     -> cache/rate-limit/ZSET/locks all available
  Redis unreachable   -> all operations return safe defaults (None/0/False/[]/1)
  Business code doesn't need if-else checks -- just call, won't explode on failure.

Safe defaults:
  - get() returns None     -> caller degrades to MySQL
  - incr() returns 1       -> rate limiter passes (doesn't block real requests)
  - zrevrange() returns [] -> feed degrades to MySQL
"""
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings


class RedisClient:

    def __init__(self):
        self._redis: Redis | None = None
        self._available: bool = False

    @property
    def available(self) -> bool:
        """External code checks redis_client.available to know if Redis is up."""
        return self._available

    async def connect(self):
        """
        Connect to Redis, 2-second timeout.

        Connection failure does NOT raise -- _available stays False.
        Business code sees available=False and takes MySQL degradation path.
        """
        try:
            self._redis = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                db=settings.redis_db,
                socket_connect_timeout=2,  # give up if not connected within 2 seconds
            )
            await self._redis.ping()
            self._available = True
        except (RedisError, OSError):
            self._available = False
            self._redis = None

    async def close(self):
        """Close connection."""
        if self._redis:
            await self._redis.close()
            self._available = False

    # ==================== String operations (caching) ====================

    async def get(self, key: str) -> str | None:
        """
        GET -- retrieve cached value.

        Returns: str (hit), None (miss or Redis unavailable).
        Caller sees None and degrades to MySQL.
        """
        if not self._available:
            return None
        try:
            val = await self._redis.get(key)
            return val.decode() if val else None
        except RedisError:
            return None

    async def set(self, key: str, value: str, ex: int = 3600, nx: bool = False) -> bool:
        """
        SET + EXPIRE -- write cache.

        Args:
          key: cache key
          value: cache value (string)
          ex: expiry seconds (default 1 hour)
          nx=True: only SET if key does NOT exist (used for distributed locks)

        Returns:
          True (write succeeded), False (Redis unavailable or nx=True and key already exists)
        """
        if not self._available:
            return False
        try:
            return bool(await self._redis.set(key, value, ex=ex, nx=nx))
        except RedisError:
            return False

    async def delete(self, *keys: str) -> int:
        """DEL -- delete one or more keys."""
        if not self._available:
            return 0
        try:
            return await self._redis.delete(*keys)
        except RedisError:
            return 0

    # ==================== Rate limiting ====================

    _INCR_WITH_EXPIRE_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """

    async def incr_with_expire(self, key: str, window_seconds: int) -> int:
        """
        Atomic INCR + conditional EXPIRE -- for rate limiter counter.

        Why Lua script?
          INCR and EXPIRE are two separate Redis commands. Sending them separately
          has a race window: INCR succeeds, process crashes, EXPIRE never sent,
          key lives forever. Lua script runs atomically on Redis server, no race.

        Returns count. Non-existent key is auto-created, returns 1.
        """
        if not self._available:
            return 1  # Redis unavailable -> return 1 (rate limiter allows)
        try:
            script = self._redis.register_script(self._INCR_WITH_EXPIRE_SCRIPT)
            return await script(keys=[key], args=[window_seconds])
        except RedisError:
            return 1

    # ==================== ZSET operations (Feed) ====================

    async def zcard(self, key: str) -> int:
        """ZCARD -- return number of ZSET members."""
        if not self._available:
            return 0
        try:
            return await self._redis.zcard(key)
        except RedisError:
            return 0

    async def zadd(self, key: str, mapping: dict[str, float]):
        """
        ZADD -- batch-add members.

        Args:
          mapping: {"video_id_str": score_float}
          e.g. {"101": 1700000000000.0, "102": 1700000001000.0}
        """
        if not self._available:
            return
        try:
            await self._redis.zadd(key, mapping)
        except RedisError:
            pass

    async def zincrby(self, key: str, member: str, amount: float):
        """
        ZINCRBY -- atomically increment/decrement member score.

        Used for real-time popularity updates: +1 per interaction event.
        """
        if not self._available:
            return
        try:
            await self._redis.zincrby(key, amount, member)
        except RedisError:
            pass

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        """
        ZREVRANGE -- get members by score descending (scores not included).

        Args:
          start=0, stop=9 -> get top 10 (highest scores).
        """
        if not self._available:
            return []
        try:
            result = await self._redis.zrevrange(key, start, stop)
            return [r.decode() if isinstance(r, bytes) else r for r in result]
        except RedisError:
            return []

    async def zrevrangebyscore(self, key: str, max_score: str,
                                min_score: str, start: int, num: int) -> list[str]:
        """
        ZREVRANGEBYSCORE -- get members by score range, descending (cursor pagination).

        Args:
          max_score: upper score bound (use "1700000000000" or "+inf")
          min_score: lower score bound (use "-inf" for unlimited)
          start=0: skip first N
          num=10: max results

        Feed cursor pagination relies on this command:
          ZREVRANGEBYSCORE feed:global_timeline <prev_page_last_time> -inf LIMIT 0 10
        """
        if not self._available:
            return []
        try:
            result = await self._redis.zrevrangebyscore(
                key, max_score, min_score, start=start, num=num,
            )
            return [r.decode() if isinstance(r, bytes) else r for r in result]
        except RedisError:
            return []

    async def zrange_with_scores(self, key: str, start: int, stop: int) -> list[tuple[str, float]]:
        """
        ZRANGE WITHSCORES -- get members + scores.

        Used to get ZSET watermark (score of oldest entry).
        """
        if not self._available:
            return []
        try:
            result = await self._redis.zrange(key, start, stop, withscores=True)
            return [
                (r[0].decode() if isinstance(r[0], bytes) else r[0], r[1])
                for r in result
            ]
        except RedisError:
            return []

    async def zunionstore(self, dest: str, keys: list[str], aggregate: str = "SUM"):
        """
        ZUNIONSTORE -- merge multiple ZSETs into one dest key.

        Hot ranking uses this: merge last 60 minute-window ZSETs into a snapshot.
        """
        if not self._available:
            return
        try:
            await self._redis.zunionstore(dest, keys, aggregate=aggregate)
        except RedisError:
            pass

    async def eval_script(self, lua_code: str, keys: list[str], args: list) -> int | None:
        """
        Execute a Lua script on the Redis server atomically.

        Returns the script's return value, or None if Redis is unavailable.
        """
        if not self._available:
            return None
        try:
            script = self._redis.register_script(lua_code)
            return await script(keys=keys, args=args)
        except RedisError:
            return None

    async def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        """
        ZREMRANGEBYRANK -- remove members by rank range.

        Used to trim ZSET timeline to keep only the latest N entries.
        """
        if not self._available:
            return 0
        try:
            return await self._redis.zremrangebyrank(key, start, stop)
        except RedisError:
            return 0

    # ==================== Utility ====================

    def key(self, fmt: str, *args) -> str:
        """
        Format Redis key.

        Usage:
          redis_client.key("account:%d", account_id)    -> "account:123"
          redis_client.key("refresh:%s", token)          -> "refresh:abc123..."
          redis_client.key("feed:listByFollowing:limit=%d:accountID=%d:before=%d", 10, 5, 0)

        Why not f-string?
          key() method can add prefix for environment isolation (e.g. dev://prod/).
        """
        return fmt % args


# Global singleton -- the entire project calls redis_client.xxx()
redis_client = RedisClient()
