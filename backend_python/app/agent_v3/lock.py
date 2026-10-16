"""按 thread_id 串行化图运行 —— 一把**跨进程**的锁。

**为什么必须跨进程。** 同一个 thread_id 上两个图运行同时读写同一份 checkpoint，
实测后果有三样，全是用户可见且撤不回的：其中一轮的消息被静默丢掉、checkpointer
报主键冲突、写操作被执行两遍（同一条私信发两条）。进程内的 `asyncio.Lock` 只挡得住
同一个 worker 里的并发 —— 换到第二个 worker 照旧。所以锁放在 Redis 里。

**Redis 不可用时直接拒绝，不退回无锁。** 没有跨进程串行化就谈不上正确性，宁可明确
报错，也不回到那条会静默损坏数据的路径。这和 checkpointer 是硬依赖是同一个判断；
但与 Redis 缓存/限流的「不可用就降级」哲学相反 —— 那两处的降级只是变慢或失去保护，
这里的降级是**损坏数据**。

**Redis 里一把锁的三个部件，缺一不可：**

* `TTL` —— 进程崩溃或被 kill 后锁会自己过期。没有它，那个会话从此再也打不开，
  比原来的进程内锁更糟（进程内的锁至少跟着进程一起死）。
* `token + compare-and-delete` —— 释放前先确认锁还是自己的。慢请求的锁过期后被别人
  接手，它退出时若直接 DEL，就把别人的锁删了，于是两个人同时跑 —— 正是要防的那件事。
* `等待轮询 + 超时` —— 同会话并发两轮要排队而不是报错；但等待必须有上限，
  否则一个卡住的运行会把后续请求无限堆积。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import settings
from app.utils.redis_client import redis_client

_KEY_PREFIX = "feedsystem:agent_v3:lock"

# 抢锁的轮询间隔。只在**有争用**时才会走到 sleep 上，无争用时第一次 SET NX 就拿到。
_POLL_INTERVAL = 0.05

# 只在「锁还是我的」时才删 —— 见模块 docstring 里 token 那一条。
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class LockUnavailable(RuntimeError):
    """锁的后端（Redis）不可用。调用方应把它当成「agent 暂时不可用」。"""


class LockTimeout(RuntimeError):
    """等别的运行放锁等超时了。"""


def lock_key(thread_id: str) -> str:
    """锁在 Redis 里的键。导出它，测试和排查都按同一个约定走。"""
    return f"{_KEY_PREFIX}:{thread_id}"


async def _acquire(key: str, token: str) -> None:
    """拿到锁才返回；拿不到就轮询到超时。

    先查 `available` 而不是直接轮询：Redis 整个不可用时要**立刻**抛错，而不是
    空转 agent_lock_wait_seconds 秒再报一个看起来像「锁被占用」的错。
    """
    if not redis_client.available:
        raise LockUnavailable("Redis 不可用，无法保证同一个会话串行执行")

    deadline = time.monotonic() + settings.agent_lock_wait_seconds
    while True:
        if await redis_client.set(
            key, token, ex=settings.agent_lock_ttl_seconds, nx=True
        ):
            return
        if not redis_client.available:
            raise LockUnavailable("等锁期间 Redis 掉线了")
        if time.monotonic() >= deadline:
            raise LockTimeout(
                f"等锁超过 {settings.agent_lock_wait_seconds} 秒，上一个运行可能卡住了"
            )
        await asyncio.sleep(_POLL_INTERVAL)


async def _release(key: str, token: str) -> None:
    """放锁。锁已经不在了、或已经不属于自己了，都不该报错。"""
    await redis_client.eval_script(_RELEASE_SCRIPT, keys=[key], args=[token])


@asynccontextmanager
async def thread_lock(thread_id: str) -> AsyncIterator[None]:
    """进入即持有这个 thread 的锁，退出（含异常、含生成器被关闭）即释放。"""
    key = lock_key(thread_id)
    token = uuid.uuid4().hex

    await _acquire(key, token)
    try:
        yield
    finally:
        await _release(key, token)
