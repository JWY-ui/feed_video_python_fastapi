"""
点赞表 (likes)

唯一约束 (video_id, account_id)：同一用户对同一视频只能赞一次。
这是数据库层面最后一道防线——Service 层虽然也做了查重，
但并发场景下两个请求同时查"未点赞"并同时 INSERT，数据库唯一约束
能保证不产生重复数据。

被哪些查询使用：
  - 点赞：INSERT + 唯一约束冲突检测
  - 取消赞：DELETE WHERE video_id = ? AND account_id = ?
  - 是否已赞：SELECT COUNT WHERE video_id = ? AND account_id = ?
  - 批量查点赞状态：SELECT video_id WHERE video_id IN (...) AND account_id = ?
  - 我赞过的视频：JOIN likes + videos WHERE account_id = ?
"""
from datetime import datetime

from sqlalchemy import Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 被点赞的视频 ID
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 点赞者的用户 ID
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 点赞时间。列表查询按此字段倒序
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # 联合唯一：同一人不能重复点赞同一视频
    __table_args__ = (UniqueConstraint("video_id", "account_id"),)
