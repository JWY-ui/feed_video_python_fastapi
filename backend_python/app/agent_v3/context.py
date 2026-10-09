"""上下文工程：工具结果的单条上限 + 长对话的 token 预算裁剪。

独立成模块是因为这两件事都是纯函数 —— 不碰 DB、不碰网络，可以单独单测。

v2 的两个问题在这里修掉：
  * 工具结果 `str(result)` 原样进上下文，一次 list_comments 能灌几十 KB
  * 历史只按条数截断（MAX_HISTORY=20），完全不看 token
"""
from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

TOOL_RESULT_MAX_BYTES = 4096

_LIST_NOTE = "结果过多，已省略 {n} 条，可缩小查询范围或调小 limit。"
_TRUNCATE_NOTE = "结果过大，已截断，可缩小查询范围。"


def _dumps(data) -> str:
    """紧凑 JSON。

    ensure_ascii=False：中文不转义成 \\uXXXX —— 既省 token 又可读。
    default=str：工具数据里夹着 datetime 这类非 JSON 类型时不炸。
    """
    return json.dumps(data, ensure_ascii=False, default=str)


def render_tool_result(data, *, max_bytes: int = TOOL_RESULT_MAX_BYTES) -> str:
    """把工具结果渲染成喂回模型的文本，超过上限就裁剪。

    无论怎么裁，返回值**始终是合法 JSON** —— 模型收到坏 JSON 只会更容易胡编。
    """
    text = _dumps(data)
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    if isinstance(data, list):
        return _trim_list(data, max_bytes)

    preview = text.encode("utf-8")[: max_bytes - 256].decode("utf-8", "ignore")
    return _dumps({"truncated": True, "note": _TRUNCATE_NOTE, "preview": preview})


def _trim_list(items: list, max_bytes: int) -> str:
    """尽量多留前缀，并如实说明省略了多少条。"""
    def payload_for(kept: list) -> dict:
        omitted = len(items) - len(kept)
        return {
            "returned": kept,
            "omitted": omitted,
            "note": _LIST_NOTE.format(n=omitted),
        }

    kept: list = []
    for item in items:
        candidate = kept + [item]
        if len(_dumps(payload_for(candidate)).encode("utf-8")) > max_bytes:
            break
        kept = candidate
    return _dumps(payload_for(kept))


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。只需要一个单调的近似值来决定"是否超预算"。

    ASCII 约 4 字符/token，非 ASCII（中文）约 1 字符/token。不引 tiktoken ——
    精确分词对"该不该裁剪"这个决定没有意义，却要付一整个分词器的依赖。
    """
    ascii_chars = sum(1 for ch in text if ch.isascii())
    return ascii_chars // 4 + (len(text) - ascii_chars)


def _message_tokens(message) -> int:
    total = estimate_tokens(getattr(message, "content", "") or "")
    for call in getattr(message, "tool_calls", None) or []:
        total += estimate_tokens(_dumps(call))
    return total


def trim_to_budget(messages: list, max_tokens: int) -> list:
    """从最新往回留，直到预算用尽。

    ToolMessage 必须和它的 tool_call_id 成对出现，否则 OpenAI 协议直接报错 ——
    所以裁完之后要把**开头悬空**的工具结果一并丢掉。
    """
    total = sum(_message_tokens(m) for m in messages)
    if total <= max_tokens:
        return list(messages)

    kept: list = []
    used = 0
    for message in reversed(messages):
        cost = _message_tokens(message)
        if kept and used + cost > max_tokens:
            break
        kept.append(message)
        used += cost
    kept.reverse()

    while kept and isinstance(kept[0], ToolMessage):
        kept.pop(0)
    return kept
