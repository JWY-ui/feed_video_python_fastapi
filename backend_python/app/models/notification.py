"""
通知表 (notifications)

通知由互动事件触发：
  - like     : 有人点赞了你的视频 → type=like,    target_id=视频ID
  - comment  : 有人评论了你的视频 → type=comment, target_id=视频ID
  - follow   : 有人关注了你       → type=follow,  target_id=关注者ID
  - mention  : 有人在评论中 @了你 → type=mention, target_id=视频ID

查询模式：
  - 通知列表：SELECT WHERE recipient_id = ? ORDER BY created_at DESC LIMIT 50
    recipient_id 有索引，走索引查询（不需要全表扫描）
  - 未读计数：SELECT COUNT WHERE recipient_id = ? AND is_read = false
  - 标记已读：UPDATE WHERE recipient_id = ? AND id = ?（单条）/ WHERE recipient_id = ?（全部）

推送机制：
  通知写入 MySQL 后，通过 SSE 推送给在线用户。
  用户不在线也不丢——下次打开列表时从 MySQL 加载。
"""
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 接收者——通知给谁看。有索引，列表查询的核心过滤字段
    recipient_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 发送者——谁触发了通知（点赞/评论/关注的人）
    sender_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 通知类型：like / comment / follow / mention
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 关联目标 ID。如视频 ID（like/comment/mention）或用户 ID（follow）
    # 前端点击通知时跳转到对应页面
    target_id: Mapped[int] = mapped_column(Integer, default=0)
    # 通知文案。如 "tom 点赞了你的视频"
    content: Mapped[str] = mapped_column(String(255), default="")
    # 是否已读。标记已读接口会批量更新此字段
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # 通知创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
