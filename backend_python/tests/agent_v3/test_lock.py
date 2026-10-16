"""跨进程的会话锁。

这一组全都要真 Redis —— 锁本身就在 Redis 里（见 app/agent_v3/lock.py）。用假
Redis 测一把分布式锁，测到的是假 Redis 的行为，不是分布式的行为。
"""
from __future__ import annotations

import asyncio

import pytest

from app.agent_v3.lock import LockTimeout, LockUnavailable, lock_key, thread_lock
from app.config import settings

T1 = "lock-test-t1"
T2 = "lock-test-t2"


async def _enter(thread_id: str, log: list[str], tag: str) -> None:
    async with thread_lock(thread_id):
        log.append(tag)


@pytest.fixture(autouse=True)
async def _clear_locks(redis_client):
    """每条测试前后清掉可能残留的锁键。"""
    await redis_client.delete(lock_key(T1), lock_key(T2))
    yield
    await redis_client.delete(lock_key(T1), lock_key(T2))


async def test_a_second_run_on_the_same_thread_waits_for_the_first(redis_client):
    """同一个 thread 上第二个运行必须等第一个放锁 —— 这是整个模块存在的理由。"""
    log: list[str] = []

    async with thread_lock(T1):
        task = asyncio.create_task(_enter(T1, log, "second"))
        await asyncio.sleep(0.3)
        assert log == [], "第一个还没放锁，第二个不能进来"
        log.append("first")

    await asyncio.wait_for(task, timeout=5)
    assert log == ["first", "second"]


async def test_different_threads_do_not_block_each_other(redis_client):
    """锁是按 thread_id 分的，不同会话互不相干。"""
    log: list[str] = []

    async with thread_lock(T1):
        await asyncio.wait_for(_enter(T2, log, "other"), timeout=5)

    assert log == ["other"]


async def test_a_stale_release_does_not_drop_the_current_owner(redis_client, monkeypatch):
    """锁因 TTL 过期被下一个人接手后，上一个持有者退出时绝不能把它删掉。

    删了就等于两个人同时持锁 —— 正是这次要防的那个静默损坏。所以释放必须
    先比对 token：还是我的，才删（Lua compare-and-delete）。
    """
    monkeypatch.setattr(settings, "agent_lock_ttl_seconds", 1)

    async with thread_lock(T1):
        await asyncio.sleep(1.5)  # 让手里这把过期
        # 模拟「下一个人已经拿到锁」
        await redis_client.set(lock_key(T1), "someone-else", ex=30)

    assert await redis_client.get(lock_key(T1)) == "someone-else", (
        "过期的持有者释放时把别人手里的锁删了"
    )


async def test_the_lock_carries_a_ttl(redis_client):
    """锁必须自带 TTL。

    没有 TTL 的话，进程崩溃、或被 kill 的 worker 会把这把锁永远留在 Redis 里 ——
    那个会话从此再也打不开。这比原来进程内的锁更糟（进程内的锁至少跟着进程一起死）。
    """
    async with thread_lock(T1):
        ttl = await redis_client._redis.ttl(lock_key(T1))

    assert 0 < ttl <= settings.agent_lock_ttl_seconds


async def test_redis_being_down_is_refused_loudly(redis_client, monkeypatch):
    """Redis 不可用时直接抛错，绝不退回「无锁照跑」。

    无锁照跑的后果是消息被静默丢弃、checkpointer 主键冲突、私信发两条 —— 都是
    用户可见且无法撤回的损坏。宁可明确不可用。
    """
    monkeypatch.setattr(redis_client, "_available", False)

    with pytest.raises(LockUnavailable):
        async with thread_lock(T1):
            pass


async def test_waiting_too_long_gives_up_with_a_clear_error(redis_client, monkeypatch):
    """等锁超时要报错退出，不能无限轮询下去把请求挂死。"""
    monkeypatch.setattr(settings, "agent_lock_wait_seconds", 1)

    async with thread_lock(T1):
        with pytest.raises(LockTimeout):
            async with thread_lock(T1):
                pass
