"""工具汇总：导入各域模块以填充 REGISTRY，再统一导出机制部分。

顺序无关，但每个域模块必须在 import 时调 register()。
"""
from app.agent_v3.tools.registry import (  # noqa: F401
    REGISTRY,
    Tier,
    ToolContext,
    ToolResult,
    ToolSpec,
    get_spec,
    register,
    specs_for_llm,
)
from app.agent_v3.tools import content, feed, message  # noqa: F401  (side-effect: register)

__all__ = [
    "REGISTRY",
    "Tier",
    "ToolContext",
    "ToolResult",
    "ToolSpec",
    "get_spec",
    "register",
    "specs_for_llm",
]
