"""工具注册表的机制部分（types + 注册表），不含任何具体工具。

具体工具在 tools/<域>.py 里定义并 register()，由 tools/__init__.py 汇总导入。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel


class Tier(str, enum.Enum):
    """工具级别 —— 决定它是否需要用户确认。

    read              只读，直接执行
    write_reversible  有反向操作、影响面小，直接执行
    write_public      对外可见、不可撤回，必须用户确认
    """

    READ = "read"
    WRITE_REVERSIBLE = "write_reversible"
    WRITE_PUBLIC = "write_public"


@dataclass(frozen=True)
class ToolContext:
    """服务端注入的身份。

    模型既看不到也改不了它 —— 提示注入无法借工具参数提权，这是安全边界的地基。
    """

    account_id: int
    username: str


@dataclass
class ToolResult:
    """工具的双通道返回。

    summary  给模型和 UI 看的一句话
    data     喂回 LLM 的结构化数据（精简投影，不含 play_url 这类长字段）
    ui       给前端的 UI 指令 —— **必须由服务端构造，绝不能由模型产出**
    """

    summary: str
    data: Any = None
    ui: list[dict] = field(default_factory=list)


Handler = Callable[[ToolContext, Any], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    tier: Tier
    handler: Handler

    def openai_schema(self) -> dict:
        """转成 OpenAI 兼容的 tools 声明（DeepSeek 走同一协议）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in REGISTRY:
        raise ValueError(f"duplicate tool name: {spec.name}")
    REGISTRY[spec.name] = spec
    return spec


def get_spec(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def specs_for_llm() -> list[dict]:
    return [spec.openai_schema() for spec in REGISTRY.values()]
