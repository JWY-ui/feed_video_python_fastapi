"""内容互动工具：点赞、取消点赞、评论。

点赞/取消是 write_reversible，直接执行。发评论对外可见、撤不回来，是 write_public，
走确认流程。
"""
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
from app.repositories.comment_repo import CommentRepository
from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository
from app.services.comment_service import CommentService
from app.services.like_service import LikeService


class VideoIdArgs(BaseModel):
    video_id: int = Field(..., description="视频 ID")


class PublishCommentArgs(BaseModel):
    video_id: int = Field(..., description="要评论的视频 ID")
    content: str = Field(..., min_length=1, max_length=500, description="评论内容")


class NoArgs(BaseModel):
    """无参数工具用。"""


async def _like_video(ctx: ToolContext, args: VideoIdArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = LikeService(LikeRepository(session), VideoRepository(session))
        try:
            await svc.like(args.video_id, ctx.account_id, ctx.username)
        except ValueError as e:
            return ToolResult(summary=f"点赞失败：{e}", data=None)
        await session.commit()
    return ToolResult(summary="已点赞", data={"video_id": args.video_id})


async def _unlike_video(ctx: ToolContext, args: VideoIdArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = LikeService(LikeRepository(session), VideoRepository(session))
        try:
            await svc.unlike(args.video_id, ctx.account_id)
        except ValueError as e:
            return ToolResult(summary=f"取消点赞失败：{e}", data=None)
        await session.commit()
    return ToolResult(summary="已取消点赞", data={"video_id": args.video_id})


async def _list_my_liked_videos(ctx: ToolContext, args: NoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = LikeService(LikeRepository(session), VideoRepository(session))
        videos = await svc.list_liked_videos(ctx.account_id)
    return ToolResult(
        summary=f"你赞过 {len(videos)} 个视频",
        data=[{
            "id": v["id"],
            "title": v["title"],
            "author": v["username"],
            "likes": v["likes_count"],
        } for v in videos],
    )


async def _list_comments(ctx: ToolContext, args: VideoIdArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = CommentService(CommentRepository(session), VideoRepository(session))
        try:
            comments = await svc.get_all(args.video_id)
        except ValueError:
            return ToolResult(summary="视频不存在", data=None)
    return ToolResult(
        summary=f"这个视频有 {len(comments)} 条评论",
        data=[{
            "id": c["id"],
            "author": c["username"],
            "content": c["content"],
        } for c in comments],
    )


async def _publish_comment(ctx: ToolContext, args: PublishCommentArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = CommentService(CommentRepository(session), VideoRepository(session))
        try:
            await svc.publish(
                args.video_id, ctx.account_id, ctx.username, args.content
            )
        except ValueError as e:
            return ToolResult(summary=f"发表评论失败：{e}", data=None)
        await session.commit()

    # ui 由服务端构造：前端据此把评论抽屉打开到这条视频
    return ToolResult(
        summary=f"已在视频 {args.video_id} 下发表评论：{args.content}",
        data={"video_id": args.video_id},
        ui=[
            {"action": "toast", "level": "ok", "text": "评论已发布"},
            {"action": "navigate", "to": f"/video/{args.video_id}"},
        ],
    )


register(
    ToolSpec(
        name="like_video",
        description="给一个视频点赞。用户明确要表达喜欢时用。",
        args_model=VideoIdArgs,
        tier=Tier.WRITE_REVERSIBLE,
        handler=_like_video,
    )
)

register(
    ToolSpec(
        name="unlike_video",
        description="取消对某个视频的点赞。",
        args_model=VideoIdArgs,
        tier=Tier.WRITE_REVERSIBLE,
        handler=_unlike_video,
    )
)

register(
    ToolSpec(
        name="list_my_liked_videos",
        description="看用户自己赞过的视频。",
        args_model=NoArgs,
        tier=Tier.READ,
        handler=_list_my_liked_videos,
    )
)

register(
    ToolSpec(
        name="list_comments",
        description="看某个视频下的评论。用户问「大家怎么说」时用。",
        args_model=VideoIdArgs,
        tier=Tier.READ,
        handler=_list_comments,
    )
)

register(
    ToolSpec(
        name="publish_comment",
        description="在视频下发评论。发表前会先让用户确认。",
        args_model=PublishCommentArgs,
        tier=Tier.WRITE_PUBLIC,
        handler=_publish_comment,
    )
)
