# -*- coding: utf-8 -*-
"""Notification module -- Pydantic request/response models."""
from pydantic import BaseModel


class MarkReadRequest(BaseModel):
    id: int | None = None  # None means mark all as read


class NotificationInfo(BaseModel):
    id: int
    recipient_id: int
    sender_id: int
    type: str
    target_id: int
    content: str
    is_read: bool
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int
