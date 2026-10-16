"""私信工具。

`send_message` 是 write_public —— 发出去就撤不回来，所以必须先经用户确认。
确认通过后的 tool_end 会带上 `ui.navigate`，前端据此跳到与对方的私信页。
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
from app.repositories.message_repo import MessageRepository
from app.services.message_service import MessageService


class SendMessageArgs(BaseModel):
    to_id: int = Field(..., description="收件人的账号 ID（先 search_user 拿到）")
    content: str = Field(..., min_length=1, max_length=500, description="私信内容")


class ListMessagesArgs(BaseModel):
    peer_id: int = Field(..., description="对方的账号 ID")


def _preview(args: dict) -> str:
    """确认卡文案。收件人和正文都要看得见 —— 否则等于没问用户。"""
    return f"将给用户 {args.get('to_id')} 发送私信：{args.get('content')}"


async def _send_message(ctx: ToolContext, args: SendMessageArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = MessageService(MessageRepository(session))
        try:
            await svc.send(ctx.account_id, args.to_id, args.content)
        except ValueError as e:
            return ToolResult(summary=f"发送失败：{e}", data=None)
        await session.commit()

    # ui 由服务端构造，模型无法产出 —— 否则提示注入就能操纵界面跳转。
    return ToolResult(
        summary=f"已给用户 {args.to_id} 发送私信：{args.content}",
        data={"to_id": args.to_id},
        ui=[
            {"action": "navigate", "to": f"/messages/{args.to_id}"},
            {"action": "toast", "level": "ok", "text": "私信已发送"},
        ],
    )


async def _list_messages(ctx: ToolContext, args: ListMessagesArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = MessageService(MessageRepository(session))
        messages = await svc.list(ctx.account_id, args.peer_id)
    return ToolResult(
        summary=f"你和对方有 {len(messages)} 条往来私信",
        data=[
            {
                "from_me": m["from_id"] == ctx.account_id,
                "content": m["content"],
            }
            for m in messages
        ],
    )


register(
    ToolSpec(
        name="send_message",
        description="给其他用户发私信。发送前会先让用户确认。",
        args_model=SendMessageArgs,
        tier=Tier.WRITE_PUBLIC,
        handler=_send_message,
        preview=_preview,
    )
)

register(
    ToolSpec(
        name="list_messages",
        description="看用户和某个人的私信往来。用户问「他回过我吗」时用。",
        args_model=ListMessagesArgs,
        tier=Tier.READ,
        handler=_list_messages,
    )
)
