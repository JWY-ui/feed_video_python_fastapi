# -*- coding: utf-8 -*-
"""Follow routes -- 5 endpoints, all require login."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user
from app.repositories.social_repo import SocialRepository
from app.repositories.account_repo import AccountRepository
from app.schemas.social import (
    FollowRequest, UnfollowRequest,
    GetAllFollowersRequest, GetAllFollowersResponse,
    GetAllVloggersRequest, GetAllVloggersResponse,
    SocialCounts,
)
from app.services.social_service import SocialService

router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_social_service(db: AsyncSession = Depends(get_db)) -> SocialService:
    return SocialService(SocialRepository(db), AccountRepository(db))


@router.post("/follow")
async def follow(req: FollowRequest,
                 current_user: dict = Depends(get_current_user),
                 service: SocialService = Depends(_get_social_service)):
    try:
        await service.follow(current_user["account_id"], req.vlogger_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "followed"}


@router.post("/unfollow")
async def unfollow(req: UnfollowRequest,
                   current_user: dict = Depends(get_current_user),
                   service: SocialService = Depends(_get_social_service)):
    try:
        await service.unfollow(current_user["account_id"], req.vlogger_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "unfollowed"}


@router.post("/getAllFollowers", response_model=GetAllFollowersResponse)
async def get_all_followers(req: GetAllFollowersRequest,
                            current_user: dict = Depends(get_current_user),
                            service: SocialService = Depends(_get_social_service)):
    vlogger_id = req.vlogger_id if req.vlogger_id != 0 else current_user["account_id"]
    followers, count = await service.get_all_followers(vlogger_id)
    return GetAllFollowersResponse(followers=followers, follower_count=count)


@router.post("/getAllVloggers", response_model=GetAllVloggersResponse)
async def get_all_vloggers(req: GetAllVloggersRequest,
                           current_user: dict = Depends(get_current_user),
                           service: SocialService = Depends(_get_social_service)):
    follower_id = req.follower_id if req.follower_id != 0 else current_user["account_id"]
    vloggers, count = await service.get_all_vloggers(follower_id)
    return GetAllVloggersResponse(vloggers=vloggers, vlogger_count=count)


@router.post("/getCounts", response_model=SocialCounts)
async def get_counts(current_user: dict = Depends(get_current_user),
                     service: SocialService = Depends(_get_social_service)):
    follower_count, vlogger_count = await service.get_counts(current_user["account_id"])
    return SocialCounts(follower_count=follower_count, vlogger_count=vlogger_count)
