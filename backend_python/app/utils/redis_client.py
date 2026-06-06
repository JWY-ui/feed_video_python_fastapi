"""
Redis 客户端封装——整个项目的 Redis 入口。

设计原则：Redis 是可选的加速层，不是必需的依赖。

  Redis 连接成功 → 缓存/限流/ZSET/锁 全部可用
  Redis 连接失败 → 所有操作返回安全默认值（None/0/False/[]/1）
  业务代码不需要 if-else 判断 Redis 是否可用——调就完了，失败了也不炸

安全默认值的设计：
  - get() 返回 None    → 调用方降级查 MySQL
  - incr() 返回 1      → 限流器放行（不阻塞正常请求）
  - zrevrange() 返回 [] → Feed 流降级查 MySQL
"""
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings


class RedisClient:

    def __init__(self):
        self._redis: Redis | None = None
        self._available: bool = False
        # 简单判断：是否连接过 Redis

    @property
    def available(self) -> bool:
        """外部通过 redis_client.available 判断 Redis 是否可用"""
        return self._available

    async def connect(self):
        """
        连接 Redis，2 秒超时。

        连接失败不抛异常——_available 保持 False。
        业务代码看到 available=False 就走 MySQL 降级路径。
        """
        try:
            self._redis = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                db=settings.redis_db,
                socket_connect_timeout=2,  # 2 秒还连不上就放弃
            )
            await self._redis.ping()
            self._available = True
        except (RedisError, OSError):
            self._available = False
            self._redis = None

    async def close(self):
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._available = False

    # ═══════════════════ String 操作（缓存用）═══════════════════

    async def get(self, key: str) -> str | None:
        """
        GET——取缓存值。

        返回：str（命中）、None（未命中或 Redis 不可用）
        调用方看到 None 就降级查 MySQL。
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
        SET + EXPIRE——写缓存。

        参数：
          key: 缓存键
          value: 缓存值（字符串）
          ex: 过期秒数（默认 1 小时）
          nx=True: 仅当 key 不存在时才 SET（用于分布式锁）

        返回：
          True（写入成功）、False（Redis 不可用 或 nx=True 时 key 已存在）
        """
        if not self._available:
            return False
        try:
            return bool(await self._redis.set(key, value, ex=ex, nx=nx))
        except RedisError:
            return False

    async def delete(self, *keys: str) -> int:
        """DEL——删除一个或多个 key"""
        if not self._available:
            return 0
        try:
            return await self._redis.delete(*keys)
        except RedisError:
            return 0

    # ═══════════════════ 限流用 ═══════════════════

    _INCR_WITH_EXPIRE_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """

    async def incr_with_expire(self, key: str, window_seconds: int) -> int:
        """
        原子 INCR + 条件 EXPIRE——用于限流计数器。

        为什么用 Lua 脚本？
          INCR 和 EXPIRE 是两个独立 Redis 命令，分开发送有竞态窗口——
          INCR 后程序崩溃了，EXPIRE 没发，key 永远不过期。
          Lua 脚本在 Redis 服务端原子执行，消除竞态。

        返回计数。key 不存在时自动创建并返回 1。
        """
        if not self._available:
            return 1  # Redis 不可用 → 返回 1（限流器放行）
        try:
            script = self._redis.register_script(self._INCR_WITH_EXPIRE_SCRIPT)
            return await script(keys=[key], args=[window_seconds])
        except RedisError:
            return 1

    # ═══════════════════ ZSET 操作（Feed 流用）═══════════════════

    async def zcard(self, key: str) -> int:
        """ZCARD——返回 ZSET 成员数"""
        if not self._available:
            return 0
        try:
            return await self._redis.zcard(key)
        except RedisError:
            return 0

    async def zadd(self, key: str, mapping: dict[str, float]):
        """
        ZADD——批量添加成员。

        参数：
          mapping: {"video_id_str": score_float}
          例如：{"101": 1700000000000.0, "102": 1700000001000.0}
        """
        if not self._available:
            return
        try:
            await self._redis.zadd(key, mapping)
        except RedisError:
            pass

    async def zincrby(self, key: str, member: str, amount: float):
        """
        ZINCRBY——原子增减成员的 score。

        用于热度值实时更新：每个互动事件 +1。
        """
        if not self._available:
            return
        try:
            await self._redis.zincrby(key, amount, member)
        except RedisError:
            pass

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        """
        ZREVRANGE——按 score 降序取成员（不包含 score）。

        参数：
          start=0, stop=9 → 取前 10 名（分数最高的）
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
        ZREVRANGEBYSCORE——按 score 范围降序取成员（游标分页）。

        参数：
          max_score: 分数上限（用 "1700000000000" 或 "+inf"）
          min_score: 分数下限（用 "-inf" 表示不限）
          start=0: 跳过前 N 个
          num=10: 最多取几条

        Feed 流游标分页全靠这个命令：
          ZREVRANGEBYSCORE feed:global_timeline <上页最后一条的时间> -inf LIMIT 0 10
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
        ZRANGE WITHSCORES——取成员 + 分数。

        用于获取 ZSET 水位线（最老一条的 score）。
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
        ZUNIONSTORE——合并多个 ZSET 到一个新 key。

        热度榜用：合并最近 60 个分钟窗口 ZSET 生成快照。
        """
        if not self._available:
            return
        try:
            await self._redis.zunionstore(dest, keys, aggregate=aggregate)
        except RedisError:
            pass

    # ═══════════════════ 工具 ═══════════════════

    def key(self, fmt: str, *args) -> str:
        """
        格式化 Redis key。

        用法：
          redis_client.key("account:%d", account_id)    → "account:123"
          redis_client.key("refresh:%s", token)          → "refresh:abc123..."
          redis_client.key("feed:listByFollowing:limit=%d:accountID=%d:before=%d", 10, 5, 0)

        为什么不用 f-string？
          key() 方法可以统一加前缀（如 dev://prod/ 环境隔离）。
        """
        return fmt % args


# 全局单例——整个项目调 redis_client.xxx() 即可
redis_client = RedisClient()
