"""点赞模块——Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field


class LikeRequest(BaseModel):
    video_id: int = Field(..., gt=0)


class IsLikedResponse(BaseModel):
    is_liked: bool
