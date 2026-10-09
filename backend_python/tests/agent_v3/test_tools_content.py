"""内容互动工具：看评论、看自己赞过的、点赞/取消，以及发评论（必须确认）。"""
from __future__ import annotations

from stubs import call_tool


async def test_list_comments_returns_them(data):
    author = await data.account("作者")
    video_id = await data.video(author, "视频")
    await data.comment(video_id, author, "第一条", username="甲")

    result = await call_tool("list_comments", video_id=video_id)

    assert [c["content"] for c in result.data] == ["第一条"]
    assert result.data[0]["author"] == "甲"


async def test_list_comments_of_a_missing_video_reports_rather_than_raises(data):
    result = await call_tool("list_comments", video_id=999999)

    assert result.data is None
    assert "不存在" in result.summary


async def test_my_liked_videos_are_only_mine(data):
    me = await data.account("我")
    other = await data.account("别人")
    mine = await data.video(me, "我赞的")
    theirs = await data.video(me, "别人赞的")
    await data.like(mine, me)
    await data.like(theirs, other)

    result = await call_tool("list_my_liked_videos", account_id=me)

    assert [v["id"] for v in result.data] == [mine]


async def test_unlike_removes_the_like(data):
    me = await data.account("我")
    video_id = await data.video(me, "视频")
    await data.like(video_id, me)

    result = await call_tool("unlike_video", account_id=me, video_id=video_id)

    assert "取消" in result.summary
    assert (await call_tool("list_my_liked_videos", account_id=me)).data == []


async def test_publish_comment_creates_it(data):
    me = await data.account("我")
    author = await data.account("作者")
    video_id = await data.video(author, "视频")

    result = await call_tool(
        "publish_comment", account_id=me, username="我",
        video_id=video_id, content="写得好",
    )

    assert "评论" in result.summary
    comments = await call_tool("list_comments", video_id=video_id)
    assert [c["content"] for c in comments.data] == ["写得好"]


async def test_publishing_on_a_missing_video_reports_rather_than_raises(data):
    me = await data.account("我")

    result = await call_tool(
        "publish_comment", account_id=me, username="我",
        video_id=999999, content="喂？",
    )

    assert "失败" in result.summary
