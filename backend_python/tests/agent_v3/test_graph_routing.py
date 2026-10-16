"""路由：只读链路不被打断，对外可见的写操作必须经用户确认，循环有上限。

`route_after_agent` 是确认机制的第一道闸门 —— 它看模型这一轮想调哪些工具，
决定是直接执行（tools）还是先挂起问用户（confirm）。另一头是「这个循环什么时候
结束」：模型可以一直调工具，得有人喊停。
"""
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END

from app.agent_v3.graph import build_graph, route_after_agent
from app.config import settings
from stubs import EXECUTED, StubChatModel, wants


def _wants(*tool_names: str) -> AIMessage:
    """构造一条"模型想调这些工具"的消息。"""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {}, "id": f"call_{i}", "type": "tool_call"}
            for i, name in enumerate(tool_names)
        ],
    )


def test_no_tool_calls_ends_the_turn():
    state = {"messages": [AIMessage(content="好的，我看看")]}
    assert route_after_agent(state) == END


def test_read_only_tool_runs_directly():
    state = {"messages": [_wants("search_videos")]}
    assert route_after_agent(state) == "tools"


def test_reversible_write_does_not_interrupt():
    state = {"messages": [_wants("like_video")]}
    assert route_after_agent(state) == "tools"


def test_public_write_goes_through_confirm():
    state = {"messages": [_wants("send_message")]}
    assert route_after_agent(state) == "confirm"


def test_one_public_write_in_a_batch_forces_confirm():
    """同一轮里只要有一个对外可见的写操作，整批都要先确认。"""
    state = {"messages": [_wants("search_videos", "send_message")]}
    assert route_after_agent(state) == "confirm"


def test_unknown_tool_name_is_not_treated_as_a_write():
    """模型幻觉出的工具名不该触发确认 —— 它根本执行不了任何东西。"""
    state = {"messages": [_wants("delete_everything")]}
    assert route_after_agent(state) == "tools"


async def test_a_model_that_keeps_calling_tools_is_stopped_at_the_budget(
    stub_tools, monkeypatch
):
    """模型一直调工具时，要在 agent_max_tool_turns 处停下并给用户一句解释。

    这个额度一直写在 config.py 里、注释也写着「超出则结束图并给出提示」，但从没
    接过线 —— 真实后果是撞上 LangGraph 默认的 recursion_limit，抛一个用户完全
    看不懂的异常。每次迭代都在烧 token，所以上限必须真的生效。
    """
    monkeypatch.setattr(settings, "agent_max_tool_turns", 3)
    graph = build_graph(
        # 脚本管够：模型每次都还想调工具，永远不肯停。
        # 注意必须每条都新建 —— `[wants(...)] * 20` 重复的是同一个对象，20 条脚本项
        # 会共享同一个消息 id，而 add_messages 按 id 去重（同 id 视为「改这条」，
        # 原地替换而不是追加），循环会假象成一轮就结束。
        llm=StubChatModel([wants("t_read") for _ in range(20)]),
        checkpointer=InMemorySaver(),
    )

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="一直查")],
            "account_id": 7,
            "username": "我",
        },
        {"configurable": {"thread_id": "budget-test"}},
    )

    assert len(EXECUTED) == settings.agent_max_tool_turns, (
        f"该正好跑满 {settings.agent_max_tool_turns} 轮，实际 {len(EXECUTED)} 轮"
    )
    assert "上限" in state["messages"][-1].content or "次数" in state["messages"][-1].content, (
        f"停下来时该给用户一句解释，实际是：{state['messages'][-1].content!r}"
    )
