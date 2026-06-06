"""
评论表 (comments)

设计要点：
  1. username 冗余存储——和 Video 表一样，评论列表展示作者名时避免 JOIN
  2. author_id 单独存——用于删除权限校验："只有作者本人能删"
  3. 三个索引各有用途：
     idx_username  → 极少用（@提及通知时按名查人可走）
     idx_video_id  → 视频详情页加载评论列表（每页 200 条，时间正序）
     idx_author_id → 几乎不用（暂未实现"我的评论"功能，但预留索引）

被哪些查询使用：
  - 发布评论：INSERT
  - 删除评论：DELETE WHERE id = ?（主键删除）
  - 评论列表：SELECT WHERE video_id = ? ORDER BY created_at ASC LIMIT 200
  - @提及通知：SELECT id FROM accounts WHERE username = ?（跨表查询）
"""
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 冗余的作者名——评论列表展示时不需要 JOIN accounts
    username: Mapped[str] = mapped_column(String(255), index=True)
    # 所属视频 ID——评论列表查询的高频过滤条件
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    # 作者 ID——删除评论时的权限校验字段
    author_id: Mapped[int] = mapped_column(Integer, index=True)
    # 评论内容。Text 类型可存长文本（MySQL 最大 65KB）
    content: Mapped[str] = mapped_column(Text)
    # 评论时间。列表按时间正序排列（旧评论在前）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
