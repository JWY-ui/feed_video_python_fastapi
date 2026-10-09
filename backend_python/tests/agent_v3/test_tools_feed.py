"""feed 域工具：全是只读，直接执行。

这些工具复用 FeedService / VideoService，不自己写 SQL —— 所以测试造真实数据、
断言真实返回。顺带守住「投影里不带 play_url / cover_url」这条：一次列表几十条
长 URL 白烧 token，而且模型根本用不上。
"""
from __future__ import annotations

from factories import _at
from stubs import call_tool

LONG_FIELDS = ("play_url", "cover_url")


async def test_latest_is_newest_first(data):
    author = await data.account("作者甲")
    await data.video(author, "旧视频", create_time=_at(2024, 1, 1))
    await data.video(author, "新视频", create_time=_at(2024, 6, 1))

    result = await call_tool("list_latest_videos", account_id=author, limit=10)

    assert [v["title"] for v in result.data] == ["新视频", "旧视频"]
    assert result.summary == "找到 2 个视频"


async def test_hot_is_ranked_by_likes(data):
    author = await data.account("作者甲")
    await data.video(author, "冷门", likes_count=1)
    await data.video(author, "爆款", likes_count=99)

    result = await call_tool("list_hot_videos", account_id=author, limit=10)

    assert [v["title"] for v in result.data] == ["爆款", "冷门"]


async def test_following_only_returns_followed_authors(data):
    me = await data.account("我")
    friend = await data.account("朋友")
    stranger = await data.account("陌生人")
    await data.video(friend, "朋友发的")
    await data.video(stranger, "陌生人发的")
    await data.follow(me, friend)

    result = await call_tool("list_following_videos", account_id=me, limit=10)

    assert [v["title"] for v in result.data] == ["朋友发的"]


async def test_by_tag_only_returns_tagged_videos(data):
    author = await data.account("作者甲")
    await data.video(author, "做菜视频", tags=("美食",))
    await data.video(author, "旅行视频", tags=("旅行",))

    result = await call_tool("list_by_tag", account_id=author, tag="美食")

    assert [v["title"] for v in result.data] == ["做菜视频"]


async def test_detail_returns_description(data):
    author = await data.account("作者甲")
    video_id = await data.video(author, "做菜视频", description="三分钟学会")

    result = await call_tool("get_video_detail", account_id=author, video_id=video_id)

    assert result.data["title"] == "做菜视频"
    assert result.data["description"] == "三分钟学会"


async def test_detail_of_a_missing_video_reports_rather_than_raises(data):
    """模型拿不准 id 是常事，不该整轮对话塌掉。"""
    author = await data.account("作者甲")

    result = await call_tool("get_video_detail", account_id=author, video_id=999999)

    assert result.data is None
    assert "不存在" in result.summary


async def test_every_projection_drops_the_long_url_fields(data):
    author = await data.account("作者甲")
    await data.video(author, "做菜视频", tags=("美食",))

    for tool, kwargs in [
        ("list_latest_videos", {}),
        ("list_hot_videos", {}),
        ("list_by_tag", {"tag": "美食"}),
    ]:
        result = await call_tool(tool, account_id=author, limit=10, **kwargs)
        for item in result.data:
            for field in LONG_FIELDS:
                assert field not in item, f"{tool} 的投影里不该有 {field}"


async def test_liked_by_me_reflects_the_viewer(data):
    author = await data.account("作者甲")
    viewer = await data.account("我")
    video_id = await data.video(author, "做菜视频")
    await data.like(video_id, viewer)

    result = await call_tool("list_latest_videos", account_id=viewer, limit=10)

    assert result.data[0]["liked_by_me"] is True
