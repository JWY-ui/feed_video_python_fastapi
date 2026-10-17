# -*- coding: utf-8 -*-
"""Like routes -- 4 endpoints, all require login."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository
from app.schemas.like import IsLikedResponse, LikeRequest, ListMyLikedRequest
from app.services.like_service import LikeService

router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_like_service(db: AsyncSession = Depends(get_db)) -> LikeService:
    return LikeService(LikeRepository(db), VideoRepository(db))


@router.post("/like")
async def like(req: LikeRequest,
               current_user: dict = Depends(get_current_user),
               service: LikeService = Depends(_get_like_service)):
    try:
        await service.like(req.video_id, current_user["account_id"],
                           current_user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "like success"}


@router.post("/unlike")
async def unlike(req: LikeRequest,
                 current_user: dict = Depends(get_current_user),
                 service: LikeService = Depends(_get_like_service)):
    try:
        await service.unlike(req.video_id, current_user["account_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "unlike success"}


@router.post("/isLiked", response_model=IsLikedResponse)
async def is_liked(req: LikeRequest,
                   current_user: dict = Depends(get_current_user),
                   service: LikeService = Depends(_get_like_service)):
    result = await service.is_liked(req.video_id, current_user["account_id"])
    return IsLikedResponse(is_liked=result)


@router.post("/listMyLikedVideos")
async def list_my_liked_videos(req: ListMyLikedRequest | None = None,
                               current_user: dict = Depends(get_current_user),
                               service: LikeService = Depends(_get_like_service)):
    """Bare array, as before. Each item now also carries `like_id` + `liked_at`;
    pass the last item's pair back to fetch the next page."""
    req = req or ListMyLikedRequest()
    return await service.list_liked_videos(
        current_user["account_id"],
        limit=req.limit,
        before_time=req.before_time,
        before_id=req.before_id,
    )
