# -*- coding: utf-8 -*-
"""Chunked-upload session state, kept in Redis.

Why this is not a module-level dict any more: the session used to live in
`routers/video.py` as plain process memory, so a restart lost an in-flight
upload and a second worker could not resume one started on the first. The chunk
**bytes** still live on the uploads volume (as before); only the small session
record moves here.

Key layout (all TTL 24h):

    chunk:session:<upload_id>        JSON session record
    chunk:hash:<account>:<hash>      upload_id, for resume by file hash
    chunk:chunks:<upload_id>         SET of chunk indices already stored

Redis being unavailable is a hard error for this feature: without the session
record there is no safe way to say which chunks landed, and silently starting
over could hand a half-written file to the merger.
"""
from __future__ import annotations

import json
import uuid

from app.utils.redis_client import redis_client

SESSION_TTL = 24 * 3600


class ChunkStateUnavailable(RuntimeError):
    """The session store (Redis) is not usable."""


def _session_key(upload_id: str) -> str:
    return f"chunk:session:{upload_id}"


def _hash_key(account_id: int, file_hash: str) -> str:
    return f"chunk:hash:{account_id}:{file_hash}"


def _chunks_key(upload_id: str) -> str:
    return f"chunk:chunks:{upload_id}"


def is_available() -> bool:
    return redis_client.available


async def load(upload_id: str) -> dict | None:
    """Return the session record, or None when it does not exist."""
    if not redis_client.available:
        raise ChunkStateUnavailable("Redis unavailable")
    raw = await redis_client.get(_session_key(upload_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def init(account_id: int, filename: str, file_size: int, chunk_size: int,
               total_chunks: int, file_hash: str) -> tuple[str, list[int]]:
    """Create a session, or return the existing one for this (account, file hash).

    Returns (upload_id, already_uploaded_indices).
    """
    if not redis_client.available:
        raise ChunkStateUnavailable("Redis unavailable")

    hash_key = _hash_key(account_id, file_hash)
    existing_id = await redis_client.get(hash_key)
    if existing_id:
        session = await load(existing_id)
        # A stale mapping (session expired) just falls through to a new session.
        if session and session.get("account_id") == account_id:
            return existing_id, await uploaded_indices(existing_id)

    upload_id = uuid.uuid4().hex
    session = {
        "account_id": account_id,
        "filename": filename,
        "file_size": file_size,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "file_hash": file_hash,
    }
    if not await redis_client.set(
        _session_key(upload_id), json.dumps(session), ex=SESSION_TTL
    ):
        raise ChunkStateUnavailable("failed to persist upload session")
    # Written second: a reader only trusts the hash mapping if the session exists.
    await redis_client.set(hash_key, upload_id, ex=SESSION_TTL)
    return upload_id, []


async def is_uploaded(upload_id: str, chunk_index: int) -> bool:
    return await redis_client.sismember(_chunks_key(upload_id), str(chunk_index))


async def mark_uploaded(upload_id: str, chunk_index: int) -> None:
    await redis_client.sadd(
        _chunks_key(upload_id), str(chunk_index), ex=SESSION_TTL
    )


async def uploaded_indices(upload_id: str) -> list[int]:
    members = await redis_client.smembers(_chunks_key(upload_id))
    return sorted(int(m) for m in members if m.isdigit())


async def drop(upload_id: str, account_id: int, file_hash: str) -> None:
    await redis_client.delete(
        _session_key(upload_id),
        _chunks_key(upload_id),
        _hash_key(account_id, file_hash),
    )
