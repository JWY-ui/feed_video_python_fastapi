"""测试替身：桩模型 + 一读一写两个合成工具。

`StubChatModel` 只实现图真正用到的方法，接口与 ChatOpenAI 一致 —— 换成真模型时
图本身不需要改。所以这个桩验证的是**状态机语义**，不是"mock 的行为"。
"""
from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agent_v3.tools import REGISTRY, Tier, ToolResult, ToolSpec, register


class Args(BaseModel):
    n: int = 0


# 每次工具真正执行时记一行，测试据此断言"有没有执行"
EXECUTED: list[tuple[str, int]] = []


async def read_handler(ctx, args):
    EXECUTED.append(("read", args.n))
    return ToolResult(summary="读到了", data={"n": args.n})


async def write_handler(ctx, args):
    EXECUTED.append(("write", args.n))
    return ToolResult(
        summary="写好了",
        data={"n": args.n},
        ui=[{"action": "navigate", "to": "/messages/42"}],
    )


SYNTHETIC_SPECS = [
    ToolSpec(name="t_read", description="读", args_model=Args,
             tier=Tier.READ, handler=read_handler),
    ToolSpec(name="t_write", description="写", args_model=Args,
             tier=Tier.WRITE_PUBLIC, handler=write_handler),
]


def install_synthetic_tools() -> None:
    for spec in SYNTHETIC_SPECS:
        register(spec)
    EXECUTED.clear()


def remove_synthetic_tools() -> None:
    for spec in SYNTHETIC_SPECS:
        REGISTRY.pop(spec.name, None)
    EXECUTED.clear()


class StubChatModel:
    """按脚本返回预设回复的假模型。"""

    def __init__(self, script: list[AIMessage]):
        self._script = list(script)
        self.bound: list | None = None

    def bind_tools(self, tools):
        self.bound = tools
        return self

    async def ainvoke(self, messages, **kwargs) -> AIMessage:
        return self._script.pop(0)


def wants(name: str) -> AIMessage:
    """构造一条"模型想调这个工具"的消息。"""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {"n": 1}, "id": f"c_{name}",
                     "type": "tool_call"}],
    )


async def call_tool(name: str, *, account_id: int = 1, username: str = "我",
                    **kwargs):
    """按注册表调用一个**真实**工具，返回 ToolResult。

    直接走注册表而不是 import 私有函数 —— 顺带证明这个工具确实注册上了、
    参数模型也吃得下这些参数。
    """
    from app.agent_v3.tools import REGISTRY, ToolContext

    spec = REGISTRY[name]
    return await spec.handler(
        ToolContext(account_id=account_id, username=username),
        spec.args_model(**kwargs),
    )
