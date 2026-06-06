"""Comment 数据访问层——唯一能 import Comment Model 的地方"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment


def _to_dict(c: Comment) -> dict:
    return {
        "id": c.id, "username": c.username, "video_id": c.video_id,
        "author_id": c.author_id, "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


class CommentRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> int:
        """创建评论，返回新 ID"""
        c = Comment(**kwargs)
        self.db.add(c)
        await self.db.flush()
        return c.id

    async def delete(self, comment_id: int) -> None:
        from sqlalchemy import delete as del_
        await self.db.execute(del_(Comment).where(Comment.id == comment_id))

    async def get_by_id(self, comment_id: int) -> dict | None:
        row = await self.db.get(Comment, comment_id)
        return _to_dict(row) if row else None

    async def get_all(self, video_id: int, limit: int = 200) -> list[dict]:
        stmt = (
            select(Comment)
            .where(Comment.video_id == video_id)
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]
