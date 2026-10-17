# -*- coding: utf-8 -*-
"""
Video module routes -- 9 endpoints.
"""
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.video_repo import VideoRepository
from app.schemas.video import (
    PublishVideoRequest, VideoInfo,
    ListByAuthorIDRequest, GetDetailRequest,
    UploadResponse, CoverUploadResponse,
    InitChunkRequest, InitChunkResponse,
    ChunkStatusRequest, ChunkStatusResponse,
    CompleteChunkRequest,
)
from app.services import chunk_session
from app.services.video_service import VideoService
from app.services.feed_service import FeedService
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository

public_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])

def _require_chunk_store() -> None:
    """Chunked upload needs Redis: the session decides which chunks exist.

    Without it we cannot tell a fresh upload from a resume, so fail loudly
    instead of silently starting over and merging a half-written file.
    """
    if not chunk_session.is_available():
        raise HTTPException(
            status_code=503,
            detail="chunked upload unavailable: Redis is not connected",
        )


async def _load_chunk_session(upload_id: str, account_id: int) -> dict:
    session = await chunk_session.load(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if session["account_id"] != account_id:
        raise HTTPException(status_code=403, detail="not your upload session")
    return session


def _get_video_service(db: AsyncSession = Depends(get_db)) -> VideoService:
    return VideoService(VideoRepository(db), db)


def _build_absolute_url(request: Request, path: str) -> str:
    scheme = request.headers.get("X-Forwarded-Proto", "http")
    return f"{scheme}://{request.base_url.netloc.rstrip('/')}{path}"


# ==================== Public endpoints ====================

@public_router.post("/listByAuthorID")
async def list_by_author_id(req: ListByAuthorIDRequest,
                            service: VideoService = Depends(_get_video_service)):
    return await service.list_by_author(req.author_id)


@public_router.post("/getDetail")
async def get_detail(req: GetDetailRequest,
                     service: VideoService = Depends(_get_video_service)):
    try:
        return await service.get_detail(req.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== Protected endpoints (require login) ====================

@protected_router.post("/publish")
async def publish_video(req: PublishVideoRequest,
                        current_user: dict = Depends(get_current_user),
                        service: VideoService = Depends(_get_video_service),
                        db: AsyncSession = Depends(get_db)):
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    if not req.play_url.strip():
        raise HTTPException(status_code=400, detail="play url is required")
    if not req.cover_url.strip():
        raise HTTPException(status_code=400, detail="cover url is required")
    video = await service.publish(
        author_id=current_user["account_id"], username=current_user["username"],
        title=req.title, description=req.description,
        play_url=req.play_url, cover_url=req.cover_url,
    )
    # Write to Feed timeline (Redis ZSET)
    feed_svc = FeedService(FeedRepository(db), LikeRepository(db))
    from datetime import datetime
    create_time = datetime.fromisoformat(video["create_time"]) if isinstance(video["create_time"], str) else video["create_time"]
    await feed_svc.add_to_timeline(video["id"], create_time)
    return video


@protected_router.post("/uploadVideo")
async def upload_video(file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user),
                       request: Request = None):
    contents = await _read_and_validate(file, {".mp4"}, 200 * 1024 * 1024)
    path = VideoService.save_upload(
        contents, file.filename or "video.mp4", "videos",
        current_user["account_id"], {".mp4"}, 200 * 1024 * 1024,
    )
    abs_url = _build_absolute_url(request, path) if request else path
    return UploadResponse(url=abs_url, play_url=abs_url)


@protected_router.post("/uploadCover")
async def upload_cover(file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user),
                       request: Request = None):
    contents = await _read_and_validate(file, {".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024)
    path = VideoService.save_upload(
        contents, file.filename or "cover.jpg", "covers",
        current_user["account_id"], {".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024,
    )
    abs_url = _build_absolute_url(request, path) if request else path
    return CoverUploadResponse(url=abs_url, cover_url=abs_url)


# ==================== Chunked upload ====================

@protected_router.post("/chunk/init", response_model=InitChunkResponse)
async def chunk_init(req: InitChunkRequest,
                     current_user: dict = Depends(get_current_user)):
    _require_chunk_store()
    upload_id, uploaded = await chunk_session.init(
        account_id=current_user["account_id"],
        filename=req.filename,
        file_size=req.file_size,
        chunk_size=req.chunk_size,
        total_chunks=req.total_chunks,
        file_hash=req.file_hash,
    )
    return InitChunkResponse(upload_id=upload_id, uploaded_chunks=uploaded)


@protected_router.post("/chunk/upload")
async def chunk_upload(upload_id: str = Form(...),
                       chunk_index: int = Form(...),
                       chunk_hash: str = Form(...),
                       file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user)):
    _require_chunk_store()
    session = await _load_chunk_session(upload_id, current_user["account_id"])
    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(status_code=400, detail="chunk_index out of range")
    if await chunk_session.is_uploaded(upload_id, chunk_index):
        raise HTTPException(status_code=409, detail="chunk already uploaded")
    chunk_data = await file.read()
    if hashlib.md5(chunk_data).hexdigest() != chunk_hash:
        raise HTTPException(status_code=400, detail="chunk hash mismatch")
    VideoService.save_chunk(upload_id, chunk_index, chunk_data)
    await chunk_session.mark_uploaded(upload_id, chunk_index)
    return {"chunk_index": chunk_index}


@protected_router.post("/chunk/status", response_model=ChunkStatusResponse)
async def chunk_status(req: ChunkStatusRequest,
                       current_user: dict = Depends(get_current_user)):
    _require_chunk_store()
    session = await _load_chunk_session(req.upload_id, current_user["account_id"])
    return ChunkStatusResponse(
        upload_id=req.upload_id,
        uploaded_chunks=await chunk_session.uploaded_indices(req.upload_id),
        total_chunks=session["total_chunks"],
    )


@protected_router.post("/chunk/complete")
async def chunk_complete(req: CompleteChunkRequest,
                         current_user: dict = Depends(get_current_user),
                         request: Request = None):
    _require_chunk_store()
    session = await _load_chunk_session(req.upload_id, current_user["account_id"])
    uploaded = await chunk_session.uploaded_indices(req.upload_id)
    if len(uploaded) != session["total_chunks"]:
        raise HTTPException(status_code=400, detail="not all chunks uploaded")
    try:
        path = VideoService.merge_chunks(
            req.upload_id, session["total_chunks"],
            session["filename"], current_user["account_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    await chunk_session.drop(
        req.upload_id, current_user["account_id"], session["file_hash"]
    )
    abs_url = _build_absolute_url(request, path) if request else path
    return UploadResponse(url=abs_url, play_url=abs_url)


async def _read_and_validate(file: UploadFile, allowed_exts: set[str], max_size: int) -> bytes:
    """Read file content once and validate size + extension. Returns the file bytes."""
    contents = await file.read()
    if len(contents) == 0 or len(contents) > max_size:
        raise HTTPException(status_code=400,
                            detail=f"invalid file size, max {max_size // (1024*1024)}MB")
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"only {allowed_exts} allowed")
    return contents


