# -*- coding: utf-8 -*-
"""
Notification routes -- 4 endpoints (including SSE real-time push).

=== Why the auth dependency is declared per-endpoint, not on the router ===
This router used `APIRouter(dependencies=[Depends(get_current_user)])`. A
router-level dependency applies to EVERY route, including /stream. Because
get_current_user -> get_db is a yield-dependency, its session would be held for
the lifetime of the SSE response -- i.e. forever -- pinning a pooled MySQL
connection per open stream whenever the token cache misses (Redis down). ~30
concurrent streams would then exhaust the pool and stall the whole app.

/stream therefore uses get_current_user_stateless, which authenticates and
releases its session before the stream starts. The other three endpoints keep
the ordinary dependency and stay protected exactly as before.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user, get_current_user_stateless
from app.schemas.notification import MarkReadRequest, UnreadCountResponse
from app.services import notification_bus
from app.services.notification_service import NotificationService


def _get_notification_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    from app.repositories.notification_repo import NotificationRepository
    return NotificationService(NotificationRepository(db))


router = APIRouter()


@router.get("/stream")
async def notification_stream(request: Request,
                              user: dict = Depends(get_current_user_stateless)):
    """
    Server-Sent Events stream of this user's notifications.

    Frames are `data: {json}`; a `: keepalive` comment is emitted every 30s so
    proxies don't reap an idle connection. The first frame is a `connected`
    handshake the client can use to confirm the stream is live.

    Note: the client must use fetch + ReadableStream, not the browser's
    EventSource -- EventSource cannot send an Authorization header, and this
    endpoint deliberately does not accept a token in the query string (it would
    leak into access logs and browser history).
    """
    user_id = user["account_id"]
    queue = notification_bus.subscribe(user_id)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'connected', 'user_id': user_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            notification_bus.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


@router.post("/list")
async def list_notifications(current_user: dict = Depends(get_current_user),
                             service: NotificationService = Depends(_get_notification_service)):
    """Returns a bare array (kept as-is: the frontend already expects one)."""
    return await service.list_by_user(current_user["account_id"])


@router.post("/markRead")
async def mark_read(req: MarkReadRequest,
                    current_user: dict = Depends(get_current_user),
                    service: NotificationService = Depends(_get_notification_service)):
    """`id` omitted/null means mark everything read."""
    await service.mark_read(current_user["account_id"], req.id)
    return {"message": "marked read"}


@router.post("/unreadCount", response_model=UnreadCountResponse)
async def unread_count(current_user: dict = Depends(get_current_user),
                       service: NotificationService = Depends(_get_notification_service)):
    count = await service.unread_count(current_user["account_id"])
    return UnreadCountResponse(count=count)
