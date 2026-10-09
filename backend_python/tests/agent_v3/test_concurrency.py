"""并发下的正确性 —— 同一个会话被两个请求同时碰的时候。

探针实测出的两个真问题，都源于同一件事：同一个 thread_id 上没有任何串行化，
两个图运行同时读写同一份 checkpoint。

  * 两次并发「确认」→ 写操作执行两遍（私信会发两条）
  * 同一会话并发两轮对话 → 其中一轮的消息被静默丢掉，checkpointer 还报主键冲突

这两条都不是"压力大才出现"的边缘情况：用户双击发送、两个标签页、前端重试都会碰到。
"""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage

from app.agent_v3.graph import build_graph
from app.agent_v3.service import AgentV3Service
from stubs import EXECUTED, StubChatModel, wants

ACCOUNT = 960002
USERNAME = "我"


def _service(script: list[AIMessage], checkpointer) -> AgentV3Service:
    return AgentV3Service(
        build_graph(llm=StubChatModel(script), checkpointer=checkpointer)
    )


async def _drain(stream) -> list[dict]:
    return [event async for event in stream]


@pytest.fixture
async def thread(checkpointer):
    """一个已建好的会话 id，用完删掉。"""
    svc = _service([AIMessage(content="好")], checkpointer)
    conv = await svc.create_conversation(ACCOUNT)
    yield conv["thread_id"]
    await svc.delete_conversation(ACCOUNT, conv["thread_id"])


async def test_concurrent_confirmations_execute_the_write_only_once(
    checkpointer, stub_tools, thread
):
    """两次「确认」同时到达，写操作只能执行一次。

    否则一个确认卡被点两下（或前端重试）就会把同一条私信发两遍 —— 这是用户可见、
    且无法撤回的损坏。
    """
    service = _service(
        [wants("t_write"), AIMessage(content="完成"), AIMessage(content="完成")],
        checkpointer,
    )
    await _drain(service.chat_stream(ACCOUNT, USERNAME, "写一条", thread))
    assert EXECUTED == [], "确认之前不该执行"

    await asyncio.gather(
        _drain(service.confirm(ACCOUNT, thread, approved=True)),
        _drain(service.confirm(ACCOUNT, thread, approved=True)),
    )

    assert EXECUTED.count(("write", 1)) == 1


async def test_concurrent_turns_on_one_thread_lose_neither_message(
    checkpointer, stub_tools, thread
):
    """同一个会话同时发两轮，两条用户消息都必须留下。"""
    service = _service(
        [
            wants("t_read"), AIMessage(content="好1"),
            wants("t_read"), AIMessage(content="好2"),
        ],
        checkpointer,
    )

    await asyncio.gather(
        _drain(service.chat_stream(ACCOUNT, USERNAME, "甲", thread)),
        _drain(service.chat_stream(ACCOUNT, USERNAME, "乙", thread)),
    )

    history = await service.get_history(ACCOUNT, thread)
    said = sorted(m["content"] for m in history if m["role"] == "user")
    assert said == ["乙", "甲"], "两轮都在，一条都不能少"


async def test_a_new_message_is_refused_while_a_confirmation_is_pending(
    checkpointer, stub_tools, thread
):
    """确认卡还开着时不能再开新一轮。

    实测后果：新一轮会**静默销毁**那个待确认的操作 —— 用户之后再点「发送」，
    写操作一次都不会执行，而且没有任何报错。宁可明确拒绝。
    """
    service = _service(
        [wants("t_write"), AIMessage(content="完成"), AIMessage(content="在的")],
        checkpointer,
    )
    first = await _drain(service.chat_stream(ACCOUNT, USERNAME, "写一条", thread))
    assert any(e["event"] == "confirm_required" for e in first)

    second = await _drain(service.chat_stream(ACCOUNT, USERNAME, "在吗", thread))

    assert any(e["event"] == "error" for e in second), "待确认时不该接受新一轮"
    # 而且原来那次确认必须还是有效的
    await _drain(service.confirm(ACCOUNT, thread, approved=True))
    assert EXECUTED.count(("write", 1)) == 1, "被拒绝的新消息不该动到待确认的操作"


async def test_abandoning_a_stream_does_not_wedge_the_thread(
    checkpointer, stub_tools, thread
):
    """客户端中途断开后，这个会话必须还能用。

    锁是在异步生成器内部持有的（图跑到一半时锁必须还在），所以一旦生成器没被正确
    关闭，锁就永远不释放 —— 那个会话从此再也打不开。router 里的 `_stream` 在检测到
    断开时会 break，从而关闭生成器；这条测试确认那条路径真的把锁放掉了。
    """
    service = _service(
        [wants("t_read"), AIMessage(content="好1"), wants("t_read"), AIMessage(content="好2")],
        checkpointer,
    )

    stream = service.chat_stream(ACCOUNT, USERNAME, "甲", thread)
    await anext(stream)          # 只取一个事件就撒手
    await stream.aclose()        # 等价于 router 检测到断开后关闭生成器

    later = await asyncio.wait_for(
        _drain(service.chat_stream(ACCOUNT, USERNAME, "乙", thread)), timeout=10
    )
    assert any(e["event"] == "done" for e in later), "断开一次之后这个会话就废了"


async def test_concurrent_turns_do_not_corrupt_the_checkpoint(
    checkpointer, stub_tools, thread
):
    """并发跑完，transcript 必须还是成对的（每个 tool_call 都有对应结果）。"""
    service = _service(
        [
            wants("t_read"), AIMessage(content="好1"),
            wants("t_read"), AIMessage(content="好2"),
        ],
        checkpointer,
    )

    await asyncio.gather(
        _drain(service.chat_stream(ACCOUNT, USERNAME, "甲", thread)),
        _drain(service.chat_stream(ACCOUNT, USERNAME, "乙", thread)),
    )

    history = await service.get_history(ACCOUNT, thread)
    calls = sum(len(m.get("tool_calls") or []) for m in history)
    results = sum(1 for m in history if m["role"] == "tool")
    assert calls == results == 2, f"tool 往返不成对：{calls} 次调用 / {results} 条结果"
