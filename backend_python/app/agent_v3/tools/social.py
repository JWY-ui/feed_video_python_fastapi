"""关注关系与找用户。

关注/取关是 write_reversible：有反向操作、影响面小，所以直接执行不打断用户。
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
from app.repositories.account_repo import AccountRepository
from app.repositories.social_repo import SocialRepository
from app.services.account_service import AccountService
from app.services.social_service import SocialService


class SearchUserArgs(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="用户名的一部分即可，会模糊匹配并返回候选列表",
    )


class FollowArgs(BaseModel):
    vlogger_id: int = Field(..., description="对方的账号 ID（先 search_user 拿到）")


class NoArgs(BaseModel):
    """无参数工具用。"""


def _user_list(users: list[dict], summary: str) -> ToolResult:
    return ToolResult(
        summary=summary,
        data=[{"id": u["id"], "username": u["username"]} for u in users],
    )


async def _search_user(ctx: ToolContext, args: SearchUserArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        users = await AccountService(AccountRepository(session)).search(args.query)
    if not users:
        return ToolResult(
            summary=f"没找到用户名含「{args.query}」的用户，可以让用户确认一下名字",
            data=[],
        )
    return _user_list(users, f"找到 {len(users)} 个用户")


async def _get_following(ctx: ToolContext, args: NoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = SocialService(SocialRepository(session), AccountRepository(session))
        users, _count = await svc.get_all_vloggers(ctx.account_id)
    return _user_list(users, f"你关注了 {len(users)} 个人")


async def _get_followers(ctx: ToolContext, args: NoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = SocialService(SocialRepository(session), AccountRepository(session))
        users, _count = await svc.get_all_followers(ctx.account_id)
    return _user_list(users, f"你有 {len(users)} 个粉丝")


async def _follow_user(ctx: ToolContext, args: FollowArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = SocialService(SocialRepository(session), AccountRepository(session))
        try:
            await svc.follow(ctx.account_id, args.vlogger_id)
        except ValueError as e:
            return ToolResult(summary=f"关注失败：{e}", data=None)
        await session.commit()
    return ToolResult(summary="已关注", data={"vlogger_id": args.vlogger_id})


async def _unfollow_user(ctx: ToolContext, args: FollowArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = SocialService(SocialRepository(session), AccountRepository(session))
        try:
            await svc.unfollow(ctx.account_id, args.vlogger_id)
        except ValueError as e:
            return ToolResult(summary=f"取消关注失败：{e}", data=None)
        await session.commit()
    return ToolResult(summary="已取消关注", data={"vlogger_id": args.vlogger_id})


register(
    ToolSpec(
        name="search_user",
        description=(
            "按用户名找用户，模糊匹配并返回候选。要关注某人、给某人发私信之前先用它拿 ID。"
        ),
        args_model=SearchUserArgs,
        tier=Tier.READ,
        handler=_search_user,
    )
)

register(
    ToolSpec(
        name="get_following",
        description="看用户关注了谁。",
        args_model=NoArgs,
        tier=Tier.READ,
        handler=_get_following,
    )
)

register(
    ToolSpec(
        name="get_followers",
        description="看谁关注了用户。",
        args_model=NoArgs,
        tier=Tier.READ,
        handler=_get_followers,
    )
)

register(
    ToolSpec(
        name="follow_user",
        description="关注某个用户。需要对方的账号 ID。",
        args_model=FollowArgs,
        tier=Tier.WRITE_REVERSIBLE,
        handler=_follow_user,
    )
)

register(
    ToolSpec(
        name="unfollow_user",
        description="取消关注某个用户。",
        args_model=FollowArgs,
        tier=Tier.WRITE_REVERSIBLE,
        handler=_unfollow_user,
    )
)
