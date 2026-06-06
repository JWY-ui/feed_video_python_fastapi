# -*- coding: utf-8 -*-
"""Comment routes -- 3 endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.comment_repo import CommentRepository
from app.repositories.video_repo import VideoRepository
from app.schemas.comment import (
    PublishCommentRequest, DeleteCommentRequest, GetAllCommentsRequest,
)
from app.services.comment_service import CommentService

public_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_comment_service(db: AsyncSession = Depends(get_db)) -> CommentService:
    return CommentService(CommentRepository(db), VideoRepository(db))


@public_router.post("/listAll")
async def list_all(req: GetAllCommentsRequest, db: AsyncSession = Depends(get_db)):
    service = CommentService(CommentRepository(db), VideoRepository(db))
    try:
        return await service.get_all(req.video_id)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@protected_router.post("/publish")
async def publish(req: PublishCommentRequest,
                  current_user: dict = Depends(get_current_user),
                  service: CommentService = Depends(_get_comment_service)):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    try:
        await service.publish(
            req.video_id, current_user["account_id"],
            current_user["username"], req.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "comment published successfully"}


@protected_router.post("/delete")
async def delete_comment(req: DeleteCommentRequest,
                         current_user: dict = Depends(get_current_user),
                         service: CommentService = Depends(_get_comment_service)):
    try:
        await service.delete(req.comment_id, current_user["account_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"message": "comment deleted successfully"}
