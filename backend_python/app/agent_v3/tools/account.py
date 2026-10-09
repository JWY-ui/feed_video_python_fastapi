"""账号域工具：看自己的资料、看通知。"""
from __future__ import annotations

from pydantic import BaseModel

from app.agent_v3.tools.registry import (
    Tier,
    ToolContext,
    ToolResult,
    ToolSpec,
    register,
)
from app.database import AsyncSessionLocal
from app.repositories.account_repo import AccountRepository
from app.repositories.notification_repo import NotificationRepository
from app.services.account_service import AccountService
from app.services.notification_service import NotificationService


class NoArgs(BaseModel):
    """无参数工具用。"""


async def _get_my_profile(ctx: ToolContext, args: NoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        try:
            user = await AccountService(AccountRepository(session)).find_by_id(
                ctx.account_id
            )
        except ValueError:
            return ToolResult(summary="账号不存在", data=None)

    # 只挑公开字段。account 的 dict 里带着 password / token / refresh_token，
    # 整条丢进上下文等于把凭据递给模型（也会进 transcript 和日志）。
    return ToolResult(
        summary=f"你是 {user['username']}",
        data={
            "id": user["id"],
            "username": user["username"],
            "avatar_url": user["avatar_url"],
            "bio": user["bio"],
        },
    )


async def _list_notifications(ctx: ToolContext, args: NoArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = NotificationService(NotificationRepository(session))
        items = await svc.list_by_user(ctx.account_id)
    return ToolResult(
        summary=f"你有 {len(items)} 条通知",
        data=[{
            "type": n["type"],
            "content": n["content"],
            "read": n["is_read"],
        } for n in items],
    )


register(
    ToolSpec(
        name="get_my_profile",
        description="看用户自己的资料（用户名、头像、简介）。",
        args_model=NoArgs,
        tier=Tier.READ,
        handler=_get_my_profile,
    )
)

register(
    ToolSpec(
        name="list_notifications",
        description="看用户的通知（谁点赞、评论、关注了）。用户问「有人找我吗」时用。",
        args_model=NoArgs,
        tier=Tier.READ,
        handler=_list_notifications,
    )
)
