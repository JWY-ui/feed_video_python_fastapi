# -*- coding: utf-8 -*-
"""Message module -- Pydantic request/response models."""
from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    to_id: int = Field(..., gt=0)
    content: str = Field(..., min_length=1)


class ListMessagesRequest(BaseModel):
    peer_id: int = Field(..., gt=0)


class MessageInfo(BaseModel):
    id: int
    from_id: int
    to_id: int
    content: str
    is_read: bool
    created_at: str


class ListMessagesResponse(BaseModel):
    messages: list[MessageInfo]
