"""LangGraph 图：唯一碰 LangGraph 的地方。

图骨架：

    START → agent ─┬─(有 write_public)→ confirm → tools → agent ...
                   ├─(只有读/可逆写)────→ tools ──→ agent ...
                   └─(没有工具调用)────→ END

`confirm` 节点内部调 `interrupt()`（动态中断）挂起，用户在前端点确认后由
`Command(resume=...)` 恢复。用动态而非静态 `interrupt_before`：静态断点无法把
「同意还是取消」传回节点。

`interrupt()` 恢复时节点会**从头重跑**，所以 `confirm` 节点在 `interrupt()` 之前
只能做无副作用的准备 —— 真正的写操作必须放在它之后的 `tools` 节点。
"""
from __future__ import annotations

import json
import operator
import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app.agent_v3.context import render_tool_result, trim_to_budget
from app.agent_v3.tools import Tier, ToolContext, get_spec, specs_for_llm
from app.config import settings

SYSTEM_PROMPT = """你是短视频平台的站内助手，帮用户找内容、看评论、管理关注和私信。

当前用户：{username}（账号 ID {account_id}）。需要用户自己的资料时直接用这两个值，不必再查。

规则：
- 回答简短、口语化。
- 需要发私信、发评论这类对外可见的操作时，直接调用工具 —— 系统会先请用户确认，
  你不要在回复里再问一遍。
- 找不到就直说，不要编造视频 ID 或用户名。"""


class AgentState(TypedDict):
    # 身份由服务端在图启动时注入。模型只能产出 messages，改不了这两个字段，
    # 所以提示注入无法借工具参数提权。
    account_id: int
    username: str
    messages: Annotated[list, add_messages]
    ui_actions: Annotated[list[dict], operator.add]
    usage: Annotated[list[dict], operator.add]


def _pending_calls(state: AgentState) -> list[dict]:
    """最后一条消息里模型想调的工具。"""
    last = state["messages"][-1]
    return list(getattr(last, "tool_calls", None) or [])


def _is_public_write(name: str) -> bool:
    spec = get_spec(name)
    return spec is not None and spec.tier is Tier.WRITE_PUBLIC


def route_after_agent(state: AgentState) -> str:
    """模型这一轮想调的工具里，只要有一个 write_public，就先去确认。

    只读和可逆写不打断用户。未注册的工具名不算写操作 —— 它执行不了任何东西，
    交给 tools 节点回一句「没有这个工具」即可。
    """
    calls = _pending_calls(state)
    if not calls:
        return END
    if any(_is_public_write(call["name"]) for call in calls):
        return "confirm"
    return "tools"


def route_after_confirm(state: AgentState) -> str:
    """用户批准 → 放行到 tools；拒绝 → 把「已取消」交回模型。"""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "agent"


def _emit(payload: dict) -> None:
    """往 SSE 流推一条自定义事件（工具轨迹）。

    在 `ainvoke`（非流式）下 `get_stream_writer()` 返回一个空接收器，所以单元测试
    里调它没有任何副作用。
    """
    get_stream_writer()(payload)


def _preview(call: dict) -> str:
    """给确认卡看的一句话。"""
    args = call.get("args") or {}
    if call["name"] == "send_message":
        return f"将给用户 {args.get('to_id')} 发送私信：{args.get('content')}"
    if call["name"] == "publish_comment":
        return f"将在视频 {args.get('video_id')} 下发表评论：{args.get('content')}"
    return f"将执行 {call['name']}（参数 {json.dumps(args, ensure_ascii=False)}）"


def build_graph(*, llm, checkpointer):
    """编译图。

    `llm` 显式注入（而不是在模块里直接构造 ChatOpenAI）—— 生产传真模型，测试传桩模型，
    两者接口一致。`checkpointer` 生产传 AsyncMySaver，测试传 InMemorySaver。
    """
    bound = llm.bind_tools(specs_for_llm())

    async def call_model(state: AgentState) -> dict:
        system = SystemMessage(
            content=SYSTEM_PROMPT.format(
                username=state.get("username", ""),
                account_id=state.get("account_id", 0),
            )
        )
        history = trim_to_budget(
            state["messages"], settings.agent_max_context_tokens
        )
        ai = await bound.ainvoke([system, *history])
        return {"messages": [ai]}

    async def run_tools(state: AgentState) -> dict:
        ctx = ToolContext(
            account_id=state["account_id"], username=state["username"]
        )
        messages: list[ToolMessage] = []
        ui_actions: list[dict] = []
        usage: list[dict] = []

        for call in _pending_calls(state):
            spec = get_spec(call["name"])
            if spec is None:
                messages.append(
                    ToolMessage(
                        content=json.dumps(
                            {"error": f"没有名为 {call['name']} 的工具"},
                            ensure_ascii=False,
                        ),
                        tool_call_id=call["id"],
                    )
                )
                continue

            # 先推「开始」再执行 —— 前端据此立刻显示进行中的一行，
            # 而不是等工具跑完才凭空出现结果。
            _emit(
                {
                    "event": "tool_start",
                    "data": {
                        "call_id": call["id"],
                        "tool": spec.name,
                        "args": call["args"],
                        "tier": spec.tier.value,
                    },
                }
            )

            started = time.monotonic()
            ok = True
            ui: list[dict] = []
            try:
                args = spec.args_model(**call["args"])
                result = await spec.handler(ctx, args)
                summary = result.summary
                payload = result.data
                ui = list(result.ui)
            except Exception as e:  # 工具失败不能让整轮对话塌掉
                ok = False
                summary = f"工具执行失败：{e}"
                payload = {"error": str(e)}

            elapsed_ms = int((time.monotonic() - started) * 1000)
            ui_actions.extend(ui)
            usage.append(
                {"tool": spec.name, "ok": ok, "ms": elapsed_ms, "summary": summary}
            )
            _emit(
                {
                    "event": "tool_end",
                    "data": {
                        "call_id": call["id"],
                        "tool": spec.name,
                        "ok": ok,
                        "ms": elapsed_ms,
                        "summary": summary,
                        # 只推服务端构造的 UI 指令，不推原始工具输出
                        "ui": ui,
                    },
                }
            )
            messages.append(
                ToolMessage(
                    content=render_tool_result(payload),
                    tool_call_id=call["id"],
                )
            )

        return {"messages": messages, "ui_actions": ui_actions, "usage": usage}

    async def ask_user(state: AgentState) -> dict:
        pending = [c for c in _pending_calls(state) if _is_public_write(c["name"])]

        # 动态中断：第一次执行到这里挂起，用户点了确认后 resume 值作为返回值。
        # 注意此节点会被从头重跑，所以上面只能做无副作用的准备。
        decision = interrupt(
            {
                "calls": [
                    {
                        "call_id": c["id"],
                        "tool": c["name"],
                        "args": c["args"],
                        "preview": _preview(c),
                    }
                    for c in pending
                ]
            }
        )

        if decision and decision.get("approved"):
            return {}

        # 被拒绝：为每个待确认的调用回一条 ToolMessage，让模型知道发生了什么。
        return {
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {"cancelled": True, "reason": "用户取消了该操作"},
                        ensure_ascii=False,
                    ),
                    tool_call_id=c["id"],
                )
                for c in pending
            ]
        }

    builder = StateGraph(AgentState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", run_tools)
    builder.add_node("confirm", ask_user)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "confirm": "confirm", END: END},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "confirm", route_after_confirm, {"tools": "tools", "agent": "agent"}
    )

    return builder.compile(checkpointer=checkpointer)
