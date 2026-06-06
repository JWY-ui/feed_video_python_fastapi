"""通知模块——Pydantic 请求/响应模型"""
from pydantic import BaseModel


class MarkReadRequest(BaseModel):
    id: int | None = None  # None 表示全部标记已读


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
