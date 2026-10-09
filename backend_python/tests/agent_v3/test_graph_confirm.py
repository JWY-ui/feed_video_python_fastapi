"""状态机：对外可见的写操作必须经用户确认才真正执行。

这是 v3 唯一真正难写、也最容易在后续改工具时被静默打破的地方。用桩模型把
interrupt / resume 的语义定住 —— 不依赖真模型、不依赖网络，可确定性重跑。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent_v3.graph import build_graph
from stubs import EXECUTED, StubChatModel, wants

CONFIG = {"configurable": {"thread_id": "test-thread"}}
START_STATE = {
    "messages": [HumanMessage(content="帮我处理一下")],
    "account_id": 7,
    "username": "我",
}


def _build(script: list[AIMessage]):
    return build_graph(llm=StubChatModel(script), checkpointer=InMemorySaver())


async def test_read_tool_executes_without_confirmation(stub_tools):
    graph = _build([wants("t_read"), AIMessage(content="好了")])

    state = await graph.ainvoke(START_STATE, CONFIG)

    assert EXECUTED == [("read", 1)]
    assert state["messages"][-1].content == "好了"


async def test_public_write_interrupts_before_executing(stub_tools):
    graph = _build([wants("t_write"), AIMessage(content="好了")])

    await graph.ainvoke(START_STATE, CONFIG)

    snapshot = await graph.aget_state(CONFIG)
    assert snapshot.interrupts, "对外可见的写操作必须先挂起"
    assert EXECUTED == [], "挂起期间绝不能已经执行"


async def test_interrupt_payload_describes_the_pending_write(stub_tools):
    graph = _build([wants("t_write"), AIMessage(content="好了")])
    await graph.ainvoke(START_STATE, CONFIG)

    payload = (await graph.aget_state(CONFIG)).interrupts[0].value

    assert payload["calls"][0]["tool"] == "t_write"
    assert payload["calls"][0]["args"] == {"n": 1}


async def test_approving_executes_the_write(stub_tools):
    graph = _build([wants("t_write"), AIMessage(content="好了")])
    await graph.ainvoke(START_STATE, CONFIG)

    state = await graph.ainvoke(Command(resume={"approved": True}), CONFIG)

    assert EXECUTED == [("write", 1)]
    assert state["messages"][-1].content == "好了"


async def test_rejecting_skips_the_write_and_tells_the_model(stub_tools):
    graph = _build([wants("t_write"), AIMessage(content="那算了")])
    await graph.ainvoke(START_STATE, CONFIG)

    state = await graph.ainvoke(Command(resume={"approved": False}), CONFIG)

    assert EXECUTED == [], "用户拒绝后不能再执行写操作"
    assert any("取消" in (getattr(m, "content", "") or "")
               for m in state["messages"]), "要让模型知道用户拒绝了"
    assert state["messages"][-1].content == "那算了"
