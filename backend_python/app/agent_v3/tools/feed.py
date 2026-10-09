"""feed 域工具。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent_v3.tools.registry import (
    Tier,
    ToolContext,
    ToolResult,
    ToolSpec,
    register,
)
from app.database import AsyncSessionLocal
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.services.feed_service import FeedService


class SearchVideosArgs(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="搜索关键词，会同时匹配视频标题、简介和标签",
    )
    limit: int = Field(default=10, gt=0, le=50, description="最多返回多少个视频")


def project_video(item) -> dict:
    """精简投影：只留模型判断需要的字段，不含 play_url / cover_url 这类长字段。"""
    return {
        "id": item.id,
        "title": item.title,
        "author": item.author.username,
        "author_id": item.author.id,
        "likes": item.likes_count,
        "liked_by_me": item.is_liked,
    }


async def _search_videos(ctx: ToolContext, args: SearchVideosArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = FeedService(FeedRepository(session), LikeRepository(session))
        items = await svc.search(args.query, args.limit, ctx.account_id)
    return ToolResult(
        summary=f"找到 {len(items)} 个视频",
        data=[project_video(v) for v in items],
    )


register(
    ToolSpec(
        name="search_videos",
        description=(
            "按关键词搜索视频。关键词会匹配标题、简介和标签三处。"
            "用户想找某类内容（例如「找几个做菜的视频」）时用这个。"
        ),
        args_model=SearchVideosArgs,
        tier=Tier.READ,
        handler=_search_videos,
    )
)
