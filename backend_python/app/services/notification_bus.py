# -*- coding: utf-8 -*-
"""
In-process notification fan-out bus.

Sits between the producers (like/comment/follow services) and the single
consumer (the SSE endpoint in routers/notification.py). Its whole reason to
exist is to keep services from importing a router -- service -> router would
invert the layering and risk a circular import, since the router imports
services.

=== Deployment caveat ===
This registry is plain process memory. Under multiple workers
(`uvicorn --workers N`, gunicorn) a publish only reaches connections held by
the SAME worker, so a user attached to worker 2 misses events raised on
worker 1. The Docker image runs a single worker, so this is sound today.
For multi-worker, replace the registry with Redis Pub/Sub -- the subscribe /
publish / unsubscribe surface below is the seam to swap.
"""
import asyncio

# user_id -> queues, one per open SSE connection (a user may have several tabs)
_clients: dict[int, list[asyncio.Queue]] = {}


def subscribe(user_id: int, maxsize: int = 100) -> asyncio.Queue:
    """Register a connection and return its queue."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _clients.setdefault(user_id, []).append(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    """
    Drop a connection. Also removes the now-empty list so logging in and out
    repeatedly doesn't leave a growing trail of empty lists behind.
    """
    queues = _clients.get(user_id)
    if not queues:
        return
    try:
        queues.remove(queue)
    except ValueError:
        return
    if not queues:
        _clients.pop(user_id, None)


def publish(user_id: int, payload: dict) -> None:
    """
    Best-effort delivery.

    A recipient with no open connection is the normal case (they are offline),
    so it must be a silent no-op. A full queue means that tab is not draining --
    drop the event rather than block or raise; the client re-reads the list from
    MySQL on load anyway, so nothing is permanently lost.
    """
    for queue in list(_clients.get(user_id, [])):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass
