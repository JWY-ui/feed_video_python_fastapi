"""私信工具：读会话（发私信那条是 write_public，见 test_service_stream）。"""
from __future__ import annotations

from stubs import call_tool


async def test_list_messages_covers_both_directions(data):
    me = await data.account("我")
    peer = await data.account("对方")
    await data.message(peer, me, "你好")
    await data.message(me, peer, "在的")

    result = await call_tool("list_messages", account_id=me, peer_id=peer)

    assert sorted(m["content"] for m in result.data) == ["你好", "在的"]


async def test_list_messages_excludes_other_people(data):
    me = await data.account("我")
    peer = await data.account("对方")
    stranger = await data.account("第三者")
    await data.message(stranger, me, "无关的")

    result = await call_tool("list_messages", account_id=me, peer_id=peer)

    assert result.data == []
