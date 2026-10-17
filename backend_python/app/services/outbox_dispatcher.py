# -*- coding: utf-8 -*-
"""Dispatcher for `outbox_msgs` (transactional outbox).

Publishing a video writes three things in ONE transaction: the video row, its
tags, and an outbox row. That guarantees the "video published" event cannot be
lost even if a downstream side effect fails. This loop is the other half: it
turns `pending` rows into side effects (the Redis timeline) and marks them
`sent`.

Why a DB claim instead of a Redis lock: `FOR UPDATE SKIP LOCKED` lets several
workers drain the same table concurrently without stepping on each other, and
crash recovery is automatic -- a row locked by a dead transaction is claimable
again.

Failure policy (no schema change):
  * still pending and younger than MAX_AGE -> retried on the next tick
  * older than MAX_AGE -> marked `failed` so one poison row cannot retry forever
  * the video no longer exists -> marked `sent` (nothing to publish; this also
    avoids writing a dangling id into the timeline)

Redis unavailable -> do nothing this tick; rows stay pending and are retried.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.video import OutboxMsg, Video
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.services.feed_service import FeedService
from app.utils.redis_client import redis_client
from app.utils.timeutil import as_utc, utc_now

logger = logging.getLogger("outbox")

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 50
MAX_AGE_HOURS = 24


async def drain_once() -> int:
    """Process one batch. Returns how many rows were resolved."""
    if not redis_client.available:
        return 0

    resolved = 0
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(OutboxMsg)
                .where(OutboxMsg.status == "pending")
                .order_by(OutboxMsg.id)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        if not rows:
            return 0

        feed = FeedService(FeedRepository(session), LikeRepository(session))
        for row in rows:
            if row.event_type != "video_published":
                row.status = "failed"
                resolved += 1
                continue

            video_id = (
                await session.execute(select(Video.id).where(Video.id == row.video_id))
            ).scalar_one_or_none()
            if video_id is None:
                row.status = "sent"  # nothing left to publish
                resolved += 1
                continue

            try:
                await feed.add_to_timeline(row.video_id, row.create_time)
                row.status = "sent"
                resolved += 1
            except Exception:
                age = utc_now() - as_utc(row.create_time)
                if age > timedelta(hours=MAX_AGE_HOURS):
                    row.status = "failed"
                    resolved += 1
                logger.exception(
                    "outbox: failed to dispatch video %s (age %s)", row.video_id, age
                )

        await session.commit()
    return resolved


async def run_forever(interval: float = POLL_INTERVAL_SECONDS) -> None:
    """Poll until cancelled. The caller owns the task's lifetime."""
    while True:
        try:
            await drain_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient DB/Redis error must not kill the loop.
            logger.exception("outbox: dispatcher iteration failed")
        await asyncio.sleep(interval)
