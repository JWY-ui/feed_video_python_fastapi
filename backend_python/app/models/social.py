"""
关注关系表 (socials)

唯一约束 (follower_id, vlogger_id)：同一关注关系不能重复。

字段命名说明：
  follower → 粉丝（关注者，主动点关注的人）
  vlogger  → UP 主（被关注者，被关注的人）

被哪些查询使用：
  - 关注：INSERT + 唯一约束冲突检测
  - 取关：DELETE WHERE follower_id = ? AND vlogger_id = ?
  - 粉丝列表：SELECT follower_id WHERE vlogger_id = ? → JOIN accounts
  - 关注列表：SELECT vlogger_id WHERE follower_id = ? → JOIN accounts
  - 是否已关注：SELECT COUNT WHERE follower_id = ? AND vlogger_id = ?
  - 关注流 Feed：子查询 SELECT vlogger_id WHERE follower_id = ?
    用于 listByFollowing 的 IN 子查询
  - 粉丝数/关注数：COUNT WHERE vlogger_id/follower_id = ?
"""
from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Social(Base):
    __tablename__ = "socials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 粉丝——主动点关注的人。用于：查"我关注了谁"、关注流 Feed 子查询
    follower_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # UP 主——被关注的人。用于：查"谁关注了我"（粉丝列表）
    vlogger_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # 联合唯一：同一个关注关系不能存两次
    __table_args__ = (UniqueConstraint("follower_id", "vlogger_id"),)
