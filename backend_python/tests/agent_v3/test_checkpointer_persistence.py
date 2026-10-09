"""生产用的 checkpointer（AsyncMySaver）：状态必须真的落在 MySQL 里。

InMemorySaver 那些测试证明的是状态机语义；这一条证明**生产路径**：挂起的确认
状态存在数据库里，而不是存在某个 Python 对象里。这正是「关掉标签页再回来还能
接着走」以及「点确认的那个 HTTP 请求和发起对话的不是同一个」能成立的原因。
"""
from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.agent_v3.graph import build_graph
from stubs import EXECUTED, StubChatModel, wants


def _state():
    return {
        "messages": [HumanMessage(content="帮我处理一下")],
        "account_id": 7,
        "username": "我",
    }


def _config() -> dict:
    return {"configurable": {"thread_id": uuid.uuid4().hex}}


async def test_transcript_survives_a_completely_new_graph(checkpointer, stub_tools):
    """消息存在 checkpointer 里，不在图对象里 —— 这是单源真相的前提。"""
    config = _config()
    first = build_graph(
        llm=StubChatModel([wants("t_read"), AIMessage(content="好了")]),
        checkpointer=checkpointer,
    )
    await first.ainvoke(_state(), config)

    second = build_graph(
        llm=StubChatModel([AIMessage(content="不该被调用")]),
        checkpointer=checkpointer,
    )
    messages = (await second.aget_state(config)).values["messages"]

    assert [type(m).__name__ for m in messages] == [
        "HumanMessage", "AIMessage", "ToolMessage", "AIMessage",
    ], "完整 transcript（含工具往返）必须从 checkpointer 读回来"


async def test_a_pending_confirmation_survives_a_new_graph(checkpointer, stub_tools):
    config = _config()
    first = build_graph(
        llm=StubChatModel([wants("t_write"), AIMessage(content="好了")]),
        checkpointer=checkpointer,
    )
    await first.ainvoke(_state(), config)
    assert EXECUTED == []

    # 全新实例、全新桩模型：状态只可能来自数据库
    second = build_graph(
        llm=StubChatModel([AIMessage(content="好了")]),
        checkpointer=checkpointer,
    )
    assert (await second.aget_state(config)).interrupts, "挂起状态必须持久化"

    await second.ainvoke(Command(resume={"approved": True}), config)

    assert EXECUTED == [("write", 1)], "换一个图实例也要能接着执行"
