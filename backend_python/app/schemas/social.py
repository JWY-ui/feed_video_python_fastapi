# -*- coding: utf-8 -*-
"""Follow module -- Pydantic request/response models."""
from pydantic import BaseModel, Field


class FollowRequest(BaseModel):
    vlogger_id: int = Field(..., gt=0)


class UnfollowRequest(BaseModel):
    vlogger_id: int = Field(..., gt=0)


class GetAllFollowersRequest(BaseModel):
    vlogger_id: int = 0  # 0 means query current logged-in user


class GetAllVloggersRequest(BaseModel):
    follower_id: int = 0


class UserBrief(BaseModel):
    id: int
    username: str
    avatar_url: str | None = None
    bio: str | None = None


class GetAllFollowersResponse(BaseModel):
    followers: list[UserBrief]
    follower_count: int


class GetAllVloggersResponse(BaseModel):
    vloggers: list[UserBrief]
    vlogger_count: int


class SocialCounts(BaseModel):
    follower_count: int
    vlogger_count: int
