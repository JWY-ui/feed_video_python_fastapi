"""最新 feed 的两条路径必须给出同一页。

`list_latest` 在 Redis 可用时走「热数据 ZSET + 冷数据 MySQL 拼接」，不可用时整条走
MySQL。这两条路径**必须等价** —— 否则同一份数据在 Redis 起来前后会翻脸。

这个文件此前不存在，而这背后是一段值得记住的历史：本机 Redis 因为 `.env` 里密码
填错，连续一周连不上，所以热路径**一行都没被执行过**，也就没人发现它有三个缺陷
（悬空 id 把首页清空、热冷拼接重复边界视频、`get_by_ids` 不保序）。密码修好的当天
它们一起显形。**把 Redis 接上 = 所有 `if redis_client.available` 分支第一次真的
跑起来**，要预期里面藏着东西。
"""
from __future__ import annotations

import pytest
from factories import _at

from app.database import AsyncSessionLocal
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.services.feed_service import TIMELINE_KEY, FeedService

pytestmark = pytest.mark.usefixtures("redis_client")


@pytest.fixture(autouse=True)
async def _clean_timeline(redis_client):
    """每条测试前后清掉时间线 ZSET。

    直接走底层客户端：`redis_client.delete` 在 available=False 时会静默跳过，
    而这些测试里有几条会临时把 available 置假，清理就漏掉了。
    """

    async def clear():
        await redis_client._redis.delete(TIMELINE_KEY)

    await clear()
    yield
    await clear()


async def _publish(video_id: int, create_time) -> None:
    """走**生产写入路径**把视频放进时间线（发布视频时调的就是它）。"""
    async with AsyncSessionLocal() as session:
        svc = FeedService(FeedRepository(session), LikeRepository(session))
        await svc.add_to_timeline(video_id, create_time)


async def _latest(limit: int = 10, latest_time_ms: int = 0):
    async with AsyncSessionLocal() as session:
        svc = FeedService(FeedRepository(session), LikeRepository(session))
        return await svc.list_latest(limit, latest_time_ms, viewer_id=0)


async def _three_videos(data):
    """造三个视频并发布到时间线，返回 (最旧, 中间, 最新) 的 id。"""
    author = await data.account("作者甲")
    ids = []
    for month, title in ((1, "一月"), (3, "三月"), (6, "六月")):
        video_id = await data.video(author, title, create_time=_at(2024, month, 1))
        await _publish(video_id, _at(2024, month, 1))
        ids.append(video_id)
    return ids


# ── 总闸：两条路径等价 ──────────────────────────────────────────

async def test_the_redis_path_and_the_mysql_path_return_the_same_page(
    data, redis_client, monkeypatch
):
    """同一份数据，Redis 开着和关着必须给同一页。

    这一条是热路径所有缺陷的总闸：不保序、拼接重复、悬空 id 清空首页，任何一种
    都会让两条路径分叉。
    """
    await _three_videos(data)

    redis_page = await _latest(limit=2)
    monkeypatch.setattr(redis_client, "_available", False)
    mysql_page = await _latest(limit=2)
    monkeypatch.undo()  # 让 fixture 的清理能真的删掉 ZSET

    assert [i.title for i in redis_page.video_list] == [
        i.title for i in mysql_page.video_list
    ]


# ── 缺陷 3：结果不保序 ─────────────────────────────────────────

async def test_the_hot_path_is_newest_first(data, redis_client):
    """热路径的结果必须是「最新优先」。

    ZSET 按分数（create_time）降序给 id，但 `get_by_ids` 是一条 `IN` 查询，
    不保证顺序 —— 实测按主键返回，于是整页倒过来。
    """
    await _three_videos(data)

    page = await _latest(limit=10)

    assert [i.title for i in page.video_list] == ["六月", "三月", "一月"]


# ── 缺陷 2：拼接重复边界视频 ───────────────────────────────────

async def test_stitching_cold_data_does_not_repeat_the_boundary_video(data, redis_client):
    """热数据不够 limit 时要拿冷数据补，但绝不能把已经返回过的视频再补一遍。

    根因同上是「顺序」：补数据的游标取自 `hot_videos[-1]`（本应是最旧的那条），
    顺序一乱就取到了最新的那条，于是「比它更早的」把已返回的又捞回来一次。
    """
    author = await data.account("作者甲")
    for month, title in ((1, "一月"), (6, "六月")):
        video_id = await data.video(author, title, create_time=_at(2024, month, 1))
        await _publish(video_id, _at(2024, month, 1))

    page = await _latest(limit=10)  # limit 远大于热数据条数 → 一定走拼接

    titles = [i.title for i in page.video_list]
    assert titles == ["六月", "一月"]
    assert len(titles) == len(set(titles)), f"拼接把边界视频重复了：{titles}"


# ── 缺陷 1：悬空 id 把首页清空 ─────────────────────────────────

async def test_a_dangling_timeline_id_does_not_blank_the_first_page(data, redis_client):
    """时间线里的悬空 id（视频已删）不能让首页整页空白。

    删过视频就会留下这种 id。老实现里热数据查不到行 -> 为空 -> 冷数据兜底用了
    `utc_from_epoch(latest_time_ms / 1000)`，而首页传进来的 latest_time_ms 是 0，
    于是游标变成 **1970 年**，而 repo 的语义是「取该时间之前的」-> 空。
    """
    await _three_videos(data)
    # 一个不存在的视频 id，分数最高 —— 排在最前面
    await redis_client.zadd(TIMELINE_KEY, {"999999999": 9_999_999_999_999})

    page = await _latest(limit=10)

    assert [i.title for i in page.video_list] == ["六月", "三月", "一月"]


# ── 分页游标 ───────────────────────────────────────────────────

async def test_paging_does_not_repeat_the_last_video_of_the_previous_page(
    data, redis_client
):
    """翻页不能把上一页最后一条又给一遍 —— 游标是开区间的。"""
    await _three_videos(data)

    first = await _latest(limit=2)
    assert [i.title for i in first.video_list] == ["六月", "三月"]
    assert first.has_more is True
    assert first.next_time > 0

    second = await _latest(limit=2, latest_time_ms=first.next_time)

    assert [i.title for i in second.video_list] == ["一月"]


# ── 降级路径 ───────────────────────────────────────────────────

async def test_the_mysql_path_is_newest_first_when_redis_is_down(
    data, redis_client, monkeypatch
):
    """Redis 不可用时整条走 MySQL，同样要「最新优先」。"""
    await _three_videos(data)
    monkeypatch.setattr(redis_client, "_available", False)

    page = await _latest(limit=10)

    assert [i.title for i in page.video_list] == ["六月", "三月", "一月"]


async def test_an_empty_database_gives_an_empty_page(data, redis_client):
    """空库就是空页，不报错。"""
    page = await _latest(limit=10)

    assert page.video_list == []
    assert page.has_more is False
