"""/agent/* 端点。

/chat 与 /confirm 是 SSE，都用 `get_current_user_stateless`：普通认证依赖
（get_current_user → get_db）会挂着一个 DB session 直到响应结束，对 SSE 就是
永远 —— 40 条并发流足以耗尽连接池。这是上一轮修 SSE 时踩过的坑。

帧格式与 /notification/stream 一致（`data: {json}`），前端复用同一个 SSE 解析器。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent_v3.deps import get_service
from app.agent_v3.schemas import ChatRequest, ConfirmRequest, ThreadRequest
from app.agent_v3.service import AgentV3Service
from app.middleware.jwt_auth import get_current_user, get_current_user_stateless

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # nginx 默认缓冲会把 SSE 攒成一坨再发，必须关掉
    "X-Accel-Buffering": "no",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream(request: Request, events):
    """客户端断开就停 —— 别让图继续跑下去（尤其别继续跑写操作）。"""
    async for event in events:
        if await request.is_disconnected():
            break
        yield _sse(event)


@router.post("/conversations")
async def create_conversation(
    user: dict = Depends(get_current_user),
    service: AgentV3Service = Depends(get_service),
):
    return await service.create_conversation(user["account_id"])


@router.post("/conversations/list")
async def list_conversations(
    user: dict = Depends(get_current_user),
    service: AgentV3Service = Depends(get_service),
):
    return await service.list_conversations(user["account_id"])


@router.post("/conversations/delete")
async def delete_conversation(
    req: ThreadRequest,
    user: dict = Depends(get_current_user),
    service: AgentV3Service = Depends(get_service),
):
    try:
        await service.delete_conversation(user["account_id"], req.thread_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"message": "deleted"}


@router.post("/conversations/history")
async def get_history(
    req: ThreadRequest,
    user: dict = Depends(get_current_user),
    service: AgentV3Service = Depends(get_service),
):
    try:
        return await service.get_history(user["account_id"], req.thread_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="conversation not found")


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    user: dict = Depends(get_current_user_stateless),
    service: AgentV3Service = Depends(get_service),
):
    events = service.chat_stream(
        user["account_id"], user["username"], req.message, req.thread_id
    )
    return StreamingResponse(
        _stream(request, events),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/confirm")
async def confirm(
    req: ConfirmRequest,
    request: Request,
    user: dict = Depends(get_current_user_stateless),
    service: AgentV3Service = Depends(get_service),
):
    events = service.confirm(user["account_id"], req.thread_id, req.approved)
    return StreamingResponse(
        _stream(request, events),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
