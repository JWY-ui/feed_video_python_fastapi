"""路由：只读链路不被打断，对外可见的写操作必须经用户确认。

`route_after_agent` 是确认机制的第一道闸门 —— 它看模型这一轮想调哪些工具，
决定是直接执行（tools）还是先挂起问用户（confirm）。
"""
from langchain_core.messages import AIMessage
from langgraph.graph import END

from app.agent_v3.graph import route_after_agent


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
