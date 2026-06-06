"""
视频模块路由——9 个接口
"""
import hashlib
import os
import uuid

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
from app.services.video_service import VideoService
from app.services.feed_service import FeedService
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository

public_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])

_chunk_sessions: dict[str, dict] = {}


def _get_video_service(db: AsyncSession = Depends(get_db)) -> VideoService:
    return VideoService(VideoRepository(db), db)


def _build_absolute_url(request: Request, path: str) -> str:
    scheme = request.headers.get("X-Forwarded-Proto", "http")
    return f"{scheme}://{request.base_url.netloc.rstrip('/')}{path}"


# ═══════════ 公开接口 ═══════════

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
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════ 需登录 ═══════════

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
    # 写入 Feed 时间线（Redis ZSET）
    feed_svc = FeedService(FeedRepository(db), LikeRepository(db))
    from datetime import datetime
    create_time = datetime.fromisoformat(video["create_time"]) if isinstance(video["create_time"], str) else video["create_time"]
    await feed_svc.add_to_timeline(video["id"], create_time)
    return video


@protected_router.post("/uploadVideo")
async def upload_video(file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user),
                       request: Request = None):
    await _check_upload_file(file, {".mp4"}, 200 * 1024 * 1024)
    contents = await file.read()
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
    await _check_upload_file(file, {".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024)
    contents = await file.read()
    path = VideoService.save_upload(
        contents, file.filename or "cover.jpg", "covers",
        current_user["account_id"], {".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024,
    )
    abs_url = _build_absolute_url(request, path) if request else path
    return CoverUploadResponse(url=abs_url, cover_url=abs_url)


# ═══════════ 分片上传 ═══════════

@protected_router.post("/chunk/init", response_model=InitChunkResponse)
async def chunk_init(req: InitChunkRequest,
                     current_user: dict = Depends(get_current_user)):
    account_id = current_user["account_id"]
    hash_key = f"chunk:{account_id}:{req.file_hash}"
    existing = _chunk_sessions.get(hash_key)
    if existing and existing in _chunk_sessions:
        session = _chunk_sessions[existing]
        return InitChunkResponse(
            upload_id=existing, uploaded_chunks=_uploaded_indices(session["uploaded"]),
        )
    upload_id = uuid.uuid4().hex
    _chunk_sessions[upload_id] = {
        "account_id": account_id, "filename": req.filename,
        "file_size": req.file_size, "chunk_size": req.chunk_size,
        "total_chunks": req.total_chunks, "file_hash": req.file_hash,
        "uploaded": [False] * req.total_chunks,
    }
    _chunk_sessions[hash_key] = upload_id
    return InitChunkResponse(upload_id=upload_id, uploaded_chunks=[])


@protected_router.post("/chunk/upload")
async def chunk_upload(upload_id: str = Form(...),
                       chunk_index: int = Form(...),
                       chunk_hash: str = Form(...),
                       file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user)):
    session = _chunk_sessions.get(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if session["account_id"] != current_user["account_id"]:
        raise HTTPException(status_code=403, detail="not your upload session")
    if chunk_index < 0 or chunk_index >= session["total_chunks"]:
        raise HTTPException(status_code=400, detail="chunk_index out of range")
    if session["uploaded"][chunk_index]:
        raise HTTPException(status_code=409, detail="chunk already uploaded")
    chunk_data = await file.read()
    if hashlib.md5(chunk_data).hexdigest() != chunk_hash:
        raise HTTPException(status_code=400, detail="chunk hash mismatch")
    VideoService.save_chunk(upload_id, chunk_index, chunk_data)
    session["uploaded"][chunk_index] = True
    return {"chunk_index": chunk_index}


@protected_router.post("/chunk/status", response_model=ChunkStatusResponse)
async def chunk_status(req: ChunkStatusRequest,
                       current_user: dict = Depends(get_current_user)):
    session = _chunk_sessions.get(req.upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if session["account_id"] != current_user["account_id"]:
        raise HTTPException(status_code=403, detail="not your upload session")
    return ChunkStatusResponse(
        upload_id=req.upload_id,
        uploaded_chunks=_uploaded_indices(session["uploaded"]),
        total_chunks=session["total_chunks"],
    )


@protected_router.post("/chunk/complete")
async def chunk_complete(req: CompleteChunkRequest,
                         current_user: dict = Depends(get_current_user),
                         request: Request = None):
    session = _chunk_sessions.get(req.upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if session["account_id"] != current_user["account_id"]:
        raise HTTPException(status_code=403, detail="not your upload session")
    if not all(session["uploaded"]):
        raise HTTPException(status_code=400, detail="not all chunks uploaded")
    try:
        path = VideoService.merge_chunks(
            req.upload_id, session["total_chunks"],
            session["filename"], current_user["account_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    hash_key = f"chunk:{current_user['account_id']}:{session['file_hash']}"
    _chunk_sessions.pop(hash_key, None)
    _chunk_sessions.pop(req.upload_id, None)
    abs_url = _build_absolute_url(request, path) if request else path
    return UploadResponse(url=abs_url, play_url=abs_url)


async def _check_upload_file(file: UploadFile, allowed_exts: set[str], max_size: int):
    contents = await file.read()
    if len(contents) == 0 or len(contents) > max_size:
        raise HTTPException(status_code=400,
                            detail=f"invalid file size, max {max_size // (1024*1024)}MB")
    await file.seek(0)
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"only {allowed_exts} allowed")


def _uploaded_indices(uploaded: list[bool]) -> list[int]:
    return [i for i, done in enumerate(uploaded) if done]
