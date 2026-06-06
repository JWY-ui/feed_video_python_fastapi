# -*- coding: utf-8 -*-
"""
Notification routes -- 4 endpoints (including SSE real-time push), all require login.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.notification_repo import NotificationRepository
from app.schemas.notification import MarkReadRequest, UnreadCountResponse

router = APIRouter(dependencies=[Depends(get_current_user)])

_sse_clients: dict[int, list[asyncio.Queue]] = {}


def push_sse(user_id: int, data: dict):
    for q in _sse_clients.get(user_id, []):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


@router.get("/stream")
async def notification_stream(request: Request,
                              user: dict = Depends(get_current_user)):
    user_id = user["account_id"]
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_clients.setdefault(user_id, []).append(queue)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_clients.get(user_id, []).remove(queue)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


@router.post("/list")
async def list_notifications(current_user: dict = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    repo = NotificationRepository(db)
    return await repo.list_by_user(current_user["account_id"])


@router.post("/markRead")
async def mark_read(req: MarkReadRequest,
                    current_user: dict = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    repo = NotificationRepository(db)
    await repo.mark_read(current_user["account_id"], req.id)
    return {"message": "marked read"}


@router.post("/unreadCount", response_model=UnreadCountResponse)
async def unread_count(current_user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    repo = NotificationRepository(db)
    count = await repo.unread_count(current_user["account_id"])
    return UnreadCountResponse(count=count)
