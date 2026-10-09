"""SSE 事件流：把图的行为翻译成前端能消费的事件序列。

覆盖的是用户真正看得见的那条链路 —— 工具轨迹实时出现、写操作先弹确认、
确认后才真执行并且把 UI 指令带回去。
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete

from app.agent_v3.graph import build_graph
from app.agent_v3.service import AgentV3Service
from app.database import AsyncSessionLocal
from app.models.agent_v3 import AgentV3Conversation
from stubs import EXECUTED, StubChatModel, wants

ACCOUNT = 900002
OTHER_ACCOUNT = 900003
USERNAME = "我"


@pytest.fixture
async def clean_conversations():
    async def wipe():
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentV3Conversation).where(
                    AgentV3Conversation.account_id.in_([ACCOUNT, OTHER_ACCOUNT])
                )
            )
            await session.commit()

    await wipe()
    yield
    await wipe()


def _service(script: list[AIMessage]) -> AgentV3Service:
    graph = build_graph(llm=StubChatModel(script), checkpointer=InMemorySaver())
    return AgentV3Service(graph)


async def _drain(stream) -> list[dict]:
    return [event async for event in stream]


def _only(events: list[dict], name: str) -> list[dict]:
    return [e for e in events if e["event"] == name]


async def test_chat_streams_tokens_and_tool_activity(stub_tools, clean_conversations):
    svc = _service([wants("t_read"), AIMessage(content="找到啦")])

    events = await _drain(svc.chat_stream(ACCOUNT, USERNAME, "帮我看看"))

    assert "找到啦" in "".join(e["data"]["text"] for e in _only(events, "token"))
    assert _only(events, "tool_start")[0]["data"]["tool"] == "t_read"
    tool_end = _only(events, "tool_end")[0]
    assert tool_end["data"]["ok"] is True
    assert tool_end["data"]["summary"] == "读到了"
    assert _only(events, "done")


async def test_tool_output_is_not_leaked_as_a_token(stub_tools, clean_conversations):
    """工具结果是喂模型的，不该混进给用户看的 token 流。"""
    svc = _service([wants("t_read"), AIMessage(content="找到啦")])

    events = await _drain(svc.chat_stream(ACCOUNT, USERNAME, "帮我看看"))

    assert "读到了" not in "".join(e["data"]["text"] for e in _only(events, "token"))


async def test_public_write_pauses_and_executes_nothing(stub_tools, clean_conversations):
    svc = _service([wants("t_write"), AIMessage(content="好了")])

    events = await _drain(svc.chat_stream(ACCOUNT, USERNAME, "发条消息"))

    assert EXECUTED == [], "确认之前绝不能执行"
    confirm = _only(events, "confirm_required")
    assert confirm[0]["data"]["calls"][0]["tool"] == "t_write"
    assert _only(events, "tool_end") == []


async def test_approving_executes_the_write_and_carries_ui(stub_tools, clean_conversations):
    svc = _service([wants("t_write"), AIMessage(content="好了")])
    conv = await svc.create_conversation(ACCOUNT)
    await _drain(svc.chat_stream(ACCOUNT, USERNAME, "发条消息", conv["thread_id"]))
    assert EXECUTED == []

    events = await _drain(svc.confirm(ACCOUNT, conv["thread_id"], approved=True))

    assert EXECUTED == [("write", 1)]
    assert _only(events, "tool_end")[0]["data"]["ui"] == [
        {"action": "navigate", "to": "/messages/42"}
    ]


async def test_rejecting_executes_nothing(stub_tools, clean_conversations):
    svc = _service([wants("t_write"), AIMessage(content="那算了")])
    conv = await svc.create_conversation(ACCOUNT)
    await _drain(svc.chat_stream(ACCOUNT, USERNAME, "发条消息", conv["thread_id"]))

    events = await _drain(svc.confirm(ACCOUNT, conv["thread_id"], approved=False))

    assert EXECUTED == []
    assert _only(events, "done")


async def test_first_message_becomes_the_title(stub_tools, clean_conversations):
    svc = _service([AIMessage(content="好的")])

    await _drain(svc.chat_stream(ACCOUNT, USERNAME, "帮我找做菜的视频"))

    conversations = await svc.list_conversations(ACCOUNT)
    assert conversations[0]["title"] == "帮我找做菜的视频"


async def test_cannot_talk_into_someone_elses_thread(stub_tools, clean_conversations):
    svc = _service([AIMessage(content="好的")])
    conv = await svc.create_conversation(ACCOUNT)

    events = await _drain(
        svc.chat_stream(OTHER_ACCOUNT, "别人", "偷看", conv["thread_id"])
    )

    assert _only(events, "error")
