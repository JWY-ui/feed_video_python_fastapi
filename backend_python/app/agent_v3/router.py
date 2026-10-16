"""/agent/* 端点。

分两个路由器，因为两类端点的依赖完全不同：

* `router` —— 会话管理（列表 / 历史 / 删除）。纯 DB 查询，廉价，不限流、
  不要求 Redis。
* `stream_router` —— 对话（/chat、/confirm）。SSE，要会话锁、要限流，是全站
  最贵的两个端点。

/chat 与 /confirm 都用 `get_current_user_stateless`：普通认证依赖
（get_current_user → get_db）会挂着一个 DB session 直到响应结束，对 SSE 就是
永远 —— 40 条并发流足以耗尽连接池。这是上一轮修 SSE 时踩过的坑。

帧格式与 /notification/stream 一致（`data: {json}`），前端复用同一个 SSE 解析器。
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agent_v3.deps import chat_rate_limiter, get_service, require_lock_backend
from app.agent_v3.schemas import ChatRequest, ConfirmRequest, ThreadRequest
from app.agent_v3.service import AgentV3Service
from app.middleware.jwt_auth import get_current_user, get_current_user_stateless

router = APIRouter()

stream_router = APIRouter(
    dependencies=[Depends(chat_rate_limiter), Depends(require_lock_backend)]
)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # nginx 默认缓冲会把 SSE 攒成一坨再发，必须关掉
    "X-Accel-Buffering": "no",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream(request: Request, events):
    """把 service 的事件流转成 SSE 帧；客户端断开就停下并关掉上游生成器。

    为什么必须显式 `aclose()`：会话锁是在 service 的 `async with` 里持有的，
    只有上游生成器被关闭才会释放。不显式关，就得等 GC 触发异步生成器的终结器 ——
    时机不确定，而锁没释放的那个会话要到 TTL 到期才打得开。

    这里能保证的是「停止推流，并尽快取消图运行」。**一次已经提交到数据库的写操作
    撤不回来** —— 别把这条读成「断开能拦住写操作」。
    """
    try:
        async for event in events:
            if await request.is_disconnected():
                break
            yield _sse(event)
    finally:
        # 任务正被取消时，finally 里的 await 自己也会吃一个 CancelledError，
        # aclose 就做不完了。shield 把清理放到独立任务上跑完；suppress 只吞
        # 清理过程中的普通异常，取消本身照旧往外抛（那是正确的取消语义）。
        with contextlib.suppress(Exception):
            await asyncio.shield(events.aclose())


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


@stream_router.post("/chat")
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


@stream_router.post("/confirm")
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
