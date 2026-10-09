"""social 域工具：搜人、看关注关系，以及关注/取关（可逆写，直接执行）。

`search_user` 是这次新放宽的能力 —— 原来是精确匹配，模型的「关注小明」在用户名
是「小明123」时会直接失败。它同时是个投影测试点：account 的 dict 里有 password
和 token，绝不能整条丢给模型。
"""
from __future__ import annotations

from stubs import call_tool


async def test_search_user_finds_partial_names(data):
    fan_id = await data.account("小明123")
    await data.account("小红")

    result = await call_tool("search_user", query="小明")

    assert result.data == [{"id": fan_id, "username": "小明123"}]


async def test_search_user_never_leaks_credentials(data):
    await data.account("小明")

    result = await call_tool("search_user", query="小明")

    assert set(result.data[0]) == {"id", "username"}


async def test_search_user_without_a_match_says_so(data):
    await data.account("小明")

    result = await call_tool("search_user", query="查无此人")

    assert result.data == []
    assert "没找到" in result.summary


async def test_following_lists_who_i_follow(data):
    me = await data.account("我")
    friend = await data.account("朋友")
    await data.follow(me, friend)

    result = await call_tool("get_following", account_id=me)

    assert result.data == [{"id": friend, "username": "朋友"}]


async def test_followers_lists_who_follows_me(data):
    me = await data.account("我")
    fan = await data.account("粉丝")
    await data.follow(fan, me)

    result = await call_tool("get_followers", account_id=me)

    assert result.data == [{"id": fan, "username": "粉丝"}]


async def test_follow_user_creates_the_relation(data):
    me = await data.account("我")
    other = await data.account("别人")

    result = await call_tool("follow_user", account_id=me, vlogger_id=other)

    assert "关注" in result.summary
    following = await call_tool("get_following", account_id=me)
    assert [u["id"] for u in following.data] == [other]


async def test_unfollow_user_removes_the_relation(data):
    me = await data.account("我")
    other = await data.account("别人")
    await call_tool("follow_user", account_id=me, vlogger_id=other)

    await call_tool("unfollow_user", account_id=me, vlogger_id=other)

    following = await call_tool("get_following", account_id=me)
    assert following.data == []


async def test_following_yourself_does_not_create_a_relation(data):
    me = await data.account("我")

    await call_tool("follow_user", account_id=me, vlogger_id=me)

    assert (await call_tool("get_following", account_id=me)).data == []
