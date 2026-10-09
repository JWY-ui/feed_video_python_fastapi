"""上下文工程：工具结果的单条上限，以及长对话的 token 预算裁剪。

v2 的教训：工具结果 `str(result)` 原样进上下文，一次 list_comments 就能灌进几十 KB；
历史只按条数截断（MAX_HISTORY=20），完全不看 token。
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent_v3.context import TOOL_RESULT_MAX_BYTES, render_tool_result, trim_to_budget


# ── 工具结果渲染 ────────────────────────────────────────────────

def test_small_tool_result_renders_as_json():
    text = render_tool_result({"id": 3, "title": "做菜"})

    assert json.loads(text) == {"id": 3, "title": "做菜"}


def test_chinese_is_not_escaped():
    """ensure_ascii 会把中文变成 \\uXXXX —— 既费 token 又难读。"""
    text = render_tool_result({"title": "做菜"})

    assert "做菜" in text


def test_oversized_list_keeps_a_prefix_and_reports_the_rest():
    data = [{"i": i, "title": "x" * 50} for i in range(500)]

    text = render_tool_result(data)

    assert len(text.encode("utf-8")) <= TOOL_RESULT_MAX_BYTES
    payload = json.loads(text)
    returned = payload["returned"]
    assert returned == data[: len(returned)], "必须是前缀，不能东挑西拣"
    assert payload["omitted"] == 500 - len(returned)
    assert "省略" in payload["note"]


def test_oversized_non_list_stays_valid_json():
    """硬截断也要能 json.loads —— 否则模型收到的是坏 JSON。"""
    text = render_tool_result({"blob": "x" * 20000})

    payload = json.loads(text)
    assert payload["truncated"] is True
    assert len(text.encode("utf-8")) <= TOOL_RESULT_MAX_BYTES


# ── token 预算裁剪 ─────────────────────────────────────────────

def _convo() -> list:
    return [HumanMessage(content="旧" * 300), AIMessage(content="旧答" * 300),
            HumanMessage(content="新问题")]


def test_under_budget_leaves_the_conversation_alone():
    messages = _convo()

    assert trim_to_budget(messages, 100_000) == messages


def test_over_budget_drops_the_oldest_and_keeps_the_newest():
    kept = trim_to_budget(_convo(), 40)

    assert kept[-1].content == "新问题"
    assert len(kept) < len(_convo())


def test_never_orphans_a_tool_result_from_its_call():
    """ToolMessage 必须和它的 tool_call_id 成对出现，否则 OpenAI 协议直接报错。"""
    call = AIMessage(content="", tool_calls=[
        {"name": "t", "args": {}, "id": "c1", "type": "tool_call"},
    ])
    result = ToolMessage(content="结果", tool_call_id="c1")
    messages = [HumanMessage(content="很旧" * 500), call, result]

    kept = trim_to_budget(messages, 30)

    has_call = any(getattr(m, "tool_calls", None) for m in kept)
    has_result = any(isinstance(m, ToolMessage) for m in kept)
    assert has_call == has_result
    assert has_result, "最新的一次工具往返不该被裁掉"


def test_drops_a_tool_result_whose_call_did_not_fit():
    """预算小到连工具调用都放不下时，宁可都不要，也不能留下孤儿 ToolMessage。"""
    call = AIMessage(content="", tool_calls=[
        {"name": "t", "args": {}, "id": "c1", "type": "tool_call"},
    ])
    messages = [HumanMessage(content="很旧" * 500), call,
                ToolMessage(content="结果", tool_call_id="c1")]

    kept = trim_to_budget(messages, 5)

    assert not any(isinstance(m, ToolMessage) for m in kept)
