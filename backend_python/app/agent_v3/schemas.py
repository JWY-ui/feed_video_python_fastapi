"""请求 DTO。

历史记录（/agent/conversations/{id}/history）直接返回 dict 列表，
与项目里其它返回裸数组的端点保持一致。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    # 不传就新建一个会话
    thread_id: str | None = Field(default=None, max_length=64)


class ConfirmRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=64)
    approved: bool
