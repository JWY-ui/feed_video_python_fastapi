"""账号域工具：看自己的资料、看通知。"""
from __future__ import annotations

from stubs import call_tool


async def test_profile_never_leaks_credentials(data):
    """account 的 dict 里带 password 和 token，整条丢给模型就是把凭据递出去了。"""
    me = await data.account("我")

    result = await call_tool("get_my_profile", account_id=me)

    assert result.data["username"] == "我"
    assert not ({"password", "token", "refresh_token"} & set(result.data))


async def test_notifications_are_listed(data):
    me = await data.account("我")
    other = await data.account("别人")
    await data.notification(me, other, "like", content="赞了你的视频")

    result = await call_tool("list_notifications", account_id=me)

    assert [n["type"] for n in result.data] == ["like"]
    assert result.data[0]["content"] == "赞了你的视频"
