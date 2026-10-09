"""内容互动工具：点赞、评论。"""
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
from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository
from app.services.like_service import LikeService


class LikeVideoArgs(BaseModel):
    video_id: int = Field(..., description="要点赞的视频 ID")


async def _like_video(ctx: ToolContext, args: LikeVideoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = LikeService(LikeRepository(session), VideoRepository(session))
        try:
            await svc.like(args.video_id, ctx.account_id, ctx.username)
        except ValueError as e:
            return ToolResult(summary=f"点赞失败：{e}")
        await session.commit()
    return ToolResult(summary="已点赞", data={"video_id": args.video_id})


register(
    ToolSpec(
        name="like_video",
        description="给一个视频点赞。用户明确要表达喜欢时用。",
        args_model=LikeVideoArgs,
        tier=Tier.WRITE_REVERSIBLE,
        handler=_like_video,
    )
)
