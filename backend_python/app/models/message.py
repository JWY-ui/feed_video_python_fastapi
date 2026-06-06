"""
私信表 (messages)

查询双方聊天记录时需要查"我发给对方"或"对方发给我"的全部消息：
  SELECT * FROM messages
  WHERE (from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?)
  ORDER BY created_at DESC
  LIMIT 50

两个单列索引（from_id, to_id）分别服务于：
  - 我发给所有人的私信（from_id 索引）
  - 所有人发给我的私信（to_id 索引）
  - 联合查询时 MySQL 会对两个索引做 index_merge
"""
from datetime import datetime

from sqlalchemy import String, Integer, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 发送者 ID
    from_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 接收者 ID
    to_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 消息内容。Text 可存长文本
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 是否已读。预留字段，当前版本未使用
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # 发送时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
