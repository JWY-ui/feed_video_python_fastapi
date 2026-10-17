# -*- coding: utf-8 -*-
"""Notification fan-out over Redis Pub/Sub.

Why Redis: this used to be a module-level `user_id -> [asyncio.Queue]` registry.
Under more than one worker a publish only reached connections held by the same
process, so a user attached to worker 2 silently missed events raised on
worker 1. Every worker now subscribes to the same per-user channel, and the
producer just publishes.

Delivery is still **best-effort**. Pub/Sub has no persistence, and a recipient
with no open connection simply has nobody listening. That is acceptable because
the notification row is committed to MySQL first and the client re-reads the
list on load -- a dropped push is not lost data.

If Redis is unavailable, publish is a no-op and a subscription receives nothing;
the SSE stream itself keeps running (keepalive + client refresh).
"""
from __future__ import annotations

import asyncio
import json

from app.utils.redis_client import redis_client

_CHANNEL = "feedsystem:notify:{}"


class Subscription:
    """One open SSE connection: a queue fed by a Redis Pub/Sub subscriber."""

    def __init__(self, user_id: int, queue: asyncio.Queue,
                 pubsub=None, task: asyncio.Task | None = None):
        self.user_id = user_id
        self.queue = queue
        self._pubsub = pubsub
        self._task = task

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(_CHANNEL.format(self.user_id))
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None


async def subscribe(user_id: int, maxsize: int = 100) -> Subscription:
    """Register this worker as a listener for the user's channel."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    pubsub = redis_client.create_pubsub()
    if pubsub is None:
        return Subscription(user_id, queue)

    task = None
    try:
        await pubsub.subscribe(_CHANNEL.format(user_id))
        task = asyncio.create_task(_pump(pubsub, queue))
    except Exception:
        try:
            await pubsub.aclose()
        except Exception:
            pass
        return Subscription(user_id, queue)
    return Subscription(user_id, queue, pubsub, task)


async def publish(user_id: int, payload: dict) -> None:
    """Best-effort push. No subscriber (or no Redis) means it is dropped."""
    await redis_client.publish(
        _CHANNEL.format(user_id),
        json.dumps(payload, ensure_ascii=False, default=str),
    )


async def _pump(pubsub, queue: asyncio.Queue) -> None:
    """Move Pub/Sub messages into the SSE connection's queue."""
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if not message or message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
            except (TypeError, ValueError):
                continue
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                # That tab is not draining. Drop the push rather than block;
                # the client refreshes the list from MySQL anyway.
                pass
    except asyncio.CancelledError:
        raise
    except Exception:
        # A broken subscriber must not take down the SSE response.
        return
