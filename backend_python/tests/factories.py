"""往测试库造数据的小工具。

几条与模型有关的事实（都是查过源码确认的，别凭印象改）：
  * **没有任何外键** —— 所以引用一个不存在的 id 不会报错，夹具得自己保证一致；
  * 所有 `default=` 都是 **Python 侧**的，走 ORM 插入可以省略，纯 SQL 不行；
  * 时间列存的是 **naive UTC 墙钟**（`utc_now()` 给的是 aware，驱动写库时剥掉 tzinfo）；
  * 字段名不统一：`Video.create_time` 但别处是 `created_at`；`Message.from_id/to_id`；
    `Social.follower_id/vlogger_id`；
  * `likes(video_id, account_id)` 和 `socials(follower_id, vlogger_id)` 有唯一约束，
    重复插会 IntegrityError。

每个方法都会 **commit**：工具处理器自己开 session，看不到未提交的数据。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.comment import Comment
from app.models.like import Like
from app.models.message import Message
from app.models.notification import Notification
from app.models.social import Social
from app.models.tag import Tag, VideoTag
from app.models.video import Video

# 清空顺序无所谓（没有外键），但保持"子表在前"便于阅读
_TABLES = (Notification, Message, Social, Like, Comment, VideoTag, Tag, Video, Account)


async def wipe() -> None:
    """清空夹具拥有的全部表。

    只动这几张：checkpoint 表归 checkpointer fixture，agent_v3_conversations 归
    它自己的 fixture。测试库是独立的 feedsystem_test，整体清空是安全的。
    """
    async with AsyncSessionLocal() as session:
        for model in _TABLES:
            await session.execute(delete(model))
        await session.commit()


def _at(year: int, month: int, day: int) -> datetime:
    """造历史时间用。必须是 aware UTC —— 传 naive 会被驱动当 UTC 处理，也说得通，
    但显式一点免得后人猜。"""
    return datetime(year, month, day, tzinfo=timezone.utc)


class Maker:
    """一行行造数据。每个方法自己 commit。"""

    async def account(self, username: str) -> int:
        async with AsyncSessionLocal() as session:
            row = Account(username=username, password="$2b$12$testhash")
            session.add(row)
            await session.commit()
            return row.id

    async def video(
        self,
        author_id: int,
        title: str,
        *,
        username: str = "作者",
        description: str | None = None,
        likes_count: int = 0,
        popularity: int = 0,
        create_time: datetime | None = None,
        tags: tuple[str, ...] = (),
    ) -> int:
        async with AsyncSessionLocal() as session:
            row = Video(
                author_id=author_id,
                username=username,
                title=title,
                description=description,
                play_url=f"http://example.test/{title}.mp4",
                cover_url=f"http://example.test/{title}.jpg",
                likes_count=likes_count,
                popularity=popularity,
            )
            if create_time is not None:
                row.create_time = create_time
            session.add(row)
            await session.flush()
            video_id = row.id

            for name in tags:
                tag = Tag(name=name)
                session.add(tag)
                await session.flush()
                session.add(VideoTag(video_id=video_id, tag_id=tag.id))

            await session.commit()
            return video_id

    async def comment(self, video_id: int, author_id: int, content: str,
                      *, username: str = "评论者") -> int:
        async with AsyncSessionLocal() as session:
            row = Comment(
                username=username, video_id=video_id,
                author_id=author_id, content=content,
            )
            session.add(row)
            await session.commit()
            return row.id

    async def like(self, video_id: int, account_id: int) -> None:
        async with AsyncSessionLocal() as session:
            session.add(Like(video_id=video_id, account_id=account_id))
            await session.commit()

    async def follow(self, follower_id: int, vlogger_id: int) -> None:
        async with AsyncSessionLocal() as session:
            session.add(Social(follower_id=follower_id, vlogger_id=vlogger_id))
            await session.commit()

    async def message(self, from_id: int, to_id: int, content: str) -> int:
        async with AsyncSessionLocal() as session:
            row = Message(from_id=from_id, to_id=to_id, content=content)
            session.add(row)
            await session.commit()
            return row.id

    async def notification(self, recipient_id: int, sender_id: int,
                           type_: str, *, target_id: int = 0,
                           content: str = "") -> int:
        async with AsyncSessionLocal() as session:
            row = Notification(
                recipient_id=recipient_id, sender_id=sender_id,
                type=type_, target_id=target_id, content=content,
            )
            session.add(row)
            await session.commit()
            return row.id


__all__ = ["Maker", "wipe", "_at"]
