"""
视频表 (videos) + 本地消息表 (outbox_msgs)

=== Video 表 ===
设计要点：
  1. author_id + username 冗余存储
     为什么违反第三范式？Feed 流每页 10~20 条视频都要显示作者名，
     如果每次 JOIN accounts 就是 20 次额外查询。冗余后一步到位。
     这是典型的"读远多于写，空间换时间"的设计。

  2. likes_count 是字段不是 COUNT(*)
     展示 20 条视频需要 20 次 COUNT(likes)，改成字段后点赞时 +1 即可，
     展示时直接读字段。写放大换读性能。

  3. popularity 是热度值（= 点赞 + 评论 + 关注等互动的加权累加）
     用于热度榜排序。后续可加时间衰减（旧互动的权重随时间降低）。

  4. 三个降序复合索引——服务于三种 Feed 流：
     idx_videos_create_time          → 最新视频流 WHERE create_time < ? ORDER BY create_time DESC
     idx_videos_likes_count_id       → 点赞排行   WHERE (likes_count < ?) OR (...) ORDER BY likes_count DESC, id DESC
     idx_videos_popularity_time_id   → 热度榜     WHERE (popularity < ?) OR (...) ORDER BY popularity DESC, create_time DESC, id DESC

     为什么都是降序？Feed 流永远取"最新的/最高的"，没有升序需求。
     为什么复合索引要包含 id？游标分页需要第二/第三排序键打破平局。

=== OutboxMsg 表 ===
  事务一致性：发布视频时，在同一事务内 INSERT videos 和 outbox_msgs。
  即使后续投递到消息队列失败，outbox_msgs 里仍有记录可补投。
  这是"发件箱模式"（Outbox Pattern）的简化实现。
"""
from datetime import datetime

from sqlalchemy import String, Integer, BigInteger, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 作者 ID。idx 索引用于 listByAuthorID 查询
    author_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 冗余的作者名。Feed 流展示时避免 JOIN accounts
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # 视频标题。发布时从标题+描述提取 #话题
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # 视频描述。可空
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 视频播放地址（mp4 文件 URL）
    play_url: Mapped[str] = mapped_column(String(255), nullable=False)
    # 封面图地址（jpg/png/webp 文件 URL）
    cover_url: Mapped[str] = mapped_column(String(255), nullable=False)
    # 创建时间。Feed 游标分页的核心排序字段
    create_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    # 点赞数。每次点赞 +1 / 取消点赞 -1，GREATEST 防止减成负数
    likes_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # 热度值。点赞+1、评论+1、关注+1 都增加热度。热度榜排序用
    popularity: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # 三个降序复合索引——各自服务一种 Feed 流查询
    __table_args__ = (
        # 最新视频流：WHERE create_time < cursor_time ORDER BY create_time DESC LIMIT N
        Index("idx_videos_create_time", "create_time"),
        # 点赞排行：WHERE (likes_count < ?) OR (likes_count = ? AND id < ?) ORDER BY likes_count DESC, id DESC
        Index("idx_videos_likes_count_id", likes_count.desc(), id.desc()),
        # 热度榜：WHERE (popularity < ?) OR (popularity = ? AND create_time < ?) OR (...) ORDER BY ...
        Index("idx_videos_popularity_time_id", popularity.desc(), create_time.desc(), id.desc()),
    )


class OutboxMsg(Base):
    """
    本地消息表——发件箱模式

    和 videos 在同一事务内写入，保证"视频发布"事件不丢失。
    status: pending → 待投递 → 投递成功 → 删除或标记为 sent
    """
    __tablename__ = "outbox_msgs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 关联的视频 ID
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    # 事件类型：video_published
    event_type: Mapped[str] = mapped_column(String(50))
    # 创建时间（等于视频发布时间，用于时间线排序）
    create_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    # 状态：pending（待投递）/ sent（已投递）/ failed（失败需重试）
    status: Mapped[str] = mapped_column(String(50), index=True, default="pending")
